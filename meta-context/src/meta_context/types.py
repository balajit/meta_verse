"""Core domain types and immutable structures for meta-context."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from meta_context.exceptions import ContextValidationError


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Immutable representation of tenant scope context."""

    tenant_id: str
    organization_id: str | None = None
    environment: str = "production"
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.tenant_id.strip():
            raise ContextValidationError("tenant_id must be a non-empty string.")

        if self.organization_id is not None and not self.organization_id.strip():
            raise ContextValidationError("organization_id, if provided, must be a non-empty string.")

        if not isinstance(self.attributes, MappingProxyType):
            object.__setattr__(
                self,
                "attributes",
                MappingProxyType(dict(self.attributes))
            )

    def get_attribute(self, key: str, default: Any = None) -> Any:
        """Retrieve a custom attribute from the tenant context safely."""
        return self.attributes.get(key, default)


@dataclass(frozen=True, slots=True)
class ContextSnapshot:
    """Immutable point-in-time snapshot of the active context state."""

    correlation_id: str | None
    tenant_context: TenantContext | None
    execution_state: Mapping[str, Any]