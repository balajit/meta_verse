"""Schema Synthesis Stage for MetaCompiler.

Maps raw JSON Schema dicts into dynamic Pydantic BaseModel instances and updates ActionRegistry schemas.
"""

import functools
import logging
import operator
import re
from typing import Any

from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, ConfigDict, create_model

from meta_compiler.core.action_registry import ActionRegistry
from meta_compiler.core.context import CompilationContext
from meta_compiler.core.telemetry import get_tracer
from meta_compiler.exceptions import MetaCompilerError
from meta_compiler.stages.base import BaseCompilerStage
from meta_compiler.stages.model_compiler import generate_model_source_code_from_schema

logger = logging.getLogger("meta_compiler.stages.schema_synthesis")
tracer = get_tracer("meta_compiler.stages.schema_synthesis")

PRIMITIVE_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _pascal_case(name: str) -> str:
    """Normalizes a schema title into the class name datamodel-code-generator produces."""
    return "".join(part.capitalize() for part in re.split(r"[^0-9A-Za-z]+", name))


class SchemaSynthesisStage(BaseCompilerStage):
    """Pipeline stage that converts raw JSON Schema dicts into dynamic Pydantic models."""

    def run(self, context: CompilationContext, registry: ActionRegistry) -> None:
        with tracer.start_as_current_span("SchemaSynthesisStage.run") as span:
            span.set_attribute("context.id", str(context.context_id))
            context.registry = registry

            if not context.raw_schemas:
                logger.info(
                    "No raw schemas present in context %s; skipping synthesis.",
                    context.context_id,
                    extra={"event": "schema_synthesis.skip", "context_id": str(context.context_id)},
                )
                span.set_status(Status(StatusCode.OK))
                return

            span.set_attribute("synthesis.raw_schema_count", len(context.raw_schemas))
            compiled_models: dict[str, type[BaseModel]] = {}

            # Namespace-driven bundling: resolve relative $ref into $defs so codegen
            # can emit typed sub-models (ShoppingTypesBuyer) instead of dict[str,Any].
            bundler = None
            if context.schema_dir and context.schema_file_index:
                try:
                    from meta_compiler.stages.schema_bundler import SchemaBundler

                    bundler = SchemaBundler(
                        schema_dir=context.schema_dir,  # type: ignore[arg-type]
                        file_index=context.schema_file_index,  # type: ignore[arg-type]
                        raw_schemas=context.raw_schemas,
                    )
                except Exception as err:
                    logger.warning(
                        "Schema bundling unavailable, falling back to raw schemas: %s",
                        err,
                        extra={"event": "schema_synthesis.bundler_init_failed"},
                    )

            try:
                for action_key, schema_data in context.raw_schemas.items():
                    bundled = schema_data
                    if bundler is not None:
                        try:
                            bundled = bundler.bundle_for(action_key)
                        except Exception as err:
                            logger.warning(
                                "Bundling failed for '%s', using raw schema: %s",
                                action_key,
                                err,
                                extra={
                                    "event": "schema_synthesis.bundle_fallback",
                                    "action_key": action_key,
                                },
                            )
                    in_model = self._synthesize_model(action_key, bundled, "Input")
                    out_model = self._synthesize_model(action_key, bundled, "Output")

                    compiled_models[f"{action_key}_Input"] = in_model
                    compiled_models[f"{action_key}_Output"] = out_model

                    if context.registry.has_action(action_key):
                        existing_spec = context.registry.resolve(action_key)
                        context.registry.register(
                            action_name=action_key,
                            callable_func=existing_spec.callable_func,
                            input_schema=in_model,
                            output_schema=out_model,
                            version=existing_spec.version,
                            allow_override=True,
                        )

                # Safely accumulate synthesized models and write namespaced metadata
                context.compiled_models.update(compiled_models)
                context.metadata["synthesized_schema_models"] = compiled_models
                context.metadata["synthesized_schema_names"] = list(compiled_models.keys())
                context.metadata["compiled_models"] = context.compiled_models

                logger.info(
                    "Synthesized %d Pydantic models across %d schema contracts.",
                    len(compiled_models),
                    len(context.raw_schemas),
                    extra={
                        "event": "schema_synthesis.success",
                        "count": len(compiled_models),
                        "context_id": str(context.context_id),
                    },
                )
                span.set_status(Status(StatusCode.OK))

            except Exception as err:
                span.record_exception(err)
                span.set_status(Status(StatusCode.ERROR, str(err)))
                logger.error(
                    "SchemaSynthesisStage failed: %s",
                    err,
                    exc_info=True,
                    extra={
                        "event": "schema_synthesis.failure",
                        "context_id": str(context.context_id),
                    },
                )
                raise MetaCompilerError(f"SchemaSynthesisStage failed: {err}") from err

    def _synthesize_model(
        self, action_key: str, schema_data: dict, model_type: str
    ) -> type[BaseModel]:
        class_name = f"{action_key.replace('.', '_').replace('-', '_')}_{model_type}"
        try:
            return self._synthesize_with_codegen(class_name, schema_data)
        except Exception:
            logger.warning(
                "datamodel-code-generator failed for '%s'; falling back to create_model",
                class_name,
                exc_info=True,
                extra={
                    "event": "schema_synthesis.codegen_fallback",
                    "class_name": class_name,
                },
            )
            return self._fallback_create_model(class_name, schema_data)

    def _synthesize_with_codegen(self, class_name: str, schema_data: dict) -> type[BaseModel]:
        # Ensure synthesized class name takes precedence over source title
        schema_doc = {**schema_data, "title": class_name, "type": schema_data.get("type", "object")}
        generated = generate_model_source_code_from_schema(schema_doc)
        namespace: dict[str, Any] = {}
        exec(compile(generated, "<synthesized_model>", "exec"), namespace)
        generated_class = namespace.get(_pascal_case(class_name))
        if not isinstance(generated_class, type) or not issubclass(generated_class, BaseModel):
            raise MetaCompilerError(
                f"datamodel-code-generator did not emit model class '{_pascal_case(class_name)}'",
                details={
                    "generated_classes": [
                        k
                        for k, v in namespace.items()
                        if isinstance(v, type) and issubclass(v, BaseModel)
                    ]
                },
            )
        # Rebuild with exec namespace so forward refs (e.g. UcpResponseCartSchema)
        # resolve. Generated code uses `from __future__ import annotations` → string
        # annotations that need the synthetic module's namespace.
        try:
            generated_class.model_rebuild(_types_namespace=namespace)
        except Exception:
            # Fallback: rebuild without custom namespace, then try with namespace
            generated_class.model_rebuild()
        return generated_class

    def _fallback_create_model(self, class_name: str, schema_data: dict) -> type[BaseModel]:
        title = schema_data.get("title", class_name)
        fields: dict[str, Any] = {}
        properties = schema_data.get("properties", {})
        required_fields = set(schema_data.get("required", []))

        for field_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict):
                logger.warning(
                    "Skipping non-dict property schema for field '%s' in action '%s'",
                    field_name,
                    class_name,
                    extra={
                        "event": "schema_synthesis.invalid_prop",
                        "field": field_name,
                        "action": class_name,
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
                "Resolved schema field '%s.%s': type=%s, required=%s",
                class_name,
                field_name,
                field_type,
                is_required,
                extra={
                    "event": "schema_synthesis.field_resolved",
                    "class_name": class_name,
                    "field": field_name,
                    "required": is_required,
                },
            )

        return create_model(
            class_name,
            __doc__=title,
            __config__=ConfigDict(extra="ignore"),
            **fields,
        )
