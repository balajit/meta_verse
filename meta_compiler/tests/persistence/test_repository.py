"""WorkflowRepository persistence tests: UUID contract and provenance columns."""

import asyncio
from uuid import UUID

import pytest

from meta_compiler.persistence.repository import (
    RepositoryError,
    WorkflowRepository,
)
from meta_compiler.stages.db_serializer import to_db_payload
from tests.conftest import RecordingSession


def _payload() -> dict:
    payload = to_db_payload(
        {
            "namespace": "ns",
            "name": "wf",
            "version": "v1",
            "description": "desc",
            "compiled_manifest": {"tasks": []},
            "execution_order": [],
        }
    )
    payload["pinned_dependencies"] = {"lib_a": {"version": "1.2.0"}}
    payload["version_vector"] = {"lib_a": "1.2.0"}
    return payload


def test_persist_stages_insert_with_native_uuid() -> None:
    session = RecordingSession()
    repo = WorkflowRepository(session)

    async def _scenario() -> UUID:
        return await repo.persist_workflow_definition(_payload())

    record_id = asyncio.run(_scenario())
    assert isinstance(record_id, UUID)
    assert len(session.executed) == 1

    compiled = session.executed[0].compile()
    assert "pinned_dependencies" in str(compiled)
    assert "version_vector" in str(compiled)
    assert any(isinstance(v, UUID) for v in compiled.params.values())
    assert {"lib_a": "1.2.0"} in compiled.params.values() or {
        "lib_a": {"version": "1.2.0"}
    } in compiled.params.values()


def test_persist_wraps_failures_in_repository_error() -> None:
    class _BrokenSession(RecordingSession):
        async def execute(self, stmt: object) -> None:
            raise RuntimeError("boom")

    repo = WorkflowRepository(_BrokenSession())

    async def _scenario() -> UUID:
        return await repo.persist_workflow_definition(_payload())

    with pytest.raises(RepositoryError):
        asyncio.run(_scenario())


def test_save_alias_delegates_to_persist() -> None:
    session = RecordingSession()
    repo = WorkflowRepository(session)

    async def _scenario() -> UUID:
        return await repo.save(_payload())

    record_id = asyncio.run(_scenario())
    assert isinstance(record_id, UUID)
    assert len(session.executed) == 1


def test_missing_id_key_raises() -> None:
    repo = WorkflowRepository(RecordingSession())

    async def _scenario() -> UUID:
        return await repo.persist_workflow_definition({"namespace": "ns"})

    with pytest.raises(KeyError):
        asyncio.run(_scenario())
