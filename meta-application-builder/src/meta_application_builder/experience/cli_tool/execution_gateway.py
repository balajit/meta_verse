# file name: meta_application_builder/cli/execution_gateway.py

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any, Dict, Optional

import httpx
import structlog

from meta_application_builder.control_plane.services.build_application_service import (
    BuildApplicationService,
    BuildJobRequest,
    BuildJobResult,
)

logger = structlog.get_logger(__name__)


class ExecutionMode(str, Enum):
    DIRECT = "direct"
    REMOTE = "remote"


class CLIExecutionGateway:
    """Gateway establishing operational behavior parity between direct in-process and remote HTTP modes."""

    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.DIRECT,
        service: Optional[BuildApplicationService] = None,
        remote_endpoint: Optional[str] = None,
        api_token: Optional[str] = None
    ) -> None:
        self.mode = mode
        self.service = service or BuildApplicationService()
        self.remote_endpoint = (remote_endpoint or "http://localhost:8000").rstrip("/")
        self.api_token = api_token or ""

    async def execute_build(
        self,
        tenant_id: str,
        actor: str,
        blueprint_id: str,
        spec_payload: Dict[str, Any],
        idempotency_key: str
    ) -> Dict[str, Any]:
        """Asynchronously dispatches build requests in direct or remote mode."""
        if self.mode == ExecutionMode.DIRECT:
            return await self._execute_direct(tenant_id, actor, blueprint_id, spec_payload)
        else:
            return await self._execute_remote(blueprint_id, spec_payload, idempotency_key)

    async def _execute_direct(
        self,
        tenant_id: str,
        actor: str,
        blueprint_id: str,
        spec_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.info("cli_executing_direct_mode", blueprint_id=blueprint_id)
        req = BuildJobRequest(
            tenant_id=tenant_id,
            actor=actor,
            blueprint_id=blueprint_id,
            spec_payload=spec_payload
        )
        res: BuildJobResult = await self.service.submit_build(req)
        return res.model_dump()

    async def _execute_remote(
        self,
        blueprint_id: str,
        spec_payload: Dict[str, Any],
        idempotency_key: str
    ) -> Dict[str, Any]:
        logger.info("cli_executing_remote_mode", endpoint=self.remote_endpoint)
        url = f"{self.remote_endpoint}/v1/build/submit"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "X-Idempotency-Key": idempotency_key
        }
        body = {
            "blueprint_id": blueprint_id,
            "spec_payload": spec_payload
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            return resp.json()