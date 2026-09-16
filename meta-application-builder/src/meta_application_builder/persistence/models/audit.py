from __future__ import annotations

import uuid
from typing import Any, Dict, List

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meta_application_builder.persistence.models.base import Base, TenantAwareMixin


class BuildJobAuditModel(Base, TenantAwareMixin):
    """Master record for code compilation and build pipeline execution."""

    __tablename__ = "build_job_audit"

    job_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="SUBMITTED")
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    specification_urn: Mapped[str] = mapped_column(String(255), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    events: Mapped[List[BuildJobEventModel]] = relationship(
        "BuildJobEventModel", back_populates="job", cascade="all, delete-orphan",
        order_by="BuildJobEventModel.sequence_number"
    )


class BuildJobEventModel(Base):
    """Cryptographically chained event logs generated during build steps."""

    __tablename__ = "build_job_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("build_job_audit.job_id", ondelete="CASCADE"),
                                        nullable=False, index=True)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)

    job: Mapped[BuildJobAuditModel] = relationship("BuildJobAuditModel", back_populates="events")

    __table_args__ = (
        UniqueConstraint("job_id", "sequence_number", name="uq_job_event_sequence"),
        Index("idx_event_chain", "job_id", "sequence_number"),
    )


class BuildIdempotencyKeyModel(Base, TenantAwareMixin):
    """Idempotency record to prevent duplicate submit execution under race conditions."""

    __tablename__ = "build_idempotency_keys"

    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False)
    response_payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_tenant_idempotency_key"),
    )