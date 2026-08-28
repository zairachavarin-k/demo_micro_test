"""
Response-time evidence collection for performance degradation analysis.

Collects per-request metrics (latency, status code, correlation ID) with
configurable concurrency levels. Produces both detailed logs and statistical
summaries.

Usage:
    # Serial baseline (healthy state)
    python collect_response_metrics.py --url http://localhost:8000 \
        --requests 50 --concurrency 1 --label "healthy_serial"

    # Concurrent workload (stress test)
    python collect_response_metrics.py --url http://localhost:8000 \
        --requests 50 --concurrency 10 --label "incident_concurrent"

    # Post-mitigation validation
    python collect_response_metrics.py --url http://localhost:8000 \
        --requests 50 --concurrency 10 --label "post_mitigation"
"""

import argparse
import concurrent.futures
import json
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
import httpx
import uuid


class ResponseCollector:
    """Collects per-request response metrics."""

    def __init__(self, url: str, label: str):
        self.url = url
        self.label = label
        self.results: List[Dict] = []
        self.start_time = None
        self.end_time = None

    def make_request(self, request_num: int) -> Dict:
        """Execute a single request and record metrics."""
        request_id = str(uuid.uuid4())[:8]
        correlation_id = str(uuid.uuid4())[:8]
        
        start = time.time()
        status_code = None
        server_elapsed_ms = None
        error = None
        
        try:
            response = httpx.get(
                f"{self.url}/transactions",
                timeout=15.0,
                headers={
                    "X-Request-ID": request_id,
                    "X-Correlation-ID": correlation_id,
                },
            )
            status_code = response.status_code
            elapsed_ms = round((time.time() - start) * 1000, 1)
            
            # Extract server-reported elapsed time if available
            try:
                data = response.json()
                server_elapsed_ms = data.get("elapsed_ms", elapsed_ms)
            except Exception:
                server_elapsed_ms = elapsed_ms
                
        except httpx.TimeoutException:
            status_code = 504
            error = "Timeout after 15s"
            elapsed_ms = round((time.time() - start) * 1000, 1)
        except Exception as e:
            status_code = 0
            error = str(e)
            elapsed_ms = round((time.time() - start) * 1000, 1)
        
        result = {
            "request_num": request_num,
            "request_id": request_id,
            "correlation_id": correlation_id,
            "utc_timestamp": datetime.utcnow().isoformat() + "Z",
            "route": "/transactions",
            "status_code": status_code,
            "total_elapsed_ms": elapsed_ms,
            "server_elapsed_ms": server_elapsed_ms or elapsed_ms,
            "error": error,
        }
        
        self.results.append(result)
        return result

    def collect(self, num_requests: int, concurrency: int) -> None:
        """Collect metrics for num_requests with given concurrency level."""
        self.start_time = datetime.utcnow()
        
        print(f"\n📊 Collecting {num_requests} requests @ {concurrency} concurrency")
        print(f"   Label: {self.label}")
        print(f"   URL: {self.url}")
        print(f"   Start: {self.start_time.isoformat()}Z\n")
        
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=concurrency
        ) as executor:
            futures = [
                executor.submit(self.make_request, i) 
                for i in range(num_requests)
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"   ⚠️  Request failed: {e}")
        
        self.end_time = datetime.utcnow()

    def save_detailed_log(self) -> Path:
        """Save detailed per-request log to JSON file."""
        output_file = Path(f"evidence_{self.label}_detailed.json")
        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2)
        print(f"\n💾 Detailed log saved: {output_file}")
        return output_file

    def print_summary(self) -> None:
        """Print statistical summary."""
        if not self.results:
            print("❌ No results to summarize")
            return
        
        status_counts = {}
        error_counts = {}
        latencies = []
        
        for r in self.results:
            status = r["status_code"]
            status_counts[status] = status_counts.get(status, 0) + 1
            
            if r["error"]:
                error_counts[r["error"]] = error_counts.get(r["error"], 0) + 1
            
            latencies.append(r["total_elapsed_ms"])
        
        total = len(self.results)
        success = status_counts.get(200, 0)
        failures = total - success
        
        sorted_latencies = sorted(latencies)
        
        print("\n" + "=" * 70)
        print(f"SUMMARY: {self.label}")
        print("=" * 70)
        print(f"Window:          {self.start_time.isoformat()}Z - {self.end_time.isoformat()}Z")
        print(f"Total requests:  {total}")
        print(f"HTTP 200:        {success} ({100*success//total}%)")
        print(f"HTTP 503:        {status_counts.get(503, 0)}")
        print(f"Failures:        {failures} ({100*failures//total}%)")
        
        if error_counts:
            print(f"\nError breakdown:")
            for error, count in sorted(error_counts.items(), key=lambda x: -x[1]):
                print(f"  • {error}: {count}")
        
        if latencies:
            print(f"\nLatency percentiles:")
            print(f"  p50:             {sorted_latencies[len(sorted_latencies)//2]:.1f} ms")
            print(f"  p90:             {sorted_latencies[int(len(sorted_latencies)*0.9)]:.1f} ms")
            print(f"  p95:             {sorted_latencies[int(len(sorted_latencies)*0.95)]:.1f} ms")
            print(f"  p99:             {sorted_latencies[int(len(sorted_latencies)*0.99)]:.1f} ms")
            print(f"  max:             {max(latencies):.1f} ms")
            print(f"  mean:            {statistics.mean(latencies):.1f} ms")
            print(f"  stdev:           {statistics.stdev(latencies) if len(latencies) > 1 else 0:.1f} ms")
        
        print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Collect response-time evidence for performance degradation"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Service URL (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=50,
        help="Number of requests (default: 50)"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Concurrent workers (default: 10)"
    )
    parser.add_argument(
        "--label",
        default="test_run",
        help="Label for evidence set (default: test_run)"
    )
    
    args = parser.parse_args()
    
    collector = ResponseCollector(args.url, args.label)
    collector.collect(args.requests, args.concurrency)
    collector.print_summary()
    collector.save_detailed_log()


if __name__ == "__main__":
    main()
