from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1/build", tags=["Builds"])


class BuildSubmitRequest(BaseModel):
    blueprint_id: str = Field(..., min_length=1)
    spec_payload: dict[str, Any] = Field(default_factory=dict)


class BuildSubmitResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    message: str


@router.post("/submit", response_model=BuildSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_build(
        payload: BuildSubmitRequest,
        idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key")
) -> BuildSubmitResponse:
    if not idempotency_key:
        logger.warning("submit_missing_idempotency_key", blueprint_id=payload.blueprint_id)
        raise HTTPException(status_code=400, detail="X-Idempotency-Key header is required.")

    job_id = uuid.uuid4()
    logger.info("build_submitted_successfully", job_id=str(job_id), blueprint_id=payload.blueprint_id,
                idempotency_key=idempotency_key)

    return BuildSubmitResponse(
        job_id=job_id,
        status="QUEUED",
        message="Build successfully queued for execution."
    )