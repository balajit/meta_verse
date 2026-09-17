import logging
import uuid
import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ToolExecutionResult(BaseModel):
    success: bool
    status_code: int
    payload: dict


class RetryStepTool:
    """Agent tool wrapper for issuing isolated retry operations with idempotency keys[cite: 7]."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")

    async def run(self, run_id: str, step_id: str, override_config: dict) -> ToolExecutionResult:
        """Invokes the /retry control plane execution endpoint[cite: 7]."""
        url = f"{self.base_url}/api/v1/execution/retry"
        payload = {
            "run_id": run_id,
            "step_id": step_id,
            "idempotency_key": f"retry_{run_id}_{step_id}_{uuid.uuid4().hex[:8]}",
            "override_config": override_config,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            return ToolExecutionResult(
                success=resp.status_code == 202,
                status_code=resp.status_code,
                payload=resp.json(),
            )