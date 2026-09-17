"""Mutator boundary tests: version vectors, drift guard, append-only mutation."""

import asyncio
from typing import Any

import pytest

from meta_compiler.orchestrator import (
    CompiledWorkflowDefinition,
)
from meta_compiler.orchestrator import (
    compile_manifest as compile_manifest_orchestrator,
)
from meta_compiler.persistence.mutator import (
    MutationGuardError,
    WorkflowDefinitionMutator,
    assert_no_pinned_dependency_drift,
    build_mutated_payload,
    compute_version_vector,
)
from meta_compiler.stages.db_serializer import to_db_payload
from tests.conftest import RecordingSession, chain_manifest


def test_compute_version_vector_from_snapshot() -> None:
    vector = compute_version_vector({"lib_a": {"version": "1.2.0"}, "lib_b": {}})
    assert vector == {"lib_a": "1.2.0", "lib_b": "unknown"}


def test_drift_guard_passes_when_current_matches() -> None:
    assert_no_pinned_dependency_drift({"lib_a": "1.2.0"}, {"lib_a": "1.2.0"})


def test_drift_guard_raises_on_drift() -> None:
    with pytest.raises(MutationGuardError):
        assert_no_pinned_dependency_drift({"lib_a": "1.2.0"}, {"lib_a": "2.0.0"})


def test_drift_guard_raises_on_missing_current() -> None:
    with pytest.raises(MutationGuardError):
        assert_no_pinned_dependency_drift({"lib_a": "1.2.0"}, {})


def test_build_mutated_payload_bumps_version_and_carries_vector() -> None:
    base = to_db_payload({"namespace": "ns", "name": "wf", "version": "v1"})
    mutated = build_mutated_payload(
        base,
        manifest_patch={"description": "patched"},
        new_version="v2",
        pinned_dependencies={"lib_a": {"version": "1.2.0"}},
        version_vector={"lib_a": "1.2.0"},
    )
    assert mutated["version"] == "v2"
    assert mutated["compiled_manifest"]["description"] == "patched"
    assert mutated["pinned_dependencies"] == {"lib_a": {"version": "1.2.0"}}
    assert mutated["version_vector"] == {"lib_a": "1.2.0"}


def test_build_mutated_payload_recomputes_vector_when_not_given() -> None:
    base = to_db_payload({"namespace": "ns", "name": "wf", "version": "v1"})
    mutated = build_mutated_payload(
        base,
        manifest_patch={},
        new_version="v2",
        pinned_dependencies={"lib_a": {"version": "3.0.0"}},
    )
    assert mutated["version_vector"] == {"lib_a": "3.0.0"}


def test_register_mutation_persists_new_record(action_registry) -> None:
    compiled = CompiledWorkflowDefinition(
        manifest_spec=compile_manifest_orchestrator(
            chain_manifest(), registry=action_registry
        ).manifest_spec,
        execution_plan=compile_manifest_orchestrator(
            chain_manifest(), registry=action_registry
        ).execution_plan,
        raw_manifest={"namespace": "ns", "name": "wf", "version": "v1"},
        pinned_dependencies={"lib_a": {"version": "1.2.0"}},
        version_vector={"lib_a": "1.2.0"},
    )
    session = RecordingSession()
    mutator = WorkflowDefinitionMutator(session)

    async def _scenario() -> Any:
        return await mutator.register_mutation(
            compiled,
            manifest_patch={"description": "mutated"},
            new_version="v2",
            current_versions={"lib_a": "1.2.0"},
        )

    record_id = asyncio.run(_scenario())
    assert record_id is not None
    assert len(session.executed) == 1
    compiled = session.executed[0].compile()
    assert "pinned_dependencies" in str(compiled)
    assert "version_vector" in str(compiled)
    assert "v2" in list(compiled.params.values())


def test_register_mutation_blocks_on_drift(action_registry) -> None:
    compiled = CompiledWorkflowDefinition(
        manifest_spec=compile_manifest_orchestrator(
            chain_manifest(), registry=action_registry
        ).manifest_spec,
        execution_plan=compile_manifest_orchestrator(
            chain_manifest(), registry=action_registry
        ).execution_plan,
        raw_manifest={"namespace": "ns", "name": "wf", "version": "v1"},
        pinned_dependencies={"lib_a": {"version": "1.2.0"}},
        version_vector={"lib_a": "1.2.0"},
    )
    mutator = WorkflowDefinitionMutator(RecordingSession())

    async def _scenario() -> None:
        await mutator.register_mutation(
            compiled,
            manifest_patch={},
            new_version="v2",
            current_versions={"lib_a": "9.9.9"},
        )

    with pytest.raises(MutationGuardError):
        asyncio.run(_scenario())
