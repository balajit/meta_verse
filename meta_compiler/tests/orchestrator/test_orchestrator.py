"""Orchestrator end-to-end tests (in-memory compile + transactional registration)."""

import asyncio
from typing import Any
from uuid import UUID

import pytest

from meta_compiler.core.action_registry import ActionRegistry
from meta_compiler.orchestrator import (
    CompiledWorkflowDefinition,
    compile_and_register_manifest,
    compile_manifest,
    register_workflow,
)
from tests.conftest import RecordingSession, chain_manifest


def test_compile_manifest_runs_in_memory_without_db(action_registry) -> None:
    compiled = compile_manifest(chain_manifest(), registry=action_registry)

    assert isinstance(compiled, CompiledWorkflowDefinition)
    assert compiled.manifest_spec is not None
    assert [t.id for t in compiled.manifest_spec.tasks] == ["produce", "consume"]
    assert compiled.execution_plan.stages == (("produce",), ("consume",))
    assert compiled.raw_manifest["namespace"] == "ns"


def test_compile_manifest_accepts_dict_input(action_registry) -> None:
    manifest_dict = {
        "version": "v1",
        "namespace": "ns",
        "name": "wf_dict",
        "entities": {},
        "tasks": [{"id": "produce", "action": "alpha"}],
    }
    compiled = compile_manifest(manifest_dict, registry=action_registry)
    assert compiled.manifest_spec is not None
    assert compiled.manifest_spec.name == "wf_dict"


def test_compile_manifest_rejects_unknown_action(action_registry) -> None:
    from meta_compiler.orchestrator import PipelineCompilationError
    from tests.conftest import manifest_yaml

    bad_yaml = manifest_yaml('  - id: "ghost"\n    action: "missing"\n')
    with pytest.raises(PipelineCompilationError):
        compile_manifest(bad_yaml, registry=ActionRegistry())


def test_register_workflow_persists_and_commits(action_registry) -> None:
    compiled = compile_manifest(chain_manifest(), registry=action_registry)
    session = RecordingSession()

    async def _scenario() -> UUID:
        return await register_workflow(compiled, session)

    record_id = asyncio.run(_scenario())
    assert isinstance(record_id, UUID)
    assert len(session.executed) == 1
    assert session.commits == 0


def test_compile_and_register_manifest_end_to_end(action_registry) -> None:
    session = RecordingSession()
    compiled = compile_manifest(
        chain_manifest(),
        registry=action_registry,
        pinned_dependencies={"lib_a": {"version": "1.2.0"}},
        version_vector={"lib_a": "1.2.0"},
    )

    async def _scenario() -> Any:
        return await compile_and_register_manifest(
            chain_manifest(),
            session,
            registry=action_registry,
            pinned_dependencies={"lib_a": {"version": "1.2.0"}},
            version_vector={"lib_a": "1.2.0"},
        )

    graph = asyncio.run(_scenario())
    assert sorted(graph.nodes) == ["consume", "produce"]
    assert graph.namespace == "ns"
    assert session.commits == 1
    assert len(session.executed) == 1
    compiled = session.executed[0].compile()
    assert "version_vector" in str(compiled)
    assert "pinned_dependencies" in str(compiled)
    assert {"lib_a": "1.2.0"} in compiled.params.values() or {
        "lib_a": {"version": "1.2.0"}
    } in compiled.params.values()


def test_pre_commit_guard_hook_is_invoked(action_registry) -> None:
    calls: list[dict[str, Any]] = []

    async def guard(pinned: dict[str, Any]) -> None:
        calls.append(pinned)

    compiled = compile_manifest(
        chain_manifest(),
        registry=action_registry,
        pinned_dependencies={"lib_a": {"version": "1.2.0"}},
    )
    session = RecordingSession()

    async def _scenario() -> None:
        await register_workflow(compiled, session, pre_commit_guard=guard)

    asyncio.run(_scenario())
    assert calls == [{"lib_a": {"version": "1.2.0"}}]
