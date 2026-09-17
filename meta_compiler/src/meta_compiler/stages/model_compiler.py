"""Dynamic model compiler module for meta_compiler core.

Translates raw manifest structures into typed runtime Pydantic objects
and provides dynamic boundary model synthesis using datamodel-code-generator,
full JSON Schema validation, thread-safe action registration, and structured observability telemetry.
"""

import functools
import hashlib
import importlib.util
import json
import logging
import operator
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import jsonschema
from datamodel_code_generator import DataModelType, InputFileType, generate
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, ConfigDict, ValidationError, create_model

from meta_compiler.core.action_registry import ActionRegistry
from meta_compiler.core.context import CompilationContext
from meta_compiler.core.models import (
    ArtifactRefSpec,
    TaskNodeSpec,
    WorkflowManifestSpec,
)
from meta_compiler.core.telemetry import get_tracer
from meta_compiler.exceptions import ContractValidationError, ModelCompilationError
from meta_compiler.stages.adapter_synthesizer import AdapterSynthesizerStage
from meta_compiler.stages.base import BaseCompilerStage
from meta_compiler.stages.common import CompiledArtifacts
from meta_compiler.stages.contract_checker import ContractCheckerStage
from meta_compiler.stages.db_serializer import to_db_payload
from meta_compiler.stages.syntax_guard import parse_and_validate_yaml
from meta_compiler.stages.topology_validator import validate_topology

__all__ = ["EntityModelCompiler", "CompiledArtifacts", "ModelCompilationError"]

logger = logging.getLogger("meta_compiler.stages.model_compiler")
tracer = get_tracer("meta_compiler.stages.model_compiler")
_DYNAMIC_MODULE_LOCK = threading.RLock()

PRIMITIVE_TYPE_MAP: dict[str, type[Any]] = {
    "string": str,
    "str": str,
    "integer": int,
    "int": int,
    "float": float,
    "number": float,
    "boolean": bool,
    "bool": bool,
    "datetime": datetime,
    "uuid": UUID,
    "json": dict,
    "dict": dict,
    "object": dict,
    "array": list,
    "list": list,
}


def _resolve_python_type(
    raw_type: Any,
    compiled_models: dict[str, type[BaseModel]],
    *,
    entity: str | None = None,
    field: str | None = None,
) -> type[Any]:
    """Resolves raw field type declarations to concrete Python or Pydantic types safely.

    Fails closed: an unknown declared type raises :class:`ModelCompilationError`
    instead of silently degrading to ``typing.Any``.

    Supports primitives, compiled domain models, and common generic/union
    declarations (``Optional[X]``, ``List[X]``, ``X | Y``, ``X | None``).
    """
    if isinstance(raw_type, type):
        return raw_type

    if hasattr(raw_type, "value"):
        raw_type = raw_type.value

    type_str = str(raw_type).strip()

    resolved = _resolve_union_type_str(type_str, compiled_models)
    if resolved is not None:
        return resolved

    if type_str.lower() in PRIMITIVE_TYPE_MAP:
        result = PRIMITIVE_TYPE_MAP[type_str.lower()]
        logger.debug(
            "Resolved primitive type '%s' -> %s",
            type_str,
            result.__name__,
            extra={"context": {"event": "type_resolution.primitive", "type_str": type_str}},
        )
        return result

    if type_str in compiled_models:
        result = compiled_models[type_str]
        logger.debug(
            "Resolved domain entity type '%s' -> %s",
            type_str,
            result.__name__,
            extra={"context": {"event": "type_resolution.domain_model", "type_str": type_str}},
        )
        return result

    logger.error(
        "Cannot resolve type '%s'%s%s; failing closed",
        type_str,
        f" for entity '{entity}'" if entity else "",
        f".[{field}]" if field else "",
        extra={
            "context": {
                "event": "type_resolution.fail_closed",
                "entity": entity,
                "field": field,
                "declared_type": type_str,
            }
        },
    )
    raise ModelCompilationError(
        f"Cannot resolve declared type '{type_str}'"
        + (f" for entity '{entity}'" if entity else "")
        + (f" field '{field}'" if field else ""),
        model_name=entity,
        details={"entity": entity, "field": field, "declared_type": type_str},
    )


def _resolve_union_type_str(
    type_str: str, compiled_models: dict[str, type[BaseModel]]
) -> type[Any] | None:
    """Parses generic/union type strings into concrete Python types.

    Returns ``None`` when the string does not encode a generic/union construct,
    signalling the caller to fall through to simple primitive/model lookups.
    """
    stripped = type_str.strip()

    # Optional[X] / List[X] / Dict[str, X] / typing.X forms
    for wrapper_token, resolver in (
        ("Optional[", _unwrap_single_arg),
        ("List[", _unwrap_single_arg),
        ("list[", _unwrap_single_arg),
        ("Dict[", _unwrap_two_arg),
        ("dict[", _unwrap_two_arg),
        ("typing.Optional[", _unwrap_single_arg),
    ):
        if stripped.startswith(wrapper_token) and stripped.endswith("]"):
            inner = resolver(stripped, wrapper_token)
            if inner is None:
                continue
            resolved_inner: Any = _resolve_or_any(inner, compiled_models)
            if wrapper_token in ("Optional[", "typing.Optional["):
                return resolved_inner | None
            if wrapper_token in ("List[", "list["):
                return list[resolved_inner]  # type: ignore[valid-type]
            # Dict[K, V]
            return dict[str, resolved_inner]  # type: ignore[valid-type]

    # PEP 604 union syntax: X | Y | None
    if "|" in stripped:
        parts = [part.strip() for part in stripped.split("|")]
        resolved_parts: list[type[Any]] = []
        for part in parts:
            if part.lower() in ("none", "null"):
                resolved_parts.append(type(None))
                continue
            part_type = _resolve_or_any(part, compiled_models)
            resolved_parts.append(part_type)
        union: Any = resolved_parts[0]
        for part_type in resolved_parts[1:]:
            union = union | part_type
        return union

    return None


def _unwrap_single_arg(stripped: str, token: str) -> str | None:
    inner = stripped[len(token) : -1]
    return inner.strip() if inner else None


def _unwrap_two_arg(stripped: str, token: str) -> str | None:
    inner = stripped[len(token) : -1]
    parts = [p.strip() for p in inner.split(",")]
    if len(parts) != 2:
        return None
    return parts[1].strip()


def _resolve_or_any(type_str: str, compiled_models: dict[str, type[BaseModel]]) -> type[Any]:
    """Resolves an inner generic component to a concrete type, failing closed."""
    trimmed = type_str.strip()
    if trimmed.lower() in PRIMITIVE_TYPE_MAP:
        return PRIMITIVE_TYPE_MAP[trimmed.lower()]
    if trimmed in compiled_models:
        return compiled_models[trimmed]
    if trimmed in ("Any", "any"):
        return Any
    resolved = _resolve_union_type_str(trimmed, compiled_models)
    if resolved is not None:
        return resolved
    raise ModelCompilationError(
        f"Cannot resolve generic component type '{trimmed}'",
        details={"declared_type": trimmed},
    )


def generate_model_source_code_from_schema(json_schema_input: str | dict[str, Any]) -> str:
    """Generates enterprise-grade Pydantic V2 code using datamodel-code-generator.

    Handles field constraints, aliases, schema composition (allOf/oneOf/anyOf),
    standalone Enums, docstrings, and tree-shaken import statements.
    """
    with tracer.start_as_current_span("generate_model_source_code_from_schema") as span:
        schema_str = (
            json.dumps(json_schema_input)
            if isinstance(json_schema_input, dict)
            else json_schema_input
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "generated_models.py"

            try:
                generate(
                    schema_str,
                    input_file_type=InputFileType.JsonSchema,
                    output_model_type=DataModelType.PydanticV2BaseModel,
                    output=output_path,
                    use_field_description=True,
                    use_double_quotes=True,
                    use_standard_collections=True,
                    use_union_operator=True,
                    use_annotated=True,
                    field_constraints=True,
                    snake_case_field=True,
                    use_title_as_name=True,
                    reuse_model=True,
                )

                generated_code = output_path.read_text(encoding="utf-8")

                logger.info(
                    "Successfully generated Pydantic source code via datamodel-code-generator",
                    extra={
                        "context": {
                            "event": "source_code.generate_success",
                            "char_count": len(generated_code),
                        }
                    },
                )
                span.set_status(Status(StatusCode.OK))
                return generated_code
            except Exception as err:
                span.record_exception(err)
                span.set_status(Status(StatusCode.ERROR, str(err)))
                logger.error(
                    "Failed to generate model source code from JSON Schema: %s",
                    err,
                    exc_info=True,
                    extra={
                        "context": {
                            "event": "source_code.generate_failure",
                            "error": str(err),
                        }
                    },
                )
                raise ModelCompilationError(
                    f"datamodel-codegen failed to process schema: {err}",
                    details={"schema": json_schema_input},
                ) from err


def generate_model_source_code(models: dict[str, type[BaseModel]]) -> str:
    """Adapter function maintaining backward compatibility while utilizing JSON Schema conversion."""
    synthetic_properties: dict[str, Any] = {}

    for model_name, model_cls in models.items():
        synthetic_properties[model_name] = model_cls.model_json_schema()

    synthetic_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "GeneratedDomainModels",
        "type": "object",
        "properties": synthetic_properties,
    }

    return generate_model_source_code_from_schema(synthetic_schema)


class ModelCompilerStage(BaseCompilerStage):
    """Stage 2 Adapter: Dynamic Pydantic runtime model compilation."""

    def run(self, context: CompilationContext, registry: ActionRegistry) -> None:
        with tracer.start_as_current_span("ModelCompilerStage.run") as span:
            span.set_attribute("context.id", str(context.context_id))
            logger.debug(
                "Executing ModelCompilerStage for context %s",
                context.context_id,
                extra={
                    "context": {
                        "event": "stage.model_compiler.start",
                        "context_id": str(context.context_id),
                    }
                },
            )
            try:
                context.registry = registry
                raw_dict = context.raw_input if isinstance(context.raw_input, dict) else {}

                if "entities" in raw_dict and raw_dict["entities"]:
                    compiler = EntityModelCompiler()
                    domain_models = compiler.compile_domain_models(raw_dict["entities"])

                    context.compiled_models.update(domain_models)
                    context.register_compiled_models()

                    context.metadata["domain_models"] = domain_models
                    context.metadata["domain_model_names"] = list(domain_models.keys())
                    context.metadata["compiled_models"] = context.compiled_models

                if raw_dict.get("tasks"):
                    context.manifest_spec = compile_runtime_models(context)
                    if context.manifest_spec:
                        context.metadata["task_count"] = len(context.manifest_spec.tasks)
                        context.metadata["task_ids"] = [t.id for t in context.manifest_spec.tasks]

                span.set_status(Status(StatusCode.OK))
            except Exception as err:
                span.record_exception(err)
                span.set_status(Status(StatusCode.ERROR, str(err)))
                logger.error(
                    "ModelCompilerStage execution failed: %s",
                    err,
                    exc_info=True,
                    extra={
                        "context": {
                            "event": "stage.model_compiler.failure",
                            "context_id": str(context.context_id),
                            "error": str(err),
                        }
                    },
                )
                raise


def _load_and_register_custom_types(custom_types_path: Path, registry: ActionRegistry) -> None:
    """Dynamically loads generated Pydantic models from disk into the ActionRegistry safely."""
    with tracer.start_as_current_span("_load_and_register_custom_types") as span:
        resolved_path = custom_types_path.resolve()
        span.set_attribute("custom_types.path", str(resolved_path))
        logger.debug(
            "Attempting to load custom dynamic types from path: '%s'",
            resolved_path,
            extra={
                "context": {
                    "event": "custom_types.load_start",
                    "path": str(resolved_path),
                }
            },
        )
        if not resolved_path.is_file() or resolved_path.suffix != ".py":
            logger.warning(
                "Custom types path '%s' is invalid or not a Python file.",
                resolved_path,
                extra={
                    "context": {
                        "event": "custom_types.invalid_path",
                        "path": str(resolved_path),
                    }
                },
            )
            span.set_status(Status(StatusCode.OK))
            return

        module_name = f"generated_types_{resolved_path.stem}_{hashlib.sha256(str(resolved_path).encode()).hexdigest()[:8]}"

        with _DYNAMIC_MODULE_LOCK:
            spec = importlib.util.spec_from_file_location(module_name, resolved_path)
            if not spec or not spec.loader:
                err_msg = f"Failed to create module spec for path '{resolved_path}'"
                span.set_status(Status(StatusCode.ERROR, err_msg))
                raise ModelCompilationError(err_msg)

            registered_count = 0
            try:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, BaseModel)
                        and attr is not BaseModel
                    ):
                        action_key = attr_name.lower()
                        if not registry.has_action(action_key):
                            registry.register(
                                action_name=action_key,
                                callable_func=lambda **kwargs: kwargs,
                                input_schema=attr,
                                output_schema=attr,
                            )
                            registered_count += 1
                            logger.debug(
                                "Registered custom dynamic model action '%s' from module class '%s'",
                                action_key,
                                attr_name,
                                extra={
                                    "context": {
                                        "event": "custom_types.action_registered",
                                        "action_key": action_key,
                                        "class_name": attr_name,
                                    }
                                },
                            )
                        else:
                            logger.debug(
                                "Skipped registering action '%s': already present in ActionRegistry",
                                action_key,
                                extra={
                                    "context": {
                                        "event": "custom_types.action_skipped",
                                        "action_key": action_key,
                                    }
                                },
                            )
                span.set_attribute("custom_types.registered_count", registered_count)
                span.set_status(Status(StatusCode.OK))
            except Exception as err:
                sys.modules.pop(module_name, None)
                span.record_exception(err)
                span.set_status(Status(StatusCode.ERROR, str(err)))
                logger.error(
                    "Failed to execute dynamic custom types module at '%s': %s",
                    resolved_path,
                    err,
                    extra={
                        "context": {
                            "event": "custom_types.execution_failure",
                            "path": str(resolved_path),
                            "error": str(err),
                        }
                    },
                )
                raise ModelCompilationError(
                    f"Failed to execute custom types module '{resolved_path}': {err}"
                ) from err
            finally:
                sys.modules.pop(module_name, None)

        logger.info(
            "Registered %d custom types from '%s'",
            registered_count,
            resolved_path,
            extra={
                "context": {
                    "event": "custom_types.registered",
                    "path": str(resolved_path),
                    "count": registered_count,
                }
            },
        )


class EntityModelCompiler:
    """Internal domain entity and dynamic artifact model compilation engine."""

    def compile_domain_models(self, entities: dict[str, Any]) -> dict[str, type[BaseModel]]:
        """Dynamically compiles entity AST dictionaries into runtime Pydantic BaseModel classes."""
        with tracer.start_as_current_span("EntityModelCompiler.compile_domain_models") as span:
            start_time = time.perf_counter()
            span.set_attribute("domain_models.entity_count", len(entities))
            logger.info(
                "Compiling dynamic domain models for %d entities: %s",
                len(entities),
                list(entities.keys()),
                extra={
                    "context": {
                        "event": "domain_models.compile_start",
                        "entity_count": len(entities),
                        "entities": list(entities.keys()),
                    }
                },
            )
            compiled_models: dict[str, type[BaseModel]] = {}

            for entity_name, entity_def in entities.items():
                if not isinstance(entity_def, dict):
                    logger.warning(
                        "Skipping non-dict entity definition for '%s'",
                        entity_name,
                        extra={
                            "context": {
                                "event": "domain_models.skip_non_dict",
                                "entity_name": entity_name,
                            }
                        },
                    )
                    continue

                fields: dict[str, Any] = {}
                attributes = entity_def.get("attributes", {})

                attr_items = (
                    attributes.items()
                    if isinstance(attributes, dict)
                    else [
                        (attr.get("name", f"field_{idx}"), attr)
                        for idx, attr in enumerate(attributes)
                        if isinstance(attr, dict)
                    ]
                )

                logger.debug(
                    "Processing entity '%s' with %d attribute fields",
                    entity_name,
                    len(attr_items),
                    extra={
                        "context": {
                            "event": "domain_models.entity_start",
                            "entity_name": entity_name,
                            "field_count": len(attr_items),
                        }
                    },
                )

                for field_name, attr_spec in attr_items:
                    if not isinstance(attr_spec, dict):
                        if hasattr(attr_spec, "model_dump"):
                            attr_spec = attr_spec.model_dump(mode="json")
                        else:
                            continue

                    raw_type = attr_spec.get("data_type") or attr_spec.get("type", "string")
                    python_type = _resolve_python_type(
                        raw_type,
                        compiled_models,
                        entity=entity_name,
                        field=field_name,
                    )

                    is_nullable = attr_spec.get("nullable", True)
                    default_val = attr_spec.get("default_value")

                    if is_nullable:
                        target_type = python_type | None if python_type is not Any else Any
                        field_default = None if default_val is None else default_val
                        fields[field_name] = (target_type, field_default)
                    else:
                        field_default = ... if default_val is None else default_val
                        fields[field_name] = (python_type, field_default)

                    logger.debug(
                        "Synthesized field '%s.%s': type=%s, nullable=%s, default=%s",
                        entity_name,
                        field_name,
                        python_type,
                        is_nullable,
                        field_default,
                        extra={
                            "context": {
                                "event": "domain_models.field_synthesized",
                                "entity": entity_name,
                                "field": field_name,
                                "resolved_type": str(python_type),
                                "nullable": is_nullable,
                            }
                        },
                    )

                model_class = create_model(
                    entity_name,
                    __config__=ConfigDict(extra="ignore", frozen=True),
                    **fields,
                )
                compiled_models[entity_name] = model_class

            duration_ms = (time.perf_counter() - start_time) * 1000
            span.set_attribute("domain_models.duration_ms", duration_ms)
            span.set_status(Status(StatusCode.OK))
            logger.info(
                "Successfully compiled %d domain models in %.2fms",
                len(compiled_models),
                duration_ms,
                extra={
                    "context": {
                        "event": "domain_models.compile_success",
                        "duration_ms": duration_ms,
                        "model_count": len(compiled_models),
                        "compiled_keys": list(compiled_models.keys()),
                    }
                },
            )
            return compiled_models

    def compile(
        self,
        manifest_input: str | dict[str, Any] | BaseModel,
        registry: ActionRegistry | None = None,
        custom_types_module: Path | None = None,
    ) -> CompiledArtifacts:
        """Executes multi-stage compilation from raw input to validated artifacts with rewind support."""
        with tracer.start_as_current_span("EntityModelCompiler.compile") as span:
            start_time = time.perf_counter()

            if isinstance(manifest_input, BaseModel):
                raw_dict = manifest_input.model_dump(mode="json")
            elif isinstance(manifest_input, dict):
                raw_dict = dict(manifest_input)
            elif isinstance(manifest_input, str):
                raw_dict = parse_and_validate_yaml(manifest_input)
            else:
                err_msg = f"Unsupported manifest input type: {type(manifest_input).__name__}"
                span.set_status(Status(StatusCode.ERROR, err_msg))
                raise ModelCompilationError(
                    err_msg,
                    details={"received_type": type(manifest_input).__name__},
                )

            if custom_types_module:
                raw_dict["custom_types_module"] = str(custom_types_module)

            context = CompilationContext(
                raw_input=raw_dict,
                registry=registry or ActionRegistry(),
            )
            span.set_attribute("context.id", str(context.context_id))

            if "entities" in raw_dict and raw_dict["entities"]:
                domain_models = self.compile_domain_models(raw_dict["entities"])
                context.compiled_models.update(domain_models)
                context.register_compiled_models()
                context.metadata["domain_models"] = domain_models
                context.metadata["domain_model_names"] = list(domain_models.keys())
                context.metadata["compiled_models"] = context.compiled_models

            if custom_types_module:
                _load_and_register_custom_types(custom_types_module, context.registry)

            has_tasks = bool(raw_dict.get("tasks"))
            span.set_attribute("compilation.has_tasks", has_tasks)

            if has_tasks:
                while True:
                    with tracer.start_as_current_span(
                        "EntityModelCompiler.compile_iteration"
                    ) as loop_span:
                        loop_span.set_attribute("iteration.pass", context.reprocess_counter)
                        logger.debug(
                            "Executing compilation iteration pass %d (max attempts: %d)",
                            context.reprocess_counter,
                            context.max_reprocess_attempts,
                            extra={
                                "context": {
                                    "event": "compilation.loop_iteration",
                                    "reprocess_counter": context.reprocess_counter,
                                    "max_attempts": context.max_reprocess_attempts,
                                }
                            },
                        )
                        context.manifest_spec = compile_runtime_models(context)
                        _, context.execution_plan = validate_topology(context.manifest_spec)

                        ContractCheckerStage().run(context=context, registry=context.registry)

                        if not context.requires_reprocessing:
                            logger.info(
                                "Contract validation passed cleanly on iteration %d; proceeding to serialization.",
                                context.reprocess_counter,
                                extra={
                                    "context": {
                                        "event": "compilation.contracts_valid",
                                        "iteration": context.reprocess_counter,
                                    }
                                },
                            )
                            loop_span.set_status(Status(StatusCode.OK))
                            break

                        if context.diagnostics:
                            loop_span.set_attribute(
                                "iteration.mismatches_found", len(context.diagnostics)
                            )
                            logger.info(
                                "Iteration %d recorded %d contract mismatches; executing AdapterSynthesizerStage",
                                context.reprocess_counter,
                                len(context.diagnostics),
                                extra={
                                    "context": {
                                        "event": "compilation.rewind_adapter_triggered",
                                        "mismatch_count": len(context.diagnostics),
                                        "iteration": context.reprocess_counter,
                                    }
                                },
                            )
                            AdapterSynthesizerStage().run(
                                context=context, registry=context.registry
                            )
                            context.diagnostics.clear()

                        if context.reprocess_counter >= context.max_reprocess_attempts:
                            err_msg = f"Pipeline failed to converge after {context.max_reprocess_attempts} reprocess attempts."
                            loop_span.set_status(Status(StatusCode.ERROR, err_msg))
                            logger.error(
                                "Compilation loop failed to converge after %d attempts",
                                context.max_reprocess_attempts,
                                extra={
                                    "context": {
                                        "event": "compilation.convergence_failure",
                                        "max_attempts": context.max_reprocess_attempts,
                                    }
                                },
                            )
                            raise ContractValidationError(err_msg)

                        context.reprocess_counter += 1
                        context.requires_reprocessing = False
                        loop_span.set_status(Status(StatusCode.OK))

                context.db_payload = to_db_payload(compiled_def=context.manifest_spec)
            else:
                logger.info(
                    "Manifest contains no task nodes; skipping DAG topology and contract checks.",
                    extra={
                        "context": {
                            "event": "compilation.no_tasks_skip",
                        }
                    },
                )
                try:
                    context.manifest_spec = compile_runtime_models(context)
                except ModelCompilationError:
                    context.manifest_spec = WorkflowManifestSpec(
                        version=str(raw_dict.get("version", "1.0.0")),
                        namespace=str(raw_dict.get("namespace", "default")),
                        name=str(raw_dict.get("name", "unnamed_workflow")),
                        entities=raw_dict.get("entities", {}),
                        fsms=raw_dict.get("fsms", {}),
                    )
                context.db_payload = {
                    "entities": raw_dict.get("entities", {}),
                    "fsms": raw_dict.get("fsms", {}),
                }

            duration_ms = (time.perf_counter() - start_time) * 1000
            span.set_attribute("compilation.duration_ms", duration_ms)
            span.set_status(Status(StatusCode.OK))
            logger.info(
                "Manifest compilation pipeline completed successfully in %.2fms",
                duration_ms,
                extra={
                    "context": {
                        "event": "compilation.pipeline_success",
                        "duration_ms": duration_ms,
                        "has_tasks": has_tasks,
                        "node_count": len(context.manifest_spec.tasks)
                        if context.manifest_spec
                        else 0,
                    }
                },
            )

            return CompiledArtifacts(
                manifest_spec=context.manifest_spec,
                execution_order=context.execution_plan,
                db_payload=context.db_payload,
                compiled_models=context.compiled_models,
            )


def compile_runtime_models(
    context_or_dict: CompilationContext | dict[str, Any],
) -> WorkflowManifestSpec:
    """Materializes typed runtime Pydantic models from CompilationContext or raw dictionary."""
    with tracer.start_as_current_span("compile_runtime_models") as span:
        logger.debug(
            "Compiling runtime Pydantic models from input",
            extra={"context": {"event": "runtime_models.start"}},
        )

        raw_dict = (
            context_or_dict.raw_input
            if isinstance(context_or_dict, CompilationContext)
            else context_or_dict
        )

        # Prefer the current compiled manifest during reprocess iterations so
        # adapter-based rewiring is preserved instead of being discarded when
        # rebuilding from the original raw input.
        if isinstance(context_or_dict, CompilationContext) and context_or_dict.manifest_spec:
            raw_dict = context_or_dict.manifest_spec.model_dump(mode="json")

        try:
            manifest_spec = WorkflowManifestSpec.model_validate(raw_dict)
            if isinstance(context_or_dict, CompilationContext):
                context_or_dict.manifest_spec = manifest_spec

            span.set_attribute("manifest.namespace", manifest_spec.namespace)
            span.set_attribute("manifest.name", manifest_spec.name)
            span.set_attribute("manifest.task_count", len(manifest_spec.tasks))

            logger.info(
                "Successfully compiled runtime spec for workflow '%s/%s' (%d tasks)",
                manifest_spec.namespace,
                manifest_spec.name,
                len(manifest_spec.tasks),
                extra={
                    "context": {
                        "event": "runtime_models.success",
                        "namespace": manifest_spec.namespace,
                        "manifest_spec_name": manifest_spec.name,
                        "task_count": len(manifest_spec.tasks),
                        "task_ids": [t.id for t in manifest_spec.tasks],
                    }
                },
            )
            span.set_status(Status(StatusCode.OK))
            return manifest_spec
        except ValidationError as err:
            span.record_exception(err)
            span.set_status(Status(StatusCode.ERROR, str(err)))
            logger.error(
                "Validation failure during WorkflowManifestSpec compilation: %s (errors: %s)",
                err,
                err.errors(),
                extra={
                    "context": {
                        "event": "runtime_models.validation_error",
                        "validation_errors": err.errors(),
                    }
                },
            )
            raise ModelCompilationError(
                f"Failed to compile WorkflowManifestSpec: {err}", details=err.errors()
            ) from err
        except Exception as err:
            span.record_exception(err)
            span.set_status(Status(StatusCode.ERROR, str(err)))
            logger.error(
                "Unexpected error during model compilation: %s",
                err,
                extra={
                    "context": {
                        "event": "runtime_models.unexpected_error",
                        "error_type": type(err).__name__,
                    }
                },
            )
            raise ModelCompilationError(
                f"Unexpected error during manifest compilation: {err}"
            ) from err


def compile_task_node(task_dict: dict[str, Any]) -> TaskNodeSpec:
    """Compiles a single raw dictionary definition into a validated TaskNodeSpec."""
    task_id = task_dict.get("id", "unknown")
    with tracer.start_as_current_span("compile_task_node") as span:
        span.set_attribute("task.id", task_id)
        span.set_attribute("task.action", str(task_dict.get("action", "unknown")))
        logger.debug(
            "Compiling TaskNodeSpec for task '%s' (action: %s)",
            task_id,
            task_dict.get("action", "unknown"),
            extra={
                "context": {
                    "event": "task_node.compile_start",
                    "task_id": task_id,
                    "action": task_dict.get("action"),
                }
            },
        )
        try:
            node = TaskNodeSpec.model_validate(task_dict)
            logger.debug(
                "TaskNodeSpec compiled successfully for '%s'",
                task_id,
                extra={"context": {"event": "task_node.compile_success", "task_id": task_id}},
            )
            span.set_status(Status(StatusCode.OK))
            return node
        except ValidationError as err:
            span.record_exception(err)
            span.set_status(Status(StatusCode.ERROR, str(err)))
            logger.error(
                "Validation failure compiling TaskNodeSpec for task '%s': %s",
                task_id,
                err.errors(),
                extra={
                    "context": {
                        "event": "task_node.compile_error",
                        "task_id": task_id,
                        "errors": err.errors(),
                    }
                },
            )
            raise ModelCompilationError(
                f"Failed to compile TaskNodeSpec for task '{task_id}': {err}",
                details=err.errors(),
            ) from err


def extract_task_artifact_schemas(
    node: TaskNodeSpec,
) -> dict[str, tuple[list[type[BaseModel]], list[type[BaseModel]]]]:
    """Generates dynamic runtime Pydantic boundary models for a TaskNodeSpec's inputs and outputs."""
    with tracer.start_as_current_span("extract_task_artifact_schemas") as span:
        span.set_attribute("node.id", node.id)
        span.set_attribute("node.input_count", len(node.inputs))
        span.set_attribute("node.output_count", len(node.outputs))
        logger.debug(
            "Extracting boundary artifact schemas for task node '%s' (inputs: %d, outputs: %d)",
            node.id,
            len(node.inputs),
            len(node.outputs),
            extra={
                "context": {
                    "event": "artifact_schemas.extract_start",
                    "node_id": node.id,
                    "input_refs": [ref.name for ref in node.inputs],
                    "output_refs": [ref.name for ref in node.outputs],
                }
            },
        )
        input_schemas = [build_dynamic_artifact_schema(ref) for ref in node.inputs]
        output_schemas = [build_dynamic_artifact_schema(ref) for ref in node.outputs]
        span.set_status(Status(StatusCode.OK))
        return {node.id: (input_schemas, output_schemas)}


def _generate_deterministic_class_name(ref_spec: ArtifactRefSpec) -> str:
    """Generates collision-free class identifiers using SHA-256 digests."""
    pascal_name = "".join(word.capitalize() for word in ref_spec.name.split("_"))
    raw_payload = f"{ref_spec.name}:{ref_spec.type}:{json.dumps(dict(ref_spec.schema_def or {}), sort_keys=True)}"
    digest = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()[:8]
    return f"DynamicArtifact_{pascal_name}_{digest}"


def build_dynamic_artifact_schema(
    ref_spec: ArtifactRefSpec,
) -> type[BaseModel]:
    """Synthesizes dynamic Pydantic boundary models for artifact validation."""
    class_name = _generate_deterministic_class_name(ref_spec)
    with tracer.start_as_current_span("build_dynamic_artifact_schema") as span:
        span.set_attribute("artifact.name", ref_spec.name)
        span.set_attribute("artifact.type", ref_spec.type)
        span.set_attribute("artifact.class_name", class_name)

        if not ref_spec.schema_def:
            logger.debug(
                "Building primitive artifact schema wrapper '%s' for artifact '%s' (type: '%s')",
                class_name,
                ref_spec.name,
                ref_spec.type,
                extra={
                    "context": {
                        "event": "artifact_schema.building_primitive",
                        "class_name": class_name,
                        "artifact_name": ref_spec.name,
                        "artifact_type": ref_spec.type,
                    }
                },
            )
            if ref_spec.type not in PRIMITIVE_TYPE_MAP:
                err_msg = f"Unsupported artifact primitive type '{ref_spec.type}' for artifact '{ref_spec.name}'."
                span.set_status(Status(StatusCode.ERROR, err_msg))
                logger.error(
                    "Unsupported primitive artifact type '%s' requested for '%s'",
                    ref_spec.type,
                    ref_spec.name,
                    extra={
                        "context": {
                            "event": "artifact_schema.unsupported_type",
                            "type": ref_spec.type,
                            "artifact": ref_spec.name,
                        }
                    },
                )
                raise ModelCompilationError(
                    f"{err_msg} Supported types: {sorted(PRIMITIVE_TYPE_MAP.keys())}"
                )

            target_type = PRIMITIVE_TYPE_MAP[ref_spec.type]
            span.set_status(Status(StatusCode.OK))
            return create_model(
                class_name,
                __config__=ConfigDict(extra="forbid", frozen=True),
                payload=(target_type, ...),
            )

        schema_dict = dict(ref_spec.schema_def)
        logger.debug(
            "Building object artifact schema '%s' for '%s' with %d explicit JSON schema properties",
            class_name,
            ref_spec.name,
            len(schema_dict.get("properties", {})),
            extra={
                "context": {
                    "event": "artifact_schema.building_object",
                    "class_name": class_name,
                    "artifact_name": ref_spec.name,
                    "properties": list(
                        schema_dict.get("properties", {})
                        if isinstance(schema_dict.get("properties"), dict)
                        else []
                    ),
                }
            },
        )

        try:
            jsonschema.Draft202012Validator.check_schema(schema_dict)
        except jsonschema.exceptions.SchemaError as err:
            span.record_exception(err)
            span.set_status(Status(StatusCode.ERROR, err.message))
            logger.error(
                "JSON Schema validation check failed for artifact '%s': %s",
                ref_spec.name,
                err.message,
                extra={
                    "context": {
                        "event": "artifact_schema.invalid_json_schema",
                        "artifact": ref_spec.name,
                        "error": err.message,
                    }
                },
            )
            raise ModelCompilationError(
                f"Invalid JSON Schema definition for artifact '{ref_spec.name}': {err.message}"
            ) from err

        properties = schema_dict.get("properties", {})
        if not isinstance(properties, dict):
            err_msg = f"Invalid JSON Schema 'properties' attribute for artifact '{ref_spec.name}': expected dict, got {type(properties).__name__}"
            span.set_status(Status(StatusCode.ERROR, err_msg))
            raise ModelCompilationError(err_msg)

        required_fields = (
            set(schema_dict.get("required", []))
            if isinstance(schema_dict.get("required"), list)
            else set()
        )
        fields: dict[str, Any] = {}

        for field_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict):
                logger.warning(
                    "Skipping non-dict property schema for field '%s' in artifact '%s'",
                    field_name,
                    ref_spec.name,
                    extra={
                        "context": {
                            "event": "artifact_schema.invalid_prop",
                            "field": field_name,
                            "artifact": ref_spec.name,
                        }
                    },
                )
                continue

            prop_type_name = prop_schema.get("type", "object")
            type_candidates: list[Any] = []

            if isinstance(prop_type_name, list):
                for t in prop_type_name:
                    if t == "null" or t is None:
                        type_candidates.append(type(None))
                    elif t in PRIMITIVE_TYPE_MAP:
                        type_candidates.append(PRIMITIVE_TYPE_MAP[t])
            else:
                if prop_type_name in PRIMITIVE_TYPE_MAP:
                    type_candidates.append(PRIMITIVE_TYPE_MAP[prop_type_name])
                elif prop_type_name == "null":
                    type_candidates.append(type(None))

            is_required = field_name in required_fields
            if not is_required and type(None) not in type_candidates:
                type_candidates.append(type(None))

            unique_types = list(dict.fromkeys(type_candidates))

            if not unique_types:
                field_type: Any = Any
            elif len(unique_types) == 1:
                field_type = unique_types[0]
            else:
                field_type = functools.reduce(operator.or_, unique_types)

            default_val = ... if is_required else None
            fields[field_name] = (field_type, default_val)

            logger.debug(
                "Resolved artifact field '%s.%s': type=%s, required=%s",
                class_name,
                field_name,
                field_type,
                is_required,
                extra={
                    "context": {
                        "event": "artifact_schema.field_resolved",
                        "class_name": class_name,
                        "field": field_name,
                        "required": is_required,
                    }
                },
            )

        compiled_artifact_cls = create_model(
            class_name,
            __config__=ConfigDict(extra="forbid", frozen=True),
            **fields,
        )
        logger.debug(
            "Synthesized dynamic Pydantic artifact schema class '%s' with fields %s",
            class_name,
            list(fields.keys()),
            extra={
                "context": {
                    "event": "artifact_schema.success",
                    "class_name": class_name,
                    "fields": list(fields.keys()),
                }
            },
        )
        span.set_status(Status(StatusCode.OK))
        return compiled_artifact_cls
