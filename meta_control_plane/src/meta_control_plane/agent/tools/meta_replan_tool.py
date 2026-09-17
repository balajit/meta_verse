import logging
import httpx
from meta_control_plane.agent.tools.meta_retry_tool import ToolExecutionResult
from meta_control_plane.api.schemas.meta_mutation_schemas import MutationSpec

logger = logging.getLogger(__name__)


class ReplanDAGTool:
    """Agent tool wrapper for invoking dynamic DAG mutation specifications[cite: 7]."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")

    async def run(self, run_id: str, failed_step_id: str, mutation_spec: MutationSpec) -> ToolExecutionResult:
        """Invokes the /replan control plane graph mutation endpoint[cite: 7]."""
        url = f"{self.base_url}/api/v1/graph/replan"
        payload = {
            "run_id": run_id,
            "failed_step_id": failed_step_id,
            "mutation_spec": mutation_spec.model_dump(mode="json"),
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            return ToolExecutionResult(
                success=resp.status_code == 200,
                status_code=resp.status_code,
                payload=resp.json(),
            )