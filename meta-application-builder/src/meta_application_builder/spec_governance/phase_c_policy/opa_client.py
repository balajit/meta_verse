from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from meta_application_builder.foundation.security_context.identity import (
    IdentityContextManager,
    UnauthenticatedContextError,
)
from meta_application_builder.spec_governance.schemas.det_schema import (
    DomainEntityTemplate,
)
from meta_application_builder.spec_governance.schemas.rfc7807_error import (
    ProblemDetails,
    ValidationErrorDetail,
)

logger = logging.getLogger("meta_application_builder.spec_governance.opa_client")


class GovernancePolicyError(Exception):
    """Raised when OPA evaluation returns an explicit policy rejection or connection timeout."""

    def __init__(self, problem: ProblemDetails) -> None:
        super().__init__(problem.detail)
        self.problem = problem


class OPAGovernanceClient:
    """Phase C Validator: High-throughput HTTP client utilizing connection pooling and strict timeouts."""

    def __init__(
        self,
        opa_endpoint_url: str,
        timeout_seconds: float = 2.0,
        max_keepalive_connections: int = 20,
        max_connections: int = 100,
    ) -> None:
        self._opa_url = opa_endpoint_url
        self._limits = httpx.Limits(
            max_keepalive_connections=max_keepalive_connections,
            max_connections=max_connections,
        )
        self._timeout = httpx.Timeout(timeout_seconds, connect=1.0)
        self._client = httpx.AsyncClient(limits=self._limits, timeout=self._timeout)

    def _build_5tuple_payload(
        self,
        principal: str,
        tenant: str,
        action: str,
        resource_urn: str,
        environment: str,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Constructs canonical 5-tuple authorization evaluation payload."""
        return {
            "input": {
                "principal": principal,
                "tenant": tenant,
                "action": action,
                "resource_urn": resource_urn,
                "environment": environment,
                "context": extra_context or {},
            }
        }

    async def evaluate_authorization(
        self,
        action: str,
        resource_urn: str,
        instance_uri: str,
        environment: str = "production",
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Enforces fine-grained authorization policy evaluation using a 5-tuple:
        (principal, tenant, action, resource_urn, environment).
        """
        try:
            tenant_id = IdentityContextManager.get_current_tenant_id()
            principal = IdentityContextManager.get_current_principal()
        except UnauthenticatedContextError as e:
            logger.error("OPA evaluation rejected: missing active security context.")
            problem = ProblemDetails.create(
                status=401,
                title="Unauthorized Security Context",
                detail="Security context claims missing during OPA policy evaluation.",
                instance=instance_uri,
                invalid_params=[ValidationErrorDetail(field_path="security_context", code="MBR-009", message=str(e))],
            )
            raise GovernancePolicyError(problem) from e

        eval_payload = self._build_5tuple_payload(
            principal=principal,
            tenant=tenant_id,
            action=action,
            resource_urn=resource_urn,
            environment=environment,
            extra_context=extra_context,
        )

        logger.info(
            "Calling OPA authorization endpoint '%s' for principal='%s', tenant='%s', action='%s', resource_urn='%s'",
            self._opa_url, principal, tenant_id, action, resource_urn
        )

        try:
            response = await self._client.post(self._opa_url, json=eval_payload)
            response.raise_for_status()
            res_data = response.json()
            result = res_data.get("result", {})

            allow = result.get("allow", False)
            reasons = result.get("reasons", [])

            if not allow:
                logger.warning(
                    "OPA policy denied authorization for principal '%s' on resource '%s': %s",
                    principal, resource_urn, reasons
                )
                invalid_params = [
                    ValidationErrorDetail(field_path="policy", code="MBR-010", message=reason)
                    for reason in reasons
                ]
                problem = ProblemDetails.create(
                    status=403,
                    title="Governance Policy Violation",
                    detail="Action violates enterprise fine-grained access governance policies evaluated by OPA.",
                    instance=instance_uri,
                    invalid_params=invalid_params or [ValidationErrorDetail(field_path="policy", code="MBR-010", message="Policy denied authorization.")],
                )
                raise GovernancePolicyError(problem)

            logger.info("OPA policy evaluation allowed action '%s' on resource '%s'", action, resource_urn)
            return True

        except httpx.TimeoutException as timeout_exc:
            logger.error("OPA sidecar evaluation timed out after %s seconds: %s", self._timeout.read, str(timeout_exc))
            problem = ProblemDetails.create(
                status=504,
                title="Policy Engine Gateway Timeout",
                detail="Open Policy Agent sidecar failed to respond within the configured 2.0 second limit.",
                instance=instance_uri,
                invalid_params=[ValidationErrorDetail(field_path="opa_client", code="MBR-012", message="Policy evaluation timeout.")],
            )
            raise GovernancePolicyError(problem) from timeout_exc

        except httpx.HTTPError as http_exc:
            logger.error("Communication failure with OPA sidecar engine: %s", str(http_exc))
            problem = ProblemDetails.create(
                status=503,
                title="Policy Engine Unavailable",
                detail="Unable to contact Open Policy Agent sidecar service.",
                instance=instance_uri,
                invalid_params=[ValidationErrorDetail(field_path="opa_client", code="MBR-011", message=str(http_exc))],
            )
            raise GovernancePolicyError(problem) from http_exc

    async def evaluate_specification(
        self,
        spec: DomainEntityTemplate,
        instance_uri: str,
        environment: str = "production",
    ) -> bool:
        """Submits context claims and specification payload to sidecar OPA policy server using 5-tuple evaluation."""
        return await self.evaluate_authorization(
            action="VALIDATE_SPECIFICATION",
            resource_urn=spec.urn,
            instance_uri=instance_uri,
            environment=environment,
            extra_context={"specification": spec.model_dump(mode="json")},
        )

    async def close(self) -> None:
        """Closes HTTP client session."""
        await self._client.aclose()