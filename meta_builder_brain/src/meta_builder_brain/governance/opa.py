"""Open Policy Agent sidecar client with HTTP error handling and validation exceptions."""

import httpx
from typing import Dict, Any, cast
from meta_telemetry import trace_span
from meta_builder_brain.config import BrainSettings
from meta_builder_brain.exceptions import (
    GovernancePolicyViolationError,
    OPAPolicyValidationError,
    OPAServiceUnavailableError,
)

__all__ = [
    "OPAEvaluator",
    "OPAPolicyValidationError",
    "GovernancePolicyViolationError",
    "OPAServiceUnavailableError",
]


class OPAEvaluator:
    """HTTP sidecar client for evaluating Rego policy contracts."""

    def __init__(self, settings: BrainSettings) -> None:
        self.opa_url = settings.opa_sidecar_url.rstrip("/")

    @trace_span(name="opa.evaluate_policy")
    async def evaluate_policy(self, policy_path: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Posts evaluation payload to local OPA sidecar endpoint."""
        endpoint = f"{self.opa_url}/{policy_path.lstrip('/')}"

        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.post(endpoint, json={"input": input_data})
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    result = payload.get("result", {})
                    if isinstance(result, dict):
                        return cast(Dict[str, Any], result)
                return {}
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                raise OPAServiceUnavailableError(
                    f"OPA sidecar service unreachable at '{endpoint}': {exc}"
                ) from exc
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500:
                    raise OPAServiceUnavailableError(
                        f"OPA sidecar server error HTTP {exc.response.status_code}: {exc}"
                    ) from exc
                raise OPAServiceUnavailableError(
                    f"OPA policy endpoint returned HTTP error {exc.response.status_code}: {exc}"
                ) from exc
            except httpx.HTTPError as exc:
                raise OPAServiceUnavailableError(
                    f"OPA evaluation request encountered transport error: {exc}"
                ) from exc

    @trace_span(name="opa.validate_component_governance")
    async def validate_component_governance(self, component_urn: str, payload: Dict[str, Any]) -> bool:
        """Validates component specification against governance rules."""
        input_data = {"urn": component_urn, "payload": payload}
        result = await self.evaluate_policy("component/governance", input_data)

        allowed = result.get("allow", False)
        if not allowed:
            reasons = result.get("reasons", ["Governance policy constraints violated"])
            raise OPAPolicyValidationError(
                f"Component '{component_urn}' governance check failed: {', '.join(reasons)}",
                payload={"urn": component_urn, "reasons": reasons},
            )
        return True