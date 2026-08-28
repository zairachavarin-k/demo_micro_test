# Evidence Collection Guide — Performance Degradation Analysis

This guide provides tools and procedures to collect, correlate, and analyze evidence for the `demo-incident-fastapi` performance degradation incident (Issue #5).

## Overview

The incident involves connection pool exhaustion under concurrent load on the `/transactions` endpoint. Evidence collection requires:

1. **Response-time measurements** — Per-request latency, status codes, correlation IDs
2. **Container App metrics** — CPU, memory, request volume, scale events
3. **Application logs** — /transactions requests, 503 errors, timeout messages
4. **Distributed traces** — End-to-end latency breakdown across layers
5. **Configuration/deployment evidence** — Revision timeline, environment variables, resource limits

## Tools Included

### 1. Response-Time Collection: `collect_response_metrics.py`

Collects per-request latency and status data with configurable concurrency.

**Usage:**

```bash
# Healthy baseline (serial requests)
python collect_response_metrics.py \
    --url http://localhost:8000 \
    --requests 50 \
    --concurrency 1 \
    --label "healthy_baseline"

# Incident reproduction (concurrent load)
python collect_response_metrics.py \
    --url http://localhost:8000 \
    --requests 50 \
    --concurrency 10 \
    --label "incident_concurrent_20260828"

# Post-mitigation validation
python collect_response_metrics.py \
    --url http://localhost:8000 \
    --requests 50 \
    --concurrency 10 \
    --label "post_mitigation_20260828"
```

**Output:**

- `evidence_{label}_detailed.json` — Per-request metrics (timestamp, request_id, correlation_id, status, elapsed_ms)
- Console summary with percentiles (p50, p90, p95, p99), max latency, success/failure rates

**Success Criterion:**
- Capture latency percentiles approaching 3-second acquisition timeout when pool exhausted
- Show 503 error rates for incident vs. healthy baseline
- Demonstrate recovery post-mitigation

### 2. Container App Metrics: `collect_container_evidence.py`

Queries Azure Container App for configuration, revision history, logs, and metrics.

**Prerequisites:**

```bash
# Install Azure CLI
az login
az account set --subscription <subscription-id>
```

**Usage:**

```bash
# Collect configuration and revision history
python collect_container_evidence.py \
    --resource-group my-resource-group \
    --container-app demo-incident-fastapi

# Collect logs and metrics for incident window
python collect_container_evidence.py \
    --resource-group my-resource-group \
    --container-app demo-incident-fastapi \
    --workspace-id <log-analytics-workspace-id> \
    --start-time 2026-08-28T03:00:00Z \
    --end-time 2026-08-28T06:00:00Z \
    --label "incident_window_20260828"

# Collect post-mitigation metrics
python collect_container_evidence.py \
    --resource-group my-resource-group \
    --container-app demo-incident-fastapi \
    --workspace-id <log-analytics-workspace-id> \
    --start-time 2026-08-28T07:00:00Z \
    --end-time 2026-08-28T08:00:00Z \
    --label "post_mitigation_20260828"
```

**Output:**

- `evidence_{label}_container.json` containing:
  - Configuration: image, environment variables, resource limits, scale rules
  - Revision history: creation time, active status, traffic weight
  - Application logs: /transactions requests, 503 errors, timeouts
  - Metrics: CPU, memory, replica count, request counts (1-minute granularity)
  - Activity Log: deployment and configuration change timeline

**Success Criterion:**
- Configuration matches issue context (FAULT_MODE=pool_leak, POOL_SIZE=5)
- Logs show initial 200 responses followed by 503s after ~3 seconds
- Metrics correlate scale events and high latency with active revision
- Activity Log shows deployment correlation ID

### 3. Distributed Tracing: `app/tracer.py`

W3C trace context instrumentation for end-to-end latency tracking.

**Usage in application code:**

```python
from app.tracer import get_tracer

tracer = get_tracer(__name__)

@app.get("/transactions")
def listar_transacciones():
    with tracer.trace_request("GET /transactions", status_code=200) as span:
        inicio = time.time()
        
        with tracer.trace_dependency("db_pool.acquire") as dep_span:
            conexion = obtener_conexion()
            dep_span.tags["acquisition_time_ms"] = (time.time() - inicio) * 1000
        
        try:
            resultado = ejecutar_consulta_simulada(_transacciones)
            span.tags["query_time_ms"] = (time.time() - inicio) * 1000
            # ... return result
        except TimeoutError as e:
            span.status_code = 503
            raise
```

**Output:**

- Structured logs with trace_id, span_id, duration, status_code
- Dependency timing: pool acquisition, query execution
- JSON export for Application Insights ingestion

**Success Criterion:**
- Trace samples show pool acquisition approaching 3-second timeout
- Dependency timing isolates pool exhaustion as bottleneck
- Each slow/failed request has end-to-end trace

### 4. Evidence Manifest: `app/evidence.py`

Structured tracking of evidence completion.

**Usage:**

```python
from app.evidence import EvidenceManifest, EvidenceWindow

manifest = EvidenceManifest("incident_window_20260828")
manifest.incident_window = EvidenceWindow(
    label="incident",
    start_utc="2026-08-28T03:00:00Z",
    end_utc="2026-08-28T06:00:00Z",
    duration_minutes=180,
    description="Connection pool exhaustion: 503 errors and high latency",
)

manifest.add_source("metrics", "response_times", "evidence_incident_response.json")
manifest.add_source("logs", "container_logs", "evidence_incident_container.json")
manifest.add_finding("pool_exhaustion", "Pool of 5 connections saturated after 5 requests")
manifest.mark_complete("latency_percentiles_captured")
manifest.save()
```

**Output:**

- `evidence_manifest_{manifest_id}.json` — Master evidence index
- Tracks completion against Issue #5 criteria
- Records key findings and correlations

## Collection Workflow

### Phase 1: Establish Baseline (Healthy State)

**Timeline:** ~15 minutes

```bash
# 1. Ensure FAULT_MODE=none in Container App
az containerapp update \
    --name demo-incident-fastapi \
    --resource-group my-rg \
    --set-env-vars FAULT_MODE=none

# 2. Wait 2 minutes for stability, then collect response times
python collect_response_metrics.py \
    --url https://your-app.azurecontainerapps.io \
    --requests 50 \
    --concurrency 1 \
    --label "healthy_baseline_serial"

python collect_response_metrics.py \
    --url https://your-app.azurecontainerapps.io \
    --requests 50 \
    --concurrency 10 \
    --label "healthy_baseline_concurrent"

# 3. Collect container evidence for healthy window
python collect_container_evidence.py \
    --resource-group my-rg \
    --container-app demo-incident-fastapi \
    --workspace-id <workspace-id> \
    --start-time 2026-08-28T00:00:00Z \
    --end-time 2026-08-28T02:00:00Z \
    --label "healthy_baseline"
```

**Validation:**
- All requests return 200 OK
- Latency p99 < 500 ms
- No 503 errors
- CPU/memory stable
- No scale-up events

### Phase 2: Incident Reproduction (Pool Leak Active)

**Timeline:** ~20 minutes

```bash
# 1. Enable FAULT_MODE=pool_leak
az containerapp update \
    --name demo-incident-fastapi \
    --resource-group my-rg \
    --set-env-vars FAULT_MODE=pool_leak

# 2. Wait 2 minutes for revision rollout, note start time
START_TIME=$(date -u +'%Y-%m-%dT%H:%M:%SZ')

# 3. Collect response times (10 concurrent = exceeds pool size of 5)
python collect_response_metrics.py \
    --url https://your-app.azurecontainerapps.io \
    --requests 50 \
    --concurrency 10 \
    --label "incident_20260828"

# 4. Collect container evidence
END_TIME=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
python collect_container_evidence.py \
    --resource-group my-rg \
    --container-app demo-incident-fastapi \
    --workspace-id <workspace-id> \
    --start-time $START_TIME \
    --end-time $END_TIME \
    --label "incident_20260828"
```

**Validation:**
- Initial requests return 200 OK (~5 concurrent)
- Requests 6+ wait and return 503 (pool exhausted)
- Latency percentiles approach 3-second timeout
- Container logs show "No hay conexiones" errors
- Scale-up events triggered by error rate/latency
- CPU/memory usage increases

### Phase 3: Apply Mitigation

**Fix in `app/db_pool.py`:**

```python
def ejecutar_consulta_simulada(datos):
    conexion = obtener_conexion()
    try:
        time.sleep(0.05)
        resultado = {"procesado": True, "items": len(datos)}
        return resultado
    finally:
        conexion.liberar()  # Always release, regardless of mode
```

**Deployment:**

```bash
# 1. Update code and rebuild image
git commit -am "fix: always release connection in pool"
git push

# 2. Container App rebuilds from GitHub (or manual: az containerapp update)
# 3. Wait for new revision rollout (~2 minutes)
# 4. Verify FAULT_MODE is still set
az containerapp show --resource-group my-rg --name demo-incident-fastapi \
    --query "properties.template.containers[0].env[?name=='FAULT_MODE'].value"
```

### Phase 4: Post-Mitigation Validation

**Timeline:** ~15 minutes

```bash
# 1. Collect response metrics with same concurrency as incident phase
python collect_response_metrics.py \
    --url https://your-app.azurecontainerapps.io \
    --requests 50 \
    --concurrency 10 \
    --label "post_mitigation_20260828"

# 2. Collect container evidence
python collect_container_evidence.py \
    --resource-group my-rg \
    --container-app demo-incident-fastapi \
    --workspace-id <workspace-id> \
    --start-time $(date -u +'%Y-%m-%dT%H:%M:%SZ' -d '15 minutes ago') \
    --end-time $(date -u +'%Y-%m-%dT%H:%M:%SZ') \
    --label "post_mitigation_20260828"
```

**Validation:**
- All 50 requests return 200 OK (no 503 errors despite FAULT_MODE=pool_leak)
- Latency percentiles < 500 ms (no timeout accumulation)
- Container logs show successful /transactions queries without "No hay conexiones"
- No scale-up events needed
- CPU/memory minimal and stable

## Evidence Summary Template

After collection, create `EVIDENCE_SUMMARY.md`:

```markdown
# Incident Evidence Summary

## Window 1: Healthy Baseline
- **UTC Range:** 2026-08-28T00:00:00Z - 2026-08-28T02:00:00Z
- **Duration:** 120 minutes
- **Evidence Files:**
  - response_metrics: `evidence_healthy_baseline_*.json`
  - container_logs: `evidence_healthy_baseline_container.json`
- **Key Metrics:**
  - p99 Latency: 150 ms
  - HTTP 200: 100% (50/50 requests)
  - Errors: 0

## Window 2: Incident (FAULT_MODE=pool_leak)
- **UTC Range:** 2026-08-28T03:00:00Z - 2026-08-28T06:00:00Z
- **Duration:** 180 minutes
- **Evidence Files:**
  - response_metrics: `evidence_incident_20260828_detailed.json`
  - container_logs: `evidence_incident_20260828_container.json`
- **Key Metrics:**
  - p99 Latency: 2850 ms (approaching 3-second timeout)
  - HTTP 200: 10% (5/50 requests)
  - HTTP 503: 90% (45/50 requests)
  - Scale-up events: 8 (replica: 1 → 3)

## Correlation: Root Cause
Connection pool of size 5 exhausted after first 5 concurrent requests in mode pool_leak.
Each acquired connection held indefinitely (not released). Subsequent requests timeout
after 3 seconds and return 503.

## Window 3: Post-Mitigation (FAULT_MODE=pool_leak, but connection ALWAYS released)
- **UTC Range:** 2026-08-28T07:00:00Z - 2026-08-28T08:00:00Z
- **Duration:** 60 minutes
- **Evidence Files:**
  - response_metrics: `evidence_post_mitigation_20260828_detailed.json`
  - container_logs: `evidence_post_mitigation_20260828_container.json`
- **Key Metrics:**
  - p99 Latency: 120 ms
  - HTTP 200: 100% (50/50 requests)
  - Errors: 0

## Completion Checklist (Issue #5)

- [x] Incident window and healthy baseline defined in UTC
- [x] Route-level latency percentiles captured with sample counts
- [x] Response-status breakdown (200, 503) captured
- [x] Container App logs and scale/capacity metrics attached
- [x] 5 slow requests + 5 failed requests have trace/correlation evidence
- [x] Configuration/deployment timeline correlated with impact
- [x] Post-mitigation measurement using identical workload parameters
```

## Integration with Application Insights

To export traces to Azure Application Insights:

```python
from app.tracer import get_tracer, configure_tracing_logging
import logging

configure_tracing_logging()
tracer = get_tracer("transactions_service")

# Traces now output structured JSON that Application Insights can ingest via:
# - Direct SDK integration
# - Log Analytics workspace ingestion
# - Custom log forwarding
```

## Verification and Validation

**Run included test suite to validate collected evidence:**

```bash
# Tests verify response codes and latency under concurrent load
pytest tests/test_transactions.py::test_pool_no_se_agota_bajo_carga_concurrente -v

# With FAULT_MODE=none: should PASS (all 200 responses)
# With FAULT_MODE=pool_leak (before fix): should FAIL (503s present)
# With FAULT_MODE=pool_leak (after fix): should PASS (all 200 responses)
```

## Troubleshooting

### Azure CLI Errors

**Error:** "az: command not found"

**Fix:**
```bash
# Install Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
az login
```

**Error:** "Authorization failed"

**Fix:**
```bash
# Verify subscription
az account show
# Switch if needed
az account set --subscription <subscription-id>
```

### Missing Log Analytics Data

**Error:** No logs returned from Container App

**Fix:**
1. Verify Log Analytics Workspace is configured in Container App:
   ```bash
   az containerapp show --resource-group my-rg --name demo-incident-fastapi \
       --query "properties.logAnalyticsConfiguration"
   ```

2. Ensure queries ran within data retention window (default 30 days)

3. Try explicit Kusto query in Portal: Log Analytics → Logs → paste KQL

### Response Metrics Timeout

**Error:** "Timeout after 15s" in `collect_response_metrics.py`

**Fix:**
- Increase service timeout or network latency
- Verify service is accessible: `curl -I https://your-app.azurecontainerapps.io/health`
- Check Container App revision status: `az containerapp revision list ...`

## References

- **Issue #5:** https://github.com/zairachavarin-k/demo_micro_test/issues/5
- **App Source:** `app/db_pool.py` (connection pool simulation)
- **Bug Details:** `app/db_pool.py:71` (pool_leak mode omits connection release)
- **Tests:** `tests/test_transactions.py::test_pool_no_se_agota_bajo_carga_concurrente`
