"""Contract checker unit tests: type compatibility, edge diagnostics, dry-run."""

from typing import Optional, Union

from pydantic import BaseModel

from meta_compiler.engine import MetaCompiler
from meta_compiler.stages.contract_checker import (
    ContractChecker,
    is_type_compatible,
    verify_edge_contracts,
)
from tests.conftest import chain_manifest, manifest_yaml


class CustomerSchema(BaseModel):
    name: str


class AuditSchema(BaseModel):
    name: str


def test_type_identity_is_compatible() -> None:
    assert is_type_compatible(str, str)
    assert is_type_compatible(CustomerSchema, CustomerSchema)


def test_any_is_compatible_with_everything() -> None:
    from typing import Any

    assert is_type_compatible(Any, int)
    assert is_type_compatible(int, Any)


def test_numeric_promotion() -> None:
    assert is_type_compatible(int, float)


def test_subclass_assignability() -> None:
    class Animal(BaseModel):
        pass

    class Dog(Animal):
        pass

    assert is_type_compatible(Dog, Animal)
    assert not is_type_compatible(Animal, Dog)


def test_union_and_optional_handling() -> None:
    assert is_type_compatible(int, Union[int, str])
    assert is_type_compatible(int, Optional[int])
    assert not is_type_compatible(int, Optional[str])


def test_incompatible_types_rejected() -> None:
    assert not is_type_compatible(int, str)
    assert not is_type_compatible(CustomerSchema, AuditSchema)


def test_incompatible_edge_contract_detected_and_self_heals(typed_registry) -> None:
    yaml_doc = manifest_yaml(
        '  - id: "produce"\n    action: "int_producer"\n'
        '  - id: "consume"\n    action: "str_consumer"\n'
        '    depends_on: ["produce"]\n'
    )
    engine = MetaCompiler(registry=typed_registry)
    context = engine.compile_sync(yaml_doc)

    assert context.reprocess_counter == 1
    assert context.requires_reprocessing is False
    assert context.diagnostics == []
    assert any(task.id.startswith("adapter_") for task in context.manifest_spec.tasks)


def test_verify_edge_contracts_returns_mismatches() -> None:
    from meta_compiler.core.action_registry import ActionRegistry

    registry = ActionRegistry()
    registry.register("int_producer", lambda **kw: None, output_schema=CustomerSchema)
    registry.register("str_consumer", lambda **kw: None, input_schema=AuditSchema)

    mismatches = verify_edge_contracts(
        manifest=_build_typed_manifest(),
        registry=registry,
    )
    assert len(mismatches) == 1
    assert mismatches[0].producer_id == "produce"
    assert mismatches[0].consumer_id == "consume"


def _build_typed_manifest():
    from meta_compiler.core.models import TaskNodeSpec, WorkflowManifestSpec

    return WorkflowManifestSpec(
        version="v1",
        namespace="ns",
        name="wf",
        entities={},
        fsms={},
        tasks=(
            TaskNodeSpec(id="produce", action="int_producer"),
            TaskNodeSpec(
                id="consume",
                action="str_consumer",
                depends_on=("produce",),
            ),
        ),
    )


def test_dry_run_executes_all_stages(typed_registry) -> None:
    yaml_doc = manifest_yaml(
        '  - id: "produce"\n    action: "int_producer"\n'
        '  - id: "consume"\n    action: "str_consumer"\n'
        '    depends_on: ["produce"]\n'
    )
    engine = MetaCompiler(registry=typed_registry)
    context = engine.compile_sync(yaml_doc)

    checker = ContractChecker(typed_registry)
    assert (
        checker.verify_node_contracts(
            manifest=context.manifest_spec,
            execution_plan=context.execution_plan,
        )
        is True
    )


def test_schema_less_chain_has_no_edge_mismatches(action_registry) -> None:
    engine = MetaCompiler(registry=action_registry)
    context = engine.compile_sync(chain_manifest())
    assert context.diagnostics == []
