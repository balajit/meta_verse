import logging
from typing import Any, Dict, Optional
import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class NotificationPayload(BaseModel):
    run_id: str
    step_id: str
    reason: str
    failure_category: str
    token_diagnostic_context: Dict[str, Any] = Field(..., description="Authentication token diagnostic metadata[cite: 6, 8]")
    stack_trace: Optional[str] = None


class OpsNotificationManager:
    """Dispatches human escalation alerts with token context directly to Ops channels[cite: 6, 8]."""

    def __init__(self, webhook_url: str = "http://localhost:9000/hooks/ops-alerts"):
        self.webhook_url = webhook_url

    async def dispatch_ops_alert(
        self,
        run_id: str,
        step_id: str,
        reason: str,
        failure_category: str,
        token_context: Optional[Dict[str, Any]] = None,
        stack_trace: Optional[str] = None,
    ) -> bool:
        """Sends instant notification payload with token diagnostic context to Ops endpoints[cite: 6, 8]."""
        auth_diagnostic = token_context or {
            "token_id_prefix": "tok_sec_***_4f92",
            "issuer": "meta-control-plane-auth",
            "missing_permissions": ["execution:retry", "graph:mutate"],
            "timestamp": "2026-08-27T12:49:07Z",
        }

        payload = NotificationPayload(
            run_id=run_id,
            step_id=step_id,
            reason=reason,
            failure_category=failure_category,
            token_diagnostic_context=auth_diagnostic,
            stack_trace=stack_trace,
        )

        logger.warning(f"Dispatching instant Ops alert for step {step_id}: {reason}[cite: 8]")

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(self.webhook_url, json=payload.model_dump(mode="json"))
                resp.raise_for_status()
                return True
        except Exception as exc:
            logger.error(f"Failed to deliver Ops alert notification: {exc}", exc_info=True)
            return False