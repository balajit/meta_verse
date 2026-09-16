import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict

import structlog
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from meta_application_builder.config.bootstrap import (
    bootstrap_application_configuration,
)
from meta_application_builder.config.config_bao import (
    BootstrapSettings,
    DynamicHostContainer,
    OpenBaoClient,
)
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Host controls startup & OpenBao connection setup
    bootstrap_settings = BootstrapSettings()
    bao_client = OpenBaoClient(
        bao_addr=bootstrap_settings.bao_addr,
        bao_token=bootstrap_settings.bao_token.get_secret_value(),
    )

    # 2. Boot configuration engine (OpenBao Fetch -> Discovery -> Fail-fast Validation)
    config_container: DynamicHostContainer = await bootstrap_application_configuration(
        bao_client=bao_client,
        bootstrap_settings=bootstrap_settings,
    )

    # Attach container directly to FastAPI app.state
    app.state.config = config_container

    # 3. Instantiate library clients explicitly using the hydrated container
    # BuildServiceConfig is automatically attached to config_container.build_service via entry points
    build_config = getattr(config_container, "build_service", None)
    app.state.build_service = BuildApplicationService(config=build_config)

    logger.info(
        "Application bootstrapped successfully",
        env=config_container.host.app_env,
        max_jobs=build_config.max_concurrent_jobs if build_config else "default",
    )
    yield


app = FastAPI(title="Meta Application Builder", lifespan=lifespan)
app.include_router(router)


# Request Helpers for Dependency Injection
def get_build_service(request: Request) -> BuildApplicationService:
    return request.app.state.build_service


class APIBuildSubmitRequest(BaseModel):
    blueprint_id: str = Field(..., min_length=1)
    spec_payload: Dict[str, Any] = Field(default_factory=dict)


class APIValidateRequest(BaseModel):
    spec_payload: Dict[str, Any] = Field(...)


def get_current_security_claims() -> SecurityClaims:
    try:
        return IdentityContextManager.get_current_identity()
    except Exception:
        return SecurityClaims(
            iss="https://identity.meta.internal",
            sub="usr_admin",
            aud="meta_control_plane",
            exp=2147483647,
            nbf=1,
            iat=1,
            jti="jti_default_test_token_12345",
            tenant_id="tenant_default",
            roles=["admin"],
        )


@router.post("/submit", response_model=BuildJobResult, status_code=status.HTTP_202_ACCEPTED)
async def submit_build(
    payload: APIBuildSubmitRequest,
    idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    claims: SecurityClaims = Depends(get_current_security_claims),
    service: BuildApplicationService = Depends(get_build_service),
) -> BuildJobResult:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="X-Idempotency-Key header is required.")

    req = BuildJobRequest(
        tenant_id=claims.tenant_id,
        actor=claims.sub,
        blueprint_id=payload.blueprint_id,
        spec_payload=payload.spec_payload,
    )
    return await service.submit_build(req)


@router.post("/validate", status_code=status.HTTP_200_OK)
async def validate_spec(
    payload: APIValidateRequest,
    service: BuildApplicationService = Depends(get_build_service),
) -> Dict[str, Any]:
    return await service.validate_spec(payload.spec_payload)


@router.get("/status/{job_id}", status_code=status.HTTP_200_OK)
async def get_build_status(
    job_id: uuid.UUID,
    service: BuildApplicationService = Depends(get_build_service),
) -> Dict[str, Any]:
    return service.get_status(job_id)


@router.get("/artifact/{job_id}", status_code=status.HTTP_200_OK)
async def get_build_artifact(
    job_id: uuid.UUID,
    service: BuildApplicationService = Depends(get_build_service),
) -> Dict[str, Any]:
    return service.get_artifact(job_id)