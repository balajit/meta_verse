from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, status
from pydantic import BaseModel

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1/build", tags=["Status & Control"])

class JobStatusResponse(BaseModel):
    job_id: uuid.UUID
    state: str
    updated_at: str

@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_build_status(job_id: uuid.UUID) -> JobStatusResponse:
    logger.debug("fetching_job_status", job_id=str(job_id))
    # Simulated record fetch
    return JobStatusResponse(
        job_id=job_id,
        state="COMPILING_IR",
        updated_at="2026-08-30T13:24:31Z"
    )

@router.post("/cancel/{job_id}", status_code=status.HTTP_200_OK)
async def cancel_build(job_id: uuid.UUID) -> dict[str, str]:
    logger.info("job_cancellation_requested", job_id=str(job_id))
    return {"job_id": str(job_id), "status": "CANCELLED"}