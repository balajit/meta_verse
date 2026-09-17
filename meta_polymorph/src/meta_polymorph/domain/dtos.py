"""Domain Data Transfer Objects (DTOs) and Pydantic schemas."""

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class TenantContext(BaseModel):
    """Context identifying tenant hierarchy and scope for resolution."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    industry_id: str
    global_id: str = "global"


class ManifestIR(BaseModel):
    """Pure, serializable Intermediate Representation container for compiled manifests."""

    model_config = ConfigDict(frozen=True)

    version: str = "1.0.0"
    namespace: str
    name: str
    description: str | None = ""
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    fsms: list[dict[str, Any]] = Field(default_factory=list)