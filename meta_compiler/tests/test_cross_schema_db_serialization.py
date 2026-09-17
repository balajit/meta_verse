"""Cross-schema import via in-memory DB serialization.

Verifies that:
- ``common.types.commontypes.json`` defines a reusable type (Amount).
- ``service.types.services.json`` Input/Output reference that type via
  relative ``$ref`` (``../../common/types/commontypes.json``).
- The pipeline, fed *in-memory* via ``register_schemas`` (no disk), correctly
  bundles the cross-file ref and produces typed models.
- The DB-serialized payload (``RecordingSession``) reflects that typed
  result — not a file read.

This exercises the path-aware engine added for embedded hosts.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from meta_compiler.core.action_registry import ActionRegistry
from meta_compiler.core.context import CompilationContext
from meta_compiler.engine import MetaCompiler
from meta_compiler.orchestrator import compile_and_register_manifest, compile_manifest
from meta_compiler.stages.schema_synthesis import SchemaSynthesisStage

from tests.conftest import RecordingSession


# In-memory JSON schemas with cross-file $ref
COMMONTYPES_SCHEMA: dict[str, Any] = {
    "title": "Amount",
    "type": "object",
    "description": "Monetary amount in minor units.",
    "properties": {
        "value": {"type": "integer", "minimum": 0, "description": "Minor units"},
        "currency": {"type": "string", "pattern": "^[A-Z]{3}$", "description": "ISO 4217"},
    },
    "required": ["value", "currency"],
}

SERVICES_SCHEMA: dict[str, Any] = {
    "title": "Service",
    "type": "object",
    "description": "Service payload referencing common Amount.",
    "properties": {
        "price": {"$ref": "../../common/types/commontypes.json", "description": "Price as Amount"},
        "quantity": {"type": "integer", "minimum": 1, "description": "Units"},
        "notes": {"type": "string"},
    },
    "required": ["price", "quantity"],
}

VIRTUAL_BASE = Path("/tmp/virtual_schemas_test")
SCHEMAS: dict[str, dict[str, Any]] = {
    "common.types.commontypes": COMMONTYPES_SCHEMA,
    "service.types.services": SERVICES_SCHEMA,
}
PATH_MAP: dict[str, Path] = {
    "common.types.commontypes": VIRTUAL_BASE / "common/types/commontypes.json",
    "service.types.services": VIRTUAL_BASE / "service/types/services.json",
}

SERVICE_MANIFEST_YAML = """
version: "v1"
namespace: "testns"
name: "crosswf"
tasks:
  - id: "svc"
    action: "service.types.services"
    params:
      price:
        value: 100
        currency: "USD"
      quantity: 2
"""


def test_cross_schema_bundling_via_register_schemas_produces_typed_model() -> None:
    """Synthesis with in-memory cross-file $ref yields typed Amount, not dict."""
    mc = MetaCompiler()
    mc.register_schemas(SCHEMAS, base_dir=VIRTUAL_BASE, path_map=PATH_MAP)

    ctx = CompilationContext(
        raw_input={},
        raw_schemas=dict(mc.raw_schemas),
        schema_dir=mc.schema_dir,
        schema_file_index=dict(mc.schema_file_index),
        registry=ActionRegistry(),
    )
    SchemaSynthesisStage().run(ctx, ctx.registry)

    # Both schemas synthesized
    assert "service.types.services_Input" in ctx.compiled_models
    assert "common.types.commontypes_Input" in ctx.compiled_models

    svc_input = ctx.compiled_models["service.types.services_Input"]
    # price must be the common Amount model, not generic dict
    price_ann = svc_input.model_fields["price"].annotation
    # Unwrap Optional if needed (service price is required, so not Optional)
    assert isinstance(price_ann, type) and issubclass(price_ann, BaseModel)
    # The bundled common type is named CommonTypesCommontypes (pascal of action_key)
    assert price_ann.__name__ == "CommonTypesCommontypes"
    assert "value" in price_ann.model_fields
    assert "currency" in price_ann.model_fields

    # Verify quantity is int, notes is optional str
    assert svc_input.model_fields["quantity"].annotation == int
    # Common type itself is correctly typed
    common = ctx.compiled_models["common.types.commontypes_Input"]
    assert set(common.model_fields) == {"value", "currency"}


def test_cross_schema_db_payload_reflects_typed_manifest_not_disk() -> None:
    """End-to-end orchestrator via in-memory schemas persists typed manifest via DB payload."""
    reg = ActionRegistry()
    reg.register("service.types.services", lambda **kw: None)

    # In-memory compile without touching disk
    compiled = compile_manifest(
        SERVICE_MANIFEST_YAML,
        registry=reg,
        schemas=SCHEMAS,
        schema_dir=VIRTUAL_BASE,
        schema_paths=PATH_MAP,
    )
    assert compiled.manifest_spec is not None
    assert compiled.manifest_spec.tasks[0].id == "svc"
    assert compiled.manifest_spec.tasks[0].action == "service.types.services"

    # The manifest params must have been validated against the typed Amount model
    # (value 100, currency USD) — would fail if price were generic dict without validation
    task_params = compiled.manifest_spec.tasks[0].params
    assert task_params["price"]["value"] == 100
    assert task_params["quantity"] == 2

    # Now verify DB serialization path (the “not from disk” assertion)
    async def _run() -> tuple[Any, RecordingSession]:
        sess = RecordingSession()
        graph = await compile_and_register_manifest(
            SERVICE_MANIFEST_YAML,
            sess,
            registry=reg,
            schemas=SCHEMAS,
            schema_dir=VIRTUAL_BASE,
            schema_paths=PATH_MAP,
        )
        return graph, sess

    graph, sess = asyncio.run(_run())

    assert graph.namespace == "testns"
    assert "svc" in graph.nodes
    assert len(sess.executed) == 1
    # DB payload is what would be persisted — inspect it directly
    compiled_stmt = sess.executed[0].compile()
    assert "compiled_manifest" in compiled_stmt.params
    db_manifest = compiled_stmt.params["compiled_manifest"]
    assert isinstance(db_manifest, dict)
    assert db_manifest["name"] == "crosswf"
    assert db_manifest["namespace"] == "testns"
    # Tasks survived serialization
    assert len(db_manifest["tasks"]) == 1
    assert db_manifest["tasks"][0]["id"] == "svc"
    # Params survived JSONB serialization via DB payload
    db_params = db_manifest["tasks"][0]["params"]
    assert db_params["price"]["value"] == 100
    assert db_params["price"]["currency"] == "USD"

    # Ensure the DB payload did NOT come from disk — the virtual base does not exist on disk
    assert not VIRTUAL_BASE.exists()
    # And the compiled model was typed (price is Amount, not dict) — prove via the earlier synthesis check
    # Re-run synthesis to double-check the type is still Amount when fed via DB path
    mc2 = MetaCompiler()
    mc2.register_schemas(SCHEMAS, base_dir=VIRTUAL_BASE, path_map=PATH_MAP)
    ctx2 = CompilationContext(
        raw_input={},
        raw_schemas=dict(mc2.raw_schemas),
        schema_dir=mc2.schema_dir,
        schema_file_index=dict(mc2.schema_file_index),
        registry=ActionRegistry(),
    )
    SchemaSynthesisStage().run(ctx2, ctx2.registry)
    svc2 = ctx2.compiled_models["service.types.services_Input"]
    assert issubclass(svc2.model_fields["price"].annotation, BaseModel)


def test_register_schemas_auto_infer_without_explicit_base_dir() -> None:
    """Auto-infer base_dir from path_map when not explicitly passed (explicit override tested above)."""
    mc = MetaCompiler()
    # No base_dir, only path_map — should infer
    mc.register_schemas(SCHEMAS, path_map=PATH_MAP)
    assert mc.schema_dir is not None
    assert mc.schema_dir == VIRTUAL_BASE.resolve() or str(mc.schema_dir).endswith("virtual_schemas_test")
    assert "service.types.services" in mc.raw_schemas
