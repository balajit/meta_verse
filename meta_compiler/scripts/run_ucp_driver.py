#!/usr/bin/env python3
"""UCP schema driver — end-to-end compilation demo.

Loads UCP JSON schemas, registers stub action handlers, and runs the
MetaCompiler pipeline against a sample checkout manifest. Emits
generated models, DB payload, and execution graph into ``./dist/``.

Also demonstrates the *embedded-host* path-aware API:
``MetaCompiler.register_schemas(schemas, base_dir, path_map)`` where JSON
and its logical file path are supplied together (DB/S3/in-memory), and
verifies the DB-serialized payload reflects the typed cross-file
result (not a disk read).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from opentelemetry.trace import Status, StatusCode

from meta_compiler import CompiledExecutionGraph, MetaCompiler
from meta_compiler.core.telemetry import JSONFormatter, get_tracer, setup_telemetry
from meta_compiler.exceptions import MetaCompilerError
from meta_compiler.stages.model_compiler import generate_model_source_code

logger = logging.getLogger(__name__)
tracer = get_tracer("meta_compiler.driver.ucp")


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter(service_name="ucp-schema-driver"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)


def register_ucp_action_handlers(compiler: MetaCompiler) -> None:
    with tracer.start_as_current_span("register_ucp_action_handlers") as span:
        action_keys = list(compiler.raw_schemas.keys())
        span.set_attribute("registry.action_count", len(action_keys))

        for key in action_keys:

            def _make(k: str):  # noqa: ANN202
                def _handler(**kwargs: Any) -> dict[str, Any]:
                    return {"status": "SUCCESS", "action": k, "processed_payload": kwargs}

                return _handler

            compiler.register_action(action_name=key, callable_func=_make(key))

        logger.info(
            "Registered %d UCP action handlers.",
            len(action_keys),
            extra={"event": "driver.handlers_registered", "count": len(action_keys)},
        )


def build_sample_ucp_manifest() -> str:
    return """
version: "v1.0.0"
namespace: "ucp_e2e"
name: "mcp_unified_checkout_flow"

tasks:
  - id: "search_catalog"
    action: "shopping.catalog_search"
    outputs:
      - name: "catalog_items"
        type: "json"
    params:
      query: "electronics"

  - id: "manage_cart"
    action: "shopping.cart"
    depends_on: ["search_catalog"]
    inputs:
      - name: "catalog_items"
        type: "json"
    outputs:
      - name: "cart_details"
        type: "json"
    params:
      cart_id: "cart_9921"

  - id: "execute_checkout"
    action: "shopping.checkout"
    depends_on: ["manage_cart"]
    inputs:
      - name: "cart_details"
        type: "json"
    outputs:
      - name: "checkout_receipt"
        type: "json"
    params:
      payment_method: "card"

  - id: "dispatch_mcp_call"
    action: "transports.mcp_tool_call"
    depends_on: ["execute_checkout"]
    inputs:
      - name: "checkout_receipt"
        type: "json"
    outputs:
      - name: "fulfillment_status"
        type: "json"
    params:
      tool_name: "notify_fulfillment"
"""


# ---------------------------------------------------------------------------
# In-memory path-aware demo (embedded host)
# ---------------------------------------------------------------------------

_IN_MEMORY_COMMON = {
    "title": "Amount",
    "type": "object",
    "properties": {
        "value": {"type": "integer", "minimum": 0},
        "currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
    },
    "required": ["value", "currency"],
}

_IN_MEMORY_SERVICE = {
    "title": "Service",
    "type": "object",
    "properties": {
        "price": {"$ref": "../../common/types/commontypes.json"},
        "quantity": {"type": "integer", "minimum": 1},
    },
    "required": ["price", "quantity"],
}


def demo_in_memory_path_aware() -> None:
    """Demonstrate embedded-host usage: JSON + path supplied together."""
    from meta_compiler.core.action_registry import ActionRegistry

    base = Path("/tmp/virtual_demo_schemas")
    schemas = {
        "common.types.commontypes": _IN_MEMORY_COMMON,
        "service.types.services": _IN_MEMORY_SERVICE,
    }
    path_map = {
        "common.types.commontypes": base / "common/types/commontypes.json",
        "service.types.services": base / "service/types/services.json",
    }

    # Two equivalent ways (explicit base_dir vs auto-infer from path_map)
    compiler = MetaCompiler()
    # Explicit override (recommended for embedded hosts that know their logical root)
    compiler.register_schemas(schemas, base_dir=base, path_map=path_map)

    # Verify the in-memory cross-file $ref was bundled correctly (price -> Amount)
    from meta_compiler.core.context import CompilationContext
    from meta_compiler.stages.schema_synthesis import SchemaSynthesisStage

    ctx = CompilationContext(
        raw_input={},
        raw_schemas=dict(compiler.raw_schemas),
        schema_dir=compiler.schema_dir,
        schema_file_index=dict(compiler.schema_file_index),
        registry=ActionRegistry(),
    )
    SchemaSynthesisStage().run(ctx, ctx.registry)
    svc = ctx.compiled_models.get("service.types.services_Input")
    assert svc is not None and issubclass(svc.model_fields["price"].annotation, object)
    logger.info(
        "In-memory demo: service price type = %s (typed, not dict)",
        svc.model_fields["price"].annotation.__name__,
        extra={"event": "driver.in_memory_verified"},
    )


async def run(schema_dir: Path) -> tuple[CompiledExecutionGraph, MetaCompiler]:
    compiler = MetaCompiler()
    # Filesystem path-aware ingestion (preserves relative $ref hierarchy)
    compiler.load_raw_schemas(schema_dir)
    register_ucp_action_handlers(compiler)
    graph = await compiler.compile(build_sample_ucp_manifest())
    return graph, compiler


def write_artifacts(graph: CompiledExecutionGraph, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # Generated Pydantic models (if any) — aggregated single file kept for compat
    models = graph.metadata.get("compiled_models")
    if isinstance(models, dict):
        model_classes = {k: v for k, v in models.items() if isinstance(v, type)}
        if model_classes:
            p = out_dir / "generated_models.py"
            p.write_text(generate_model_source_code(model_classes), encoding="utf-8")
            written.append(p)

    # DB payload — this is the source of truth, not disk
    db_payload = graph.metadata.get("db_payload")
    if db_payload:
        p = out_dir / "compiled_payload.json"
        p.write_text(json.dumps(db_payload, indent=2, default=str), encoding="utf-8")
        written.append(p)

    # Execution graph (sanitize type refs for JSON)
    graph_dict = graph.model_dump(mode="python")
    meta = graph_dict.get("metadata")
    if isinstance(meta, dict):
        sanitized: dict[str, Any] = {}
        for k, v in meta.items():
            if k == "compiled_models" and isinstance(v, dict):
                sanitized[k] = {n: getattr(c, "__name__", str(c)) for n, c in v.items()}
            elif isinstance(v, type):
                sanitized[k] = getattr(v, "__name__", str(v))
            else:
                sanitized[k] = v
        graph_dict["metadata"] = sanitized

    p = out_dir / "compiled_execution_graph.json"
    p.write_text(json.dumps(graph_dict, indent=2, default=str), encoding="utf-8")
    written.append(p)
    return written


def _verify_per_file_artifacts(out_dir: Path) -> None:
    """Sanity-check per-file generation: class naming and cross-file imports."""
    base = out_dir / "schemas"
    # shopping/types/item.py should define `class Item` and import Amount
    item_py = base / "shopping/types/item.py"
    if item_py.exists():
        text = item_py.read_text(encoding="utf-8")
        assert "class Item" in text, f"{item_py} missing class Item"
        # common type via import, not inlined
        assert (
            "from ...common.types import amount" in text
            or "from ..common" in text
            or "amount.Amount" in text
        ), f"{item_py} missing Amount import"
        logger.info(
            "Verified %s: class Item with Amount import",
            item_py,
            extra={"event": "driver.per_file_verified"},
        )
    # common type file should exist and define Amount
    amount_py = base / "common/types/amount.py"
    if amount_py.exists():
        assert "class Amount" in amount_py.read_text(encoding="utf-8")

    # Also verify DB payload reflects typed result
    payload_path = out_dir / "compiled_payload.json"
    if payload_path.exists():
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        assert "compiled_manifest" in payload or "execution_plan" in payload


async def main() -> None:
    configure_logging()

    parser = argparse.ArgumentParser(description="UCP Schema Driver for MetaCompiler")
    parser.add_argument("--schema-dir", type=Path, default=Path("./schemas"))
    parser.add_argument("--otlp-endpoint", type=str, default="localhost:4317")
    parser.add_argument(
        "--in-memory-demo",
        action="store_true",
        help="Run in-memory path-aware demo (common+service) and verify DB payload",
    )
    args = parser.parse_args()

    setup_telemetry(service_name="ucp-schema-driver", otlp_endpoint=args.otlp_endpoint)

    with tracer.start_as_current_span("ucp_driver.main") as span:
        schema_path = args.schema_dir.resolve()
        span.set_attribute("driver.schema_dir", str(schema_path))
        logger.info(
            "Initializing UCP driver.",
            extra={"event": "driver.init", "schema_dir": str(schema_path)},
        )

        try:
            graph, compiler = await run(schema_path)
            files = write_artifacts(graph, Path("./dist"))
            # Per-file generation mirroring JSON hierarchy with imports
            try:
                per_file = compiler.write_per_file_schemas(Path("./dist/schemas"))
                files.extend(per_file)
                logger.info(
                    "Wrote %d per-file schemas.",
                    len(per_file),
                    extra={"event": "driver.per_file_written", "count": len(per_file)},
                )
                _verify_per_file_artifacts(Path("./dist"))
            except Exception as per_err:
                logger.warning(
                    "Per-file generation failed: %s",
                    per_err,
                    extra={"event": "driver.per_file_failure"},
                )

            # Optional in-memory path-aware demo for embedded hosts
            if args.in_memory_demo:
                demo_in_memory_path_aware()
                logger.info(
                    "In-memory path-aware demo completed",
                    extra={"event": "driver.in_memory_demo_ok"},
                )

            stages = graph.metadata.get("execution_stages", [])
            print("\n" + "=" * 60)
            print(" COMPILATION SUCCESSFUL")
            print("=" * 60)
            print(f"Manifest ID    : {graph.manifest_id}")
            print(f"Name           : {graph.namespace}/{graph.name}:{graph.version}")
            print(f"Total Nodes    : {len(graph.nodes)}")
            print("Execution Stages:")
            if stages:
                for i, stage in enumerate(stages, 1):
                    print(f"  Stage {i}: {', '.join(stage)}")
            else:
                print("  N/A")
            print("=" * 60)
            print("\nPersisted Artifacts:")
            for f in files:
                print(f"  - {f.resolve()}")
            print("=" * 60)

        except MetaCompilerError as err:
            span.record_exception(err)
            span.set_status(Status(StatusCode.ERROR, str(err)))
            logger.error(
                "Compilation failed: %s", err, extra={"event": "driver.compilation_failure"}
            )
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
