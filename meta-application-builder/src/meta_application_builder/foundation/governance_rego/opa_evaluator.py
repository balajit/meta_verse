# file name: /meta-application-builder/src/meta_application_builder/foundation/governance_rego/opa_evaluator.py

from __future__ import annotations

import asyncio
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


class OPAMode(str, Enum):
    HTTP = "http"
    LOCAL_FALLBACK = "local_fallback"


class OPAEvaluationError(Exception):
    """Raised when OPA evaluation encounters an unrecoverable failure."""
    pass


class OPAEvaluator:
    """OPA Evaluator supporting persistent HTTP sidecar connections with fallback logic."""

    def __init__(
            self,
            opa_url: str = "http://localhost:8181",
            policy_uri: str = "policies/governance.rego",
            timeout_seconds: float = 5.0,
    ) -> None:
        self.opa_url = opa_url.rstrip("/")
        self.policy_uri = policy_uri
        self.timeout_seconds = timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> OPAEvaluator:
        self._client = httpx.AsyncClient(
            base_url=self.opa_url,
            timeout=self.timeout_seconds,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _build_opa_endpoint(self, policy_path: str) -> str:
        """Normalizes file paths or Rego package rules to OPA REST endpoints."""
        if policy_path.endswith(".rego"):
            policy_name = Path(policy_path).stem
            return f"/v1/data/{policy_name}/allow"

        clean_path = policy_path.strip("/").replace(".", "/")
        return f"/v1/data/{clean_path}"

    async def evaluate(
            self,
            policy_uri: Optional[str] = None,
            input_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Evaluates payload against Rego policy via persistent HTTP client or fallback."""
        target_policy = policy_uri or self.policy_uri
        payload = input_data or {}

        # Resolves path using the endpoint helper
        url = self._build_opa_endpoint(target_policy)

        # Auto-initialize transient client if context manager (__aenter__) wasn't used
        client = self._client or httpx.AsyncClient(base_url=self.opa_url, timeout=self.timeout_seconds)

        try:
            response = await client.post(url, json={"input": payload})
            if response.status_code == 200:
                data = response.json()
                result = data.get("result", False)
                if isinstance(result, bool):
                    return result
                if isinstance(result, dict):
                    return bool(result.get("allow", True))
                return bool(result)
        except Exception as err:
            logger.warning(
                "opa_http_query_failed_using_fallback",
                error=str(err),
                policy=target_policy,
                endpoint=url,
            )
        finally:
            if self._client is None:
                await client.aclose()

        return self._fallback_evaluate(payload)

    def _fallback_evaluate(self, payload: Dict[str, Any]) -> bool:
        """Local structural safety check executed when the OPA daemon is unreachable."""
        if not payload:
            logger.warning("opa_fallback_rejected_empty_payload")
            return False

        model_name = payload.get("model_name")
        fields = payload.get("fields")

        if not model_name or not isinstance(fields, list):
            logger.warning("opa_fallback_missing_required_fields", model_name=model_name)
            return False

        metadata = payload.get("metadata", {})
        if metadata.get("tier") == "forbidden":
            logger.warning("opa_fallback_rejected_forbidden_tier", model_name=model_name)
            return False

        logger.info("opa_fallback_evaluation_passed", model_name=model_name)
        return True