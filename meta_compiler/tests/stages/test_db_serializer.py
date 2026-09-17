"""Database serializer tests: UUID end-to-end typing and payload shape."""

from uuid import UUID

from meta_compiler.engine import MetaCompiler
from meta_compiler.stages.db_serializer import to_db_payload
from tests.conftest import chain_manifest


def test_db_payload_id_is_native_uuid(action_registry) -> None:
    payload = to_db_payload(
        {
            "namespace": "ns",
            "name": "wf",
            "version": "v1",
            "description": None,
            "compiled_manifest": {"tasks": []},
            "execution_order": [],
        }
    )
    assert isinstance(payload["id"], UUID)


def test_db_payload_shape_from_context(action_registry) -> None:
    engine = MetaCompiler(registry=action_registry)
    context = engine.compile_sync(chain_manifest())

    payload = to_db_payload(context.db_payload)
    assert isinstance(payload["id"], UUID)
    assert payload["namespace"] == "ns"
    assert payload["name"] == "wf"
    assert payload["version"] == "v1"
    assert payload["compiled_manifest"]["version"] == "v1"
    assert isinstance(payload["execution_plan"], (list, dict))


def test_db_payload_from_compiled_artifacts(action_registry) -> None:
    engine = MetaCompiler(registry=action_registry)
    context = engine.compile_sync(chain_manifest())
    payload = context.db_payload
    assert "compiled_manifest" in payload
    assert "execution_plan" in payload


def test_id_override_is_honored() -> None:
    from uuid import uuid4

    fixed = uuid4()
    payload = to_db_payload(
        {"namespace": "ns", "name": "wf", "version": "v1"},
        id_override=fixed,
    )
    assert payload["id"] == fixed
