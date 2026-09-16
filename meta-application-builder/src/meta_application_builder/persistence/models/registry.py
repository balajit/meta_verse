from __future__ import annotations

import uuid
from typing import Any, Dict

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from meta_application_builder.persistence.models.base import Base, TenantAwareMixin


class SpecificationRegistryModel(Base, TenantAwareMixin):
    """ORM representation of canonical blueprint specifications."""

    __tablename__ = "specifications_registry"

    urn: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    immutability_tier: Mapped[str] = mapped_column(String(16), nullable=False, default="OVERRIDABLE")
    schema_payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "urn", "version", name="uq_tenant_urn_version"),
        Index("idx_spec_registry_tenant_urn", "tenant_id", "urn"),
    )


class DAGLineageClosureModel(Base):
    """Precomputed closure table storing dependency graph relations for fast lookup."""

    __tablename__ = "dag_lineage_closure"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # FIX: Implemented missing Foreign Keys to prevent orphaned records upon node deletion
    ancestor_urn: Mapped[str] = mapped_column(
        String(255), ForeignKey("specifications_registry.urn", ondelete="CASCADE"), nullable=False, index=True
    )
    descendant_urn: Mapped[str] = mapped_column(
        String(255), ForeignKey("specifications_registry.urn", ondelete="CASCADE"), nullable=False, index=True
    )
    depth: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "ancestor_urn", "descendant_urn", name="uq_dag_closure_edge"),
        Index("idx_dag_closure_traversal", "tenant_id", "ancestor_urn", "depth"),
    )