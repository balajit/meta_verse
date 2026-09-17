"""API router for Meta Builder Brain persistence and orchestration endpoints."""

from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from meta_builder_brain.exceptions import BuildExecutionError, PersistenceError
from meta_builder_brain.orchestrator import BuildOrchestrator
from meta_builder_brain.persistence.mbb_models import (
    BuildJobAuditRecord,
    BuildJobEventRecord,
    SpecificationRecord,
)
from meta_builder_brain.persistence.mbb_mutator import DatabaseMutator
from meta_builder_brain.persistence.mbb_repository import EntityRepository

router = APIRouter(prefix="/v1", tags=["Meta Builder Brain"])


class BuildJobRequest(BaseModel):
    tenant_id: str = Field(..., description="Tenant identifier executing build")
    manifest_urn: str = Field(..., description="Canonical URN spec identifier")
    execution_graph: Dict[str, Any] = Field(
        default_factory=dict, description="DAG execution graph configuration"
    )


class SpecificationUpsertRequest(BaseModel):
    urn: str = Field(..., description="Canonical URN spec identifier")
    namespace: str
    component_name: str
    version: str
    specification_manifest: Dict[str, Any]
    checksum_sha256: str


def get_repository() -> EntityRepository:
    raise NotImplementedError("Repository dependency provider not wired.")


def get_mutator() -> DatabaseMutator:
    raise NotImplementedError("Mutator dependency provider not wired.")


def get_orchestrator() -> BuildOrchestrator:
    raise NotImplementedError("Orchestrator dependency provider not wired.")


@router.post(
    "/builds",
    response_model=BuildJobAuditRecord,
    status_code=status.HTTP_201_CREATED,
)
async def create_build_job(
    request: BuildJobRequest,
    orchestrator: BuildOrchestrator = Depends(get_orchestrator),
) -> BuildJobAuditRecord:
    """Triggers a build execution job given a manifest URN and execution topology."""
    try:
        return await orchestrator.execute_build_job(
            tenant_id=request.tenant_id,
            manifest_urn=request.manifest_urn,
            execution_graph=request.execution_graph,
        )
    except BuildExecutionError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        ) from err
    except PersistenceError as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Persistence error during build execution: {err}",
        ) from err


@router.get("/builds/{job_id}", response_model=BuildJobAuditRecord)
async def get_build_job(
    job_id: UUID,
    repository: EntityRepository = Depends(get_repository),
) -> BuildJobAuditRecord:
    """Retrieves audit state for a target build job by UUID."""
    job = await repository.get_build_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Build job {job_id} not found.",
        )
    return job


@router.get("/builds/{job_id}/events", response_model=List[BuildJobEventRecord])
async def list_build_job_events(
    job_id: UUID,
    repository: EntityRepository = Depends(get_repository),
) -> List[BuildJobEventRecord]:
    """Retrieves execution events for a build job in chronological order."""
    return await repository.get_build_job_events(job_id)


@router.get("/specifications/{urn:path}", response_model=SpecificationRecord)
async def get_specification(
    urn: str,
    repository: EntityRepository = Depends(get_repository),
) -> SpecificationRecord:
    """Fetches a specification manifest record by canonical URN."""
    spec = await repository.get_specification(urn)
    if not spec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Specification URN {urn} not found.",
        )
    return spec


@router.post(
    "/specifications",
    response_model=SpecificationRecord,
    status_code=status.HTTP_201_CREATED,
)
async def upsert_specification(
    request: SpecificationUpsertRequest,
    mutator: DatabaseMutator = Depends(get_mutator),
) -> SpecificationRecord:
    """Registers or updates a specification manifest record in the repository."""
    try:
        record = SpecificationRecord(
            urn=request.urn,
            namespace=request.namespace,
            component_name=request.component_name,
            version=request.version,
            specification_manifest=request.specification_manifest,
            checksum_sha256=request.checksum_sha256,
        )
        return await mutator.upsert_specification(record)
    except PersistenceError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to register specification: {err}",
        ) from err