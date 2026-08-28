"""
Container App metrics and configuration evidence collection.

Queries Azure Container App for:
  • Metrics: CPU, memory, request count, response status breakdown
  • Logs: application console logs with /transactions requests, 503 errors, timeouts
  • Configuration: image, environment vars, resource limits, scale rules
  • Deployment history: revision timeline and traffic weights

This script requires Azure CLI (az) and Log Analytics query credentials.

Usage:
    python collect_container_evidence.py \
        --resource-group my-rg \
        --container-app demo-incident-fastapi \
        --workspace-id <log-analytics-workspace-id> \
        --start-time 2026-08-28T00:00:00Z \
        --end-time 2026-08-28T06:00:00Z \
        --label "incident_window_20260828"
"""

import argparse
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


class ContainerEvidenceCollector:
    """Collects Azure Container App evidence for incident analysis."""

    def __init__(
        self,
        resource_group: str,
        container_app: str,
        workspace_id: Optional[str] = None,
        label: str = "evidence",
    ):
        self.resource_group = resource_group
        self.container_app = container_app
        self.workspace_id = workspace_id
        self.label = label
        self.evidence = {}

    def run_command(self, cmd: List[str]) -> Optional[str]:
        """Run Azure CLI command and return output."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"⚠️  Command failed: {' '.join(cmd)}")
            print(f"    Error: {e.stderr}")
            return None
        except FileNotFoundError:
            print("❌ Azure CLI not found. Install with: az login")
            return None

    def collect_configuration(self) -> None:
        """Collect Container App configuration."""
        print(f"\n📋 Collecting configuration for {self.container_app}...")
        
        cmd = [
            "az", "containerapp", "show",
            "--resource-group", self.resource_group,
            "--name", self.container_app,
            "--query", "{image:properties.template.containers[0].image, "
                       "env:properties.template.containers[0].env, "
                       "resources:properties.template.containers[0].resources, "
                       "scale:properties.template.scale, "
                       "revision:properties.latestRevisionName, "
                       "traffic:properties.template.revisionSuffix}",
            "--output", "json",
        ]
        
        output = self.run_command(cmd)
        if output:
            self.evidence["configuration"] = json.loads(output)
            print("   ✅ Configuration collected")

    def collect_revisions(self) -> None:
        """Collect Container App revision history."""
        print(f"\n🔄 Collecting revision history...")
        
        cmd = [
            "az", "containerapp", "revision", "list",
            "--resource-group", self.resource_group,
            "--name", self.container_app,
            "--query", "sort_by([].{name:name, "
                               "createdTime:properties.createdTime, "
                               "active:properties.active, "
                               "traffic:properties.trafficWeight, "
                               "image:properties.template.containers[0].image}, "
                       "&createdTime)",
            "--output", "json",
        ]
        
        output = self.run_command(cmd)
        if output:
            self.evidence["revisions"] = json.loads(output)
            print(f"   ✅ {len(self.evidence['revisions'])} revisions found")

    def collect_logs(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Collect application console logs from Log Analytics."""
        if not self.workspace_id:
            print("\n⚠️  Skipping logs: --workspace-id not provided")
            return
        
        print(f"\n📝 Querying logs ({start_time} - {end_time})...")
        
        # KQL query for /transactions requests, 503s, and timeouts
        kql_query = """
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "demo-incident-fastapi"
| where TimeGenerated between (datetime('{start}') .. datetime('{end}'))
| where Log_s has "/transactions" or Log_s has "No hay conexiones" or Log_s has "503"
| project TimeGenerated, 
          RevisionName=RevisionName_s, 
          ContainerName=ContainerName_s, 
          Log=Log_s
| order by TimeGenerated asc
""".format(
            start=start_time.isoformat() + "Z",
            end=end_time.isoformat() + "Z",
        )
        
        # Escape quotes for shell
        kql_query_escaped = kql_query.replace('"', '\\"')
        
        cmd = [
            "az", "monitor", "log-analytics", "query",
            "--workspace", self.workspace_id,
            "--analytics-query", kql_query_escaped,
            "--output", "json",
        ]
        
        output = self.run_command(cmd)
        if output:
            try:
                data = json.loads(output)
                self.evidence["logs"] = data.get("tables", [{}])[0].get("rows", [])
                print(f"   ✅ {len(self.evidence['logs'])} log entries found")
            except json.JSONDecodeError:
                print("   ⚠️  Could not parse log response")

    def collect_metrics(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Collect Container App metrics (CPU, memory, requests)."""
        print(f"\n📊 Querying metrics ({start_time} - {end_time})...")
        
        metrics = [
            "CpuUsage",
            "MemoryUsage",
            "Replicas",
            "Requests",
        ]
        
        for metric in metrics:
            cmd = [
                "az", "monitor", "metrics", "list",
                "--resource", f"/subscriptions/{{subscription-id}}"
                              f"/resourceGroups/{self.resource_group}"
                              f"/providers/Microsoft.App/containerApps/{self.container_app}",
                "--metric", metric,
                "--start-time", start_time.isoformat() + "Z",
                "--end-time", end_time.isoformat() + "Z",
                "--interval", "PT1M",
                "--output", "json",
            ]
            
            output = self.run_command(cmd)
            if output:
                try:
                    self.evidence[f"metrics_{metric}"] = json.loads(output)
                except json.JSONDecodeError:
                    pass
        
        print(f"   ✅ Metrics collected")

    def collect_activity_log(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        """Collect Activity Log entries for the Container App."""
        print(f"\n📅 Querying Activity Log ({start_time} - {end_time})...")
        
        cmd = [
            "az", "monitor", "activity-log", "list",
            "--resource-group", self.resource_group,
            "--resource-type", "Microsoft.App/containerApps",
            "--resource", self.container_app,
            "--start-time", start_time.isoformat() + "Z",
            "--end-time", end_time.isoformat() + "Z",
            "--query", "[].{eventTimestamp:eventTimestamp, "
                         "operationName:operationName.value, "
                         "resourceGroup:resourceGroup, "
                         "status:status.value, "
                         "correlationId:correlationId}",
            "--output", "json",
        ]
        
        output = self.run_command(cmd)
        if output:
            self.evidence["activity_log"] = json.loads(output)
            print(f"   ✅ {len(self.evidence['activity_log'])} activity entries found")

    def collect(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> None:
        """Collect all evidence."""
        if not start_time:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=1)
        elif not end_time:
            end_time = datetime.utcnow()
        
        print(f"\n{'='*70}")
        print(f"Container App Evidence Collection: {self.container_app}")
        print(f"{'='*70}")
        
        self.collect_configuration()
        self.collect_revisions()
        self.collect_logs(start_time, end_time)
        self.collect_metrics(start_time, end_time)
        self.collect_activity_log(start_time, end_time)

    def save(self) -> Path:
        """Save collected evidence to JSON file."""
        output_file = Path(f"evidence_{self.label}_container.json")
        with open(output_file, "w") as f:
            json.dump(self.evidence, f, indent=2)
        print(f"\n💾 Container evidence saved: {output_file}\n")
        return output_file


def main():
    parser = argparse.ArgumentParser(
        description="Collect Container App evidence for incident analysis"
    )
    parser.add_argument(
        "--resource-group",
        required=True,
        help="Azure resource group name"
    )
    parser.add_argument(
        "--container-app",
        required=True,
        help="Container App name"
    )
    parser.add_argument(
        "--workspace-id",
        help="Log Analytics Workspace ID (for log collection)"
    )
    parser.add_argument(
        "--start-time",
        help="Start time for metrics/logs (ISO format: 2026-08-28T00:00:00Z)"
    )
    parser.add_argument(
        "--end-time",
        help="End time for metrics/logs (ISO format, default: now)"
    )
    parser.add_argument(
        "--label",
        default="evidence",
        help="Label for evidence set"
    )
    
    args = parser.parse_args()
    
    start_time = None
    if args.start_time:
        start_time = datetime.fromisoformat(args.start_time.replace("Z", "+00:00"))
    
    end_time = None
    if args.end_time:
        end_time = datetime.fromisoformat(args.end_time.replace("Z", "+00:00"))
    
    collector = ContainerEvidenceCollector(
        args.resource_group,
        args.container_app,
        args.workspace_id,
        args.label,
    )
    collector.collect(start_time, end_time)
    collector.save()


if __name__ == "__main__":
    main()
