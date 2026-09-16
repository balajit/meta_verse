from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ImmutabilityTier(str, Enum):
    """Governs schema field inheritance and overriding behavior across child templates."""

    FINAL = "FINAL"  # Strictly immutable; child templates cannot alter this definition.
    EXTENDABLE = "EXTENDABLE"  # Attributes can be appended, but existing structures cannot be deleted.
    OVERRIDABLE = "OVERRIDABLE"  # Child templates can fully reconfigure or override this node.


class AttributeDefinition(BaseModel):
    """Schema property definition within a Domain Entity Template."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(..., pattern=r"^[a_z][a-z0-9_]*$")
    data_type: str = Field(..., description="Target language Primitive or Complex Type name.")
    required: bool = Field(default=True)
    immutability_tier: ImmutabilityTier = Field(default=ImmutabilityTier.OVERRIDABLE)
    default_value: Optional[Union[str, int, float, bool, Dict[str, Any], List[Any]]] = None
    description: Optional[str] = None


class DomainEntityTemplate(BaseModel):
    """Canonical domain schema manifest representation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    urn: str = Field(..., pattern=r"^urn:meta:bcr:[a-z0-9_\-]+:[a-z0-9_\-]+:[a-z0-9_\.\-]+$")
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    name: str = Field(..., pattern=r"^[A-Z][a-zA-Z0-9]*$")
    parent_urn: Optional[str] = None
    immutability_tier: ImmutabilityTier = Field(default=ImmutabilityTier.OVERRIDABLE)
    attributes: Dict[str, AttributeDefinition] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)

    @field_validator("attributes")
    @classmethod
    def validate_attribute_keys(cls, v: Dict[str, AttributeDefinition]) -> Dict[str, AttributeDefinition]:
        """Ensures key identifiers in attribute mappings match inner name definitions."""
        for key, attr in v.items():
            if key != attr.name:
                raise ValueError(f"Attribute key '{key}' does not match attribute name field '{attr.name}'.")
        return v