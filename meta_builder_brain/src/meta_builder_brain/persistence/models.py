"""SQLAlchemy ORM models and Declarative Base for database persistence."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, JSON
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Declarative base class for dynamically generated and static ORM models."""

    pass


class SpecificationsRegistry(Base):
    __tablename__ = "specifications_registry"

    urn = Column(String(500), primary_key=True)
    namespace_id = Column(String(255), nullable=False)
    component_name = Column(String(255), nullable=False)
    version = Column(String(50), nullable=False)
    schema_ast = Column(JSON, nullable=False, default=dict)
    checksum_sha256 = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class BuildJobAudit(Base):
    __tablename__ = "build_job_audit"

    job_id = Column(String(255), primary_key=True)
    namespace_id = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="PENDING")
    initiated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    events = relationship("BuildJobEvents", back_populates="job", cascade="all, delete-orphan")


class BuildJobEvents(Base):
    __tablename__ = "build_job_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(255), ForeignKey("build_job_audit.job_id"), nullable=False)
    event_type = Column(String(100), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    job = relationship("BuildJobAudit", back_populates="events")


class ArtifactManifests(Base):
    __tablename__ = "artifact_manifests"

    artifact_id = Column(String(255), primary_key=True)
    job_id = Column(String(255), nullable=False)
    urn = Column(String(500), nullable=False)
    artifact_type = Column(String(100), nullable=False)
    location_uri = Column(String(1000), nullable=False)
    checksum_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))