"""Database serializer module for meta_compiler."""

import logging
import time
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel

from meta_compiler.core.action_registry import ActionRegistry
from meta_compiler.core.context import CompilationContext
from meta_compiler.exceptions import MetaCompilerError
from meta_compiler.stages.base import BaseCompilerStage
from meta_compiler.stages.common import CompiledArtifacts

logger = logging.getLogger("meta_compiler.persistence.db_serializer")


class DBSerializerStage(BaseCompilerStage):
    """Stage 5 Adapter: JSONB payload normalization."""

    def run(self, context: CompilationContext, registry: ActionRegistry) -> None:
        logger.debug(
            "Executing DBSerializerStage for context %s",
            context.context_id,
            extra={"event": "stage.db_serializer.start", "context_id": str(context.context_id)},
        )
        target_def = context.manifest_spec or context.raw_input
        if target_def:
            context.db_payload = to_db_payload(compiled_def=target_def)
            # added for debugging purposes.
            context.metadata["db_payload"] = context.db_payload


class SerializationError(MetaCompilerError):
    """Raised when JSONB payload mapping or database serialization fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message=message, details=details)


def _dump_payload_field(field_obj: Any) -> Any:
    """Safely converts models or dictionaries into JSON-serializable structures."""
    if isinstance(field_obj, BaseModel):
        return field_obj.model_dump(mode="json")
    if isinstance(field_obj, dict):
        return field_obj
    if isinstance(field_obj, (list, tuple)):
        return [_dump_payload_field(item) for item in field_obj]
    return field_obj


def to_db_payload(
    compiled_def: CompiledArtifacts | dict[str, Any] | Any,
    id_override: UUID | None = None,
) -> dict[str, Any]:
    """Transforms compiled artifacts or workflow definitions into a DB JSONB payload map."""
    start_time = time.perf_counter()

    try:
        if hasattr(compiled_def, "manifest_spec") and hasattr(compiled_def, "execution_order"):
            manifest = compiled_def.manifest_spec
            plan = compiled_def.execution_order
        elif isinstance(compiled_def, dict):
            manifest = compiled_def.get("manifest_spec", compiled_def)
            plan = compiled_def.get("execution_order", [])
        else:
            manifest = getattr(compiled_def, "manifest_spec", compiled_def)
            plan = getattr(compiled_def, "execution_plan", [])

        namespace = getattr(manifest, "namespace", None) or (
            manifest.get("namespace") if isinstance(manifest, dict) else "default"
        )
        name = getattr(manifest, "name", None) or (
            manifest.get("name") if isinstance(manifest, dict) else "unnamed_workflow"
        )
        version = getattr(manifest, "version", None) or (
            manifest.get("version") if isinstance(manifest, dict) else "v1"
        )
        description = getattr(manifest, "description", None) or (
            manifest.get("description") if isinstance(manifest, dict) else None
        )

        compiled_manifest_data = _dump_payload_field(manifest)
        execution_plan_data = _dump_payload_field(plan)

        payload_id = id_override if id_override is not None else uuid4()
        payload = {
            "id": payload_id,
            "namespace": namespace,
            "name": name,
            "version": version,
            "description": description,
            "compiled_manifest": compiled_manifest_data,
            "execution_plan": execution_plan_data,
        }

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Successfully serialized DB payload for '%s/%s' (ID: %s) in %.2fms",
            namespace,
            name,
            payload_id,
            duration_ms,
            extra={
                "event": "db_serializer.success",
                "payload_id": str(payload_id),
                "duration_ms": duration_ms,
            },
        )
        return payload

    except Exception as err:
        logger.error(
            "Serialization failed for workflow definition: %s",
            err,
            extra={"event": "db_serializer.failure"},
        )
        raise SerializationError(
            message=f"Failed to serialize workflow definition into DB payload: {err}",
            details={"error": str(err)},
        ) from err
