from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1/build", tags=["Artifacts"])

class ArtifactResponse(BaseModel):
    job_id: uuid.UUID
    cas_pointer: str = Field(..., description="Content-Addressable Storage hash pointer.")
    provenance_metadata: dict[str, str] = Field(default_factory=dict)

@router.get("/artifacts/{job_id}", response_model=ArtifactResponse)
async def get_build_artifacts(job_id: uuid.UUID) -> ArtifactResponse:
    logger.debug("fetching_artifacts", job_id=str(job_id))
    return ArtifactResponse(
        job_id=job_id,
        cas_pointer="sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        provenance_metadata={"builder_version": "2.4.0", "compiler_mode": "strict"}
    )