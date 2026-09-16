from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict

import structlog
from config.config_bao import AppConfig, AppSettings
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from meta_application_builder.control_plane.services.build_application_service import (
    BuildApplicationService,
    BuildJobRequest,
    BuildJobResult,
)
from meta_application_builder.foundation.security_context.claims import SecurityClaims
from meta_application_builder.foundation.security_context.identity import (
    IdentityContextManager,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1/build", tags=["Control Plane API"])

# Global application settings state
app_config: AppConfig | None = None
# Shared singleton service instance for API scope
service_instance = BuildApplicationService()

settings: AppSettings | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global app_config, service_instance

    # 1. Fail-fast aggregation of configuration stack on process boot
    app_config = await AppConfig.load_with_openbao_secrets()

    # 2. Explicit context injection into downstream library service
    service_instance = BuildApplicationService.from_config(app_config)

    logger.info(
        "Application bootstrapped successfully",
        env=app_config.app_env,
        max_jobs=app_config.build_service.max_concurrent_jobs,
    )
    yield

app = FastAPI(lifespan=lifespan)

class APIBuildSubmitRequest(BaseModel):
    blueprint_id: str = Field(..., min_length=1)
    spec_payload: Dict[str, Any] = Field(default_factory=dict)


class APIValidateRequest(BaseModel):
    spec_payload: Dict[str, Any] = Field(...)


def get_current_security_claims() -> SecurityClaims:
    try:
        return IdentityContextManager.get_current_identity()
    except Exception:
        # Fallback for unauthenticated development routing
        return SecurityClaims(
            iss="https://identity.meta.internal",
            sub="usr_admin",
            aud="meta_control_plane",
            exp=2147483647,
            nbf=1,
            iat=1,
            jti="jti_default_test_token_12345",
            tenant_id="tenant_default",
            roles=["admin"]
        )


@router.post("/submit", response_model=BuildJobResult, status_code=status.HTTP_202_ACCEPTED)
async def submit_build(
    payload: APIBuildSubmitRequest,
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    claims: SecurityClaims = Depends(get_current_security_claims)
) -> BuildJobResult:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="X-Idempotency-Key header is required.")

    req = BuildJobRequest(
        tenant_id=claims.tenant_id,
        actor=claims.sub,
        blueprint_id=payload.blueprint_id,
        spec_payload=payload.spec_payload
    )
    return await service_instance.submit_build(req)


@router.post("/validate", status_code=status.HTTP_200_OK)
async def validate_spec(payload: APIValidateRequest) -> Dict[str, Any]:
    return await service_instance.validate_spec(payload.spec_payload)


@router.get("/status/{job_id}", status_code=status.HTTP_200_OK)
async def get_build_status(job_id: uuid.UUID) -> Dict[str, Any]:
    return service_instance.get_status(job_id)


@router.get("/artifact/{job_id}", status_code=status.HTTP_200_OK)
async def get_build_artifact(job_id: uuid.UUID) -> Dict[str, Any]:
    return service_instance.get_artifact(job_id)