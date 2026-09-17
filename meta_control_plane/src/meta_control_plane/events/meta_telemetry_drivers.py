import logging
from typing import Any, Dict, List
from pydantic import BaseModel, Field
import httpx

logger = logging.getLogger(__name__)


class TelemetryContext(BaseModel):
    run_id: str
    step_id: str
    stack_trace: List[str]
    resource_metrics: Dict[str, Any]
    graph_state: Dict[str, Any]
    input_artifacts: Dict[str, Any]


class ManifestTelemetryDriver:
    """Fetches execution context, stack traces, and metrics via inspect_manifest API[cite: 5]."""

    def __init__(self, control_plane_base_url: str = "http://localhost:8000"):
        self.base_url = control_plane_base_url.rstrip("/")

    async def fetch_telemetry_context(self, run_id: str, step_id: str, depth: int = 2) -> TelemetryContext:
        """Calls inspect_manifest endpoint to gather telemetry prior to failure diagnosis[cite: 5]."""
        url = f"{self.base_url}/api/v1/manifest/inspect"
        payload = {"run_id": run_id, "step_id": step_id, "depth": depth}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        return TelemetryContext(
            run_id=data["run_id"],
            step_id=data["step_id"],
            stack_trace=data.get("execution_logs", []),
            resource_metrics=data.get("telemetry_metrics", {}),
            graph_state=data.get("graph_state", {}),
            input_artifacts=data.get("artifacts", {}),
        )