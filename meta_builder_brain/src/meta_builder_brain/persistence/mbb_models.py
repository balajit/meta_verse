"""Pure Pydantic domain models, Enums, and re-exported ORM abstractions for meta_builder_brain."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Re-export SQLAlchemy ORM models to support persistence test imports
from meta_builder_brain.persistence.models import (
    ArtifactManifests,
    Base,
    BuildJobAudit,
    BuildJobEvents,
    SpecificationsRegistry,
)


class BuildJobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class IdempotencyStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SpecificationRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    urn: str = Field(..., description="Canonical URN spec identifier")
    namespace: str
    component_name: str
    version: str
    specification_manifest: Dict[str, Any]
    checksum_sha256: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BuildJobAuditRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    job_id: UUID
    tenant_id: str
    status: BuildJobStatus
    manifest_urn: str
    execution_graph: Dict[str, Any]
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BuildJobEventRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    event_id: UUID
    job_id: UUID
    event_type: str
    payload: Dict[str, Any]
    created_at: Optional[datetime] = None


class ArtifactManifestRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    artifact_id: UUID
    job_id: UUID
    urn: str
    artifact_type: str
    location_uri: str
    checksum_sha256: str
    created_at: Optional[datetime] = None


class LineageClosureRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    ancestor_urn: str
    descendant_urn: str
    path_length: int
    generation_id: int
    is_active: bool = False
    created_at: Optional[datetime] = None


class IdempotencyRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    idempotency_key: str
    status: IdempotencyStatus
    response_payload: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    expires_at: datetime


__all__ = [
    "Base",
    "SpecificationsRegistry",
    "BuildJobAudit",
    "BuildJobEvents",
    "ArtifactManifests",
    "BuildJobStatus",
    "IdempotencyStatus",
    "SpecificationRecord",
    "BuildJobAuditRecord",
    "BuildJobEventRecord",
    "ArtifactManifestRecord",
    "LineageClosureRecord",
    "IdempotencyRecord",
]