"""Pipeline orchestration entrypoint."""

import logging
import time
from typing import Any

from pydantic import ValidationError

from meta_telemetry import trace_span
from meta_polymorph.domain.dtos import ManifestIR, TenantContext
from meta_polymorph.exceptions import PolymorphicCompilationError
from meta_polymorph.resolver import PolymorphicResolver

logger = logging.getLogger("meta_polymorph.pipeline")


def _extract_pipeline_attrs(params: dict[str, Any]) -> dict[str, Any]:
    context = params.get("context")
    layers = params.get("layers")
    attrs: dict[str, Any] = {}

    if isinstance(context, TenantContext):
        attrs["tenant.id"] = context.tenant_id
        attrs["tenant.industry_id"] = context.industry_id
        attrs["tenant.global_id"] = context.global_id

    if isinstance(layers, list):
        attrs["pipeline.layer_count"] = len(layers)

    return attrs


class PolymorphicPipeline:
    """Pipeline entrypoint orchestrating layer resolution into a compiled ManifestIR container."""

    @classmethod
    @trace_span(name="PolymorphicPipeline.compile_to_ir", extract_attributes=_extract_pipeline_attrs)
    def compile_to_ir(
        cls, context: TenantContext, layers: list[dict[str, Any]]
    ) -> ManifestIR:
        """Resolves pre-ordered layers and instantiates the pure ManifestIR container."""
        start_time = time.perf_counter()
        logger.info(
            "Starting ManifestIR compilation",
            extra={
                "event_type": "compilation_start",
                "tenant_id": context.tenant_id,
                "industry_id": context.industry_id,
                "layer_count": len(layers) if isinstance(layers, list) else 0,
            },
        )

        try:
            resolver = PolymorphicResolver()
            merged_data = resolver.resolve(layers)

            # Apply fallback contextual attributes if unassigned in raw layers
            merged_data.setdefault("namespace", context.tenant_id)
            merged_data.setdefault("name", f"manifest_{context.tenant_id}")

            manifest_ir = ManifestIR(**merged_data)
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "Successfully compiled ManifestIR",
                extra={
                    "event_type": "compilation_success",
                    "tenant_id": context.tenant_id,
                    "duration_ms": round(duration_ms, 2),
                    "task_count": len(manifest_ir.tasks),
                    "entity_count": len(manifest_ir.entities),
                },
            )
            return manifest_ir
        except (ValidationError, TypeError, ValueError) as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "Failed to compile ManifestIR due to schema or layer validation error",
                extra={
                    "event_type": "compilation_failure",
                    "tenant_id": context.tenant_id,
                    "duration_ms": round(duration_ms, 2),
                    "error": str(e),
                },
                exc_info=True,
            )
            raise PolymorphicCompilationError(
                message=f"Failed to compile ManifestIR for tenant '{context.tenant_id}': {e}",
                tenant_id=context.tenant_id,
                original_exception=e,
            ) from e