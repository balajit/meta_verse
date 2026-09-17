"""Unified engine pipeline tests: stage order, sync/async compile, adapter self-healing."""

import asyncio

import pytest

from meta_compiler.core.immutable import ImmutableDict
from meta_compiler.engine import MetaCompiler
from meta_compiler.exceptions import ContractValidationError, ModelCompilationError
from meta_compiler.stages.contract_checker import ContractCheckerStage
from meta_compiler.stages.model_compiler import ModelCompilerStage
from meta_compiler.stages.schema_synthesis import SchemaSynthesisStage
from meta_compiler.stages.semantic_validator import SemanticValidatorStage
from meta_compiler.stages.syntax_guard import SyntaxGuardStage as SyntaxGuard
from meta_compiler.stages.topology_validator import TopologyValidatorStage as TopologyValidator
from tests.conftest import chain_manifest, manifest_yaml


def test_default_validation_stage_order() -> None:
    engine = MetaCompiler()
    expected = [
        SyntaxGuard,
        SchemaSynthesisStage,
        ModelCompilerStage,
        SemanticValidatorStage,
        TopologyValidator,
        ContractCheckerStage,
    ]
    assert engine._validation_stage_classes == expected


def test_compile_sync_produces_manifest_plan_and_db_payload(action_registry) -> None:
    engine = MetaCompiler(registry=action_registry)
    context = engine.compile_sync(chain_manifest())

    assert context.manifest_spec is not None
    task_ids = [t.id for t in context.manifest_spec.tasks]
    assert task_ids == ["produce", "consume"]

    assert context.execution_plan is not None
    assert context.execution_plan.roots == ("produce",)
    assert context.execution_plan.leaves == ("consume",)
    assert context.execution_plan.stages == (("produce",), ("consume",))

    assert context.db_payload
    assert context.db_payload["namespace"] == "ns"
    assert len(context.db_payload["compiled_manifest"]["tasks"]) == 2


def test_manifest_task_params_are_deep_frozen(action_registry) -> None:
    engine = MetaCompiler(registry=action_registry)
    yaml_doc = manifest_yaml(
        '  - id: "produce"\n    action: "alpha"\n    params:\n      mode: "fast"\n'
    )
    context = engine.compile_sync(yaml_doc)
    task_params = context.manifest_spec.tasks[0].params
    assert isinstance(task_params, ImmutableDict)
    with pytest.raises(TypeError):
        task_params["mode"] = "slow"  # type: ignore[index]


def test_compile_async_returns_execution_graph(action_registry) -> None:
    async def _scenario() -> None:
        engine = MetaCompiler(registry=action_registry)
        graph = await engine.compile(chain_manifest())
        assert sorted(graph.nodes) == ["consume", "produce"]
        assert graph.namespace == "ns"
        assert graph.db_record_id == "unpersisted"

    asyncio.run(_scenario())


def test_adapter_self_healing_injects_adapter_and_converges(typed_registry) -> None:
    engine = MetaCompiler(registry=typed_registry)
    yaml_doc = manifest_yaml(
        '  - id: "int_produce"\n    action: "int_producer"\n'
        '  - id: "str_consume"\n    action: "str_consumer"\n'
        '    depends_on: ["int_produce"]\n'
    )
    context = engine.compile_sync(yaml_doc)

    assert context.reprocess_counter == 1
    assert context.requires_reprocessing is False
    task_ids = [t.id for t in context.manifest_spec.tasks]
    assert any(tid.startswith("adapter_") for tid in task_ids)


def test_unregistered_action_fails_compilation(action_registry) -> None:
    engine = MetaCompiler(registry=action_registry)
    yaml_doc = manifest_yaml('  - id: "ghost"\n    action: "noop"\n')
    with pytest.raises(ContractValidationError):
        engine.compile_sync(yaml_doc)


def test_self_dependency_is_rejected(action_registry) -> None:
    engine = MetaCompiler(registry=action_registry)
    yaml_doc = manifest_yaml(
        '  - id: "selfish"\n    action: "alpha"\n    depends_on: ["selfish"]\n'
    )
    with pytest.raises(ModelCompilationError):
        engine.compile_sync(yaml_doc)
