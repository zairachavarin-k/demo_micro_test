"""
Evidence manifest and summary for incident analysis.

This module defines the structure for evidence collection results,
enabling correlation across multiple data sources (metrics, logs, traces).

Usage:
    manifest = EvidenceManifest("incident_window_20260828")
    manifest.add_metrics("response_times", "evidence_incident_response.json")
    manifest.add_logs("container_logs", "evidence_incident_container.json")
    manifest.save()
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class EvidenceSource:
    """Reference to a single evidence file or data source."""
    
    name: str
    category: str  # "metrics", "logs", "traces", "configuration"
    path: Optional[str] = None
    url: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    description: Optional[str] = None


@dataclass
class EvidenceWindow:
    """Time window for evidence collection."""
    
    label: str
    start_utc: str
    end_utc: str
    duration_minutes: int
    description: Optional[str] = None


@dataclass
class EvidenceManifest:
    """Master manifest correlating all evidence sources."""
    
    manifest_id: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    incident_window: Optional[EvidenceWindow] = None
    baseline_window: Optional[EvidenceWindow] = None
    mitigation_window: Optional[EvidenceWindow] = None
    
    sources: Dict[str, List[EvidenceSource]] = field(default_factory=lambda: {
        "metrics": [],
        "logs": [],
        "traces": [],
        "configuration": [],
    })
    
    completion_checklist: Dict[str, bool] = field(default_factory=lambda: {
        "incident_and_baseline_defined": False,
        "latency_percentiles_captured": False,
        "http_status_rates_captured": False,
        "container_logs_attached": False,
        "scale_capacity_metrics_attached": False,
        "slow_requests_traced": False,
        "failed_requests_traced": False,
        "configuration_timeline_attached": False,
        "post_mitigation_measured": False,
    })
    
    findings: Dict[str, str] = field(default_factory=dict)
    
    def add_source(
        self,
        category: str,
        name: str,
        path: Optional[str] = None,
        url: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        """Add an evidence source to the manifest."""
        source = EvidenceSource(
            name=name,
            category=category,
            path=path,
            url=url,
            description=description,
        )
        if category in self.sources:
            self.sources[category].append(source)
    
    def add_finding(self, key: str, value: str) -> None:
        """Record a finding from evidence analysis."""
        self.findings[key] = value
    
    def mark_complete(self, item: str) -> None:
        """Mark a completion criterion as done."""
        if item in self.completion_checklist:
            self.completion_checklist[item] = True
    
    def save(self, output_file: Optional[Path] = None) -> Path:
        """Save manifest to JSON file."""
        if not output_file:
            output_file = Path(f"evidence_manifest_{self.manifest_id}.json")
        
        with open(output_file, "w") as f:
            json.dump(asdict(self), f, indent=2)
        
        print(f"📄 Manifest saved: {output_file}")
        return output_file
    
    def print_status(self) -> None:
        """Print completion status."""
        completed = sum(self.completion_checklist.values())
        total = len(self.completion_checklist)
        
        print(f"\n{'='*70}")
        print(f"Evidence Collection Status: {self.manifest_id}")
        print(f"{'='*70}")
        print(f"Completion: {completed}/{total} criteria")
        print()
        
        for criterion, done in self.completion_checklist.items():
            status = "✅" if done else "⏳"
            print(f"  {status} {criterion}")
        
        if self.findings:
            print(f"\nFindings:")
            for key, value in self.findings.items():
                print(f"  • {key}: {value}")
        
        print(f"{'='*70}\n")


# Template evidence structures for documentation
EVIDENCE_TEMPLATE = {
    "metrics_collection": {
        "description": "Request, availability, and capacity metrics at 1-min granularity",
        "dimensions": [
            "timestamp (UTC)",
            "environment",
            "revision_name",
            "route (/transactions)",
            "status_code (200, 503, etc.)",
        ],
        "measurements": [
            "request_count",
            "requests_per_second",
            "concurrent_requests",
            "http_200_rate",
            "http_503_rate",
            "replica_count",
            "cpu_percent_per_replica",
            "memory_mb_per_replica",
            "container_restarts",
        ],
    },
    "response_time_collection": {
        "description": "Per-request latency measurements with correlation",
        "per_request_fields": [
            "request_id (UUID)",
            "correlation_id (UUID)",
            "utc_timestamp",
            "route",
            "status_code",
            "total_elapsed_ms",
            "server_reported_elapsed_ms",
        ],
        "statistics": [
            "p50_latency_ms",
            "p90_latency_ms",
            "p95_latency_ms",
            "p99_latency_ms",
            "max_latency_ms",
            "mean_latency_ms",
            "stdev_latency_ms",
            "sample_count",
            "throughput_rps",
        ],
    },
    "container_logs_query": {
        "description": "Kusto query for /transactions, 503, and timeout logs",
        "kql": (
            "ContainerAppConsoleLogs_CL\n"
            "| where ContainerAppName_s == 'demo-incident-fastapi'\n"
            "| where Log_s has '/transactions' or Log_s has 'No hay conexiones' or Log_s has '503'\n"
            "| project TimeGenerated, RevisionName_s, ContainerName_s, Log_s\n"
            "| order by TimeGenerated asc"
        ),
        "required_fields": [
            "TimeGenerated",
            "ContainerAppName_s",
            "RevisionName_s",
            "ContainerName_s",
            "Log_s",
        ],
        "context_window": "5 minutes before and after first slow/failed request",
    },
    "trace_sample_selection": {
        "description": "Criteria for selecting representative traces",
        "slow_requests": "5 requests exceeding p99 latency (should approach 3s timeout)",
        "failed_requests": "5 representative 503 responses after pool exhaustion",
        "healthy_baseline": "5 successful requests from healthy period",
    },
    "configuration_evidence": {
        "description": "Container App state at incident time",
        "items": [
            "revision (demo-incident-fastapi--000004)",
            "image digest/tag",
            "FAULT_MODE environment variable",
            "POOL_SIZE setting",
            "resource_limits (0.5 vCPU, 1 GiB)",
            "scale_rules (min=1, max=10, threshold=10 concurrent)",
            "traffic_weight for active revision",
            "Activity Log correlation ID (0d2a0b70-c48f-4f92-97de-fd90ca497c09)",
        ],
    },
}
