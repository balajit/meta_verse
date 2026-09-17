"""Schema synthesis tests: datamodel-code-generator consolidation path."""

from meta_compiler.core.action_registry import ActionRegistry
from meta_compiler.core.context import CompilationContext
from meta_compiler.stages.schema_synthesis import SchemaSynthesisStage


def test_synthesis_builds_input_output_models() -> None:
    context = CompilationContext(
        raw_input={},
        raw_schemas={
            "produce": {
                "type": "object",
                "properties": {"value": {"type": "integer", "minimum": 1}},
                "required": ["value"],
            }
        },
    )
    registry = ActionRegistry()
    SchemaSynthesisStage().run(context, registry)

    assert "produce_Input" in context.compiled_models
    assert "produce_Output" in context.compiled_models
    model = context.compiled_models["produce_Output"]
    assert "value" in model.model_fields
    validated = model(value=5)
    assert validated.value == 5


def test_synthesis_updates_registered_action_contracts() -> None:
    registry = ActionRegistry()
    registry.register("produce", lambda **kw: None)

    context = CompilationContext(
        raw_input={},
        raw_schemas={"produce": {"type": "object", "properties": {"x": {"type": "string"}}}},
        registry=registry,
    )
    SchemaSynthesisStage().run(context, registry)

    spec = registry.resolve("produce")
    assert spec.input_schema is not None
    assert spec.output_schema is not None


def test_synthesis_supports_all_of_composition() -> None:
    context = CompilationContext(
        raw_input={},
        raw_schemas={
            "shape": {
                "allOf": [
                    {"type": "object", "properties": {"kind": {"type": "string"}}},
                    {"type": "object", "properties": {"size": {"type": "integer"}}},
                ]
            }
        },
    )
    SchemaSynthesisStage().run(context, ActionRegistry())

    model = context.compiled_models["shape_Output"]
    assert {"kind", "size"} <= set(model.model_fields)
