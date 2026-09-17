import pytest
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncSession
from meta_builder_brain.persistence.mbb_models import (
    Base,
    SpecificationsRegistry,
    BuildJobAudit,
    BuildJobEvents,
    ArtifactManifests,
)
from meta_builder_brain.persistence.orm_builder import DynamicMetaclassBuilder


@pytest.mark.asyncio
async def test_specifications_registry_crud(async_session: AsyncSession):
    spec = SpecificationsRegistry(
        urn="urn:meta:bcr:global:test_entity:v1.0",
        namespace_id="global",
        component_name="test_entity",
        version="v1.0",
        schema_ast={"type": "object", "properties": {"id": {"type": "string"}}},
    )
    async_session.add(spec)
    await async_session.commit()

    stmt = select(SpecificationsRegistry).where(
        SpecificationsRegistry.urn == "urn:meta:bcr:global:test_entity:v1.0"
    )
    result = await async_session.execute(stmt)
    retrieved = result.scalar_one_or_none()
    assert retrieved is not None
    assert retrieved.component_name == "test_entity"
    assert retrieved.schema_ast["type"] == "object"


@pytest.mark.asyncio
async def test_build_job_audit_events_relationship(async_session: AsyncSession):
    job = BuildJobAudit(
        job_id="job_999",
        namespace_id="global",
        status="RUNNING",
        initiated_by="test_suite",
    )
    async_session.add(job)
    await async_session.commit()

    event = BuildJobEvents(
        job_id="job_999",
        event_type="STAGE_COMPLETED",
        payload={"stage": "AST_PARSING"},
    )
    async_session.add(event)
    await async_session.commit()

    stmt = select(BuildJobAudit).where(BuildJobAudit.job_id == "job_999")
    res = await async_session.execute(stmt)
    audit_record = res.scalar_one()
    assert audit_record.status == "RUNNING"


def test_dynamic_metaclass_builder_synthesis():
    fields_spec = {
        "username": {"type": "string", "nullable": False},
        "login_count": {"type": "integer", "nullable": True},
        "metadata_json": {"type": "json", "nullable": True},
    }

    DynamicModel = DynamicMetaclassBuilder.create_orm_model(
        class_name="DynamicUserProfile",
        table_name="dyn_user_profile",
        fields=fields_spec,
        base_class=Base,
    )

    assert DynamicModel.__tablename__ == "dyn_user_profile"
    assert hasattr(DynamicModel, "id")
    assert hasattr(DynamicModel, "username")
    assert hasattr(DynamicModel, "login_count")
    assert hasattr(DynamicModel, "metadata_json")