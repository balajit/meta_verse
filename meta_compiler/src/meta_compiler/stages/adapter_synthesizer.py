"""Adapter Synthesizer Stage for meta_compiler.

Consumes ContractMismatch diagnostics, injects dynamic AST adapter task nodes,
rewires graph dependencies, and registers runtime adapter schema transformations.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from opentelemetry.trace import Status, StatusCode

from meta_compiler.core.action_registry import ActionRegistry
from meta_compiler.core.context import CompilationContext
from meta_compiler.core.models import TaskNodeSpec, WorkflowManifestSpec
from meta_compiler.core.telemetry import get_tracer
from meta_compiler.exceptions import MetaCompilerError
from meta_compiler.stages.base import BaseCompilerStage
from meta_compiler.stages.contract_checker import ContractMismatch

logger = logging.getLogger("meta_compiler.stages.adapter_synthesizer")
tracer = get_tracer("meta_compiler.stages.adapter_synthesizer")


class AdapterSynthesisError(MetaCompilerError):
    """Raised when transformation adapter synthesis or AST rewiring fails."""

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            details=details,
        )


class AdapterSynthesizerStage(BaseCompilerStage):
    """Stage 5 Adapter: Synthesizes graph transformation adapters based on contract diagnostics."""

    def run(
        self,
        context: CompilationContext,
        registry: ActionRegistry,
    ) -> None:
        with tracer.start_as_current_span("AdapterSynthesizerStage.run") as span:
            span.set_attribute(
                "context.id",
                str(context.context_id),
            )

            logger.debug(
                "Executing AdapterSynthesizerStage for context %s",
                context.context_id,
                extra={
                    "event_type": "stage.adapter_synthesizer.start",
                    "context_id": str(context.context_id),
                },
            )

            context.registry = registry

            if context.diagnostics and context.manifest_spec is not None:
                synthesizer = AdapterSynthesizer()
                synthesizer.synthesize_adapters(context)


class AdapterSynthesizer:
    """Synthesizes immutable manifest transformations."""

    def synthesize_adapters(
        self,
        context: CompilationContext,
    ) -> None:
        """Process pending diagnostics and replace the manifest with a transformed copy."""

        manifest = context.manifest_spec

        if manifest is None:
            return

        with tracer.start_as_current_span("AdapterSynthesizer.synthesize_adapters") as span:
            start_time = time.perf_counter()
            mismatch_count = len(context.diagnostics)

            span.set_attribute(
                "adapter.mismatch_count",
                mismatch_count,
            )

            logger.info(
                "Synthesizing %d transformation adapters for workflow '%s'",
                mismatch_count,
                manifest.name,
                extra={
                    "event_type": "adapter_synthesis.start",
                    "manifest": manifest.name,
                    "count": mismatch_count,
                    "context_id": str(context.context_id),
                },
            )

            transformed_manifest = manifest

            for diagnostic in tuple(context.diagnostics):
                if isinstance(diagnostic, ContractMismatch):
                    transformed_manifest = self.inject_transformation_adapter(
                        context=context,
                        manifest=transformed_manifest,
                        mismatch=diagnostic,
                    )

            # Re-run model validators (self-dependency / duplicate-ID / unknown-dep
            # invariants) that model_copy(update=...) bypasses during rewiring.
            # Use by_alias + exclude_none so ArtifactRefSpec alias "schema" round-trips
            # correctly (see ArtifactRefSpec.populate_by_name).
            transformed_manifest = WorkflowManifestSpec.model_validate(
                transformed_manifest.model_dump(mode="json", by_alias=True, exclude_none=True)
            )

            context.manifest_spec = transformed_manifest

            duration_ms = (time.perf_counter() - start_time) * 1000

            span.set_attribute(
                "adapter.duration_ms",
                duration_ms,
            )

            logger.info(
                "Adapter synthesis completed for workflow '%s'",
                transformed_manifest.name,
                extra={
                    "event_type": "adapter_synthesis.complete",
                    "manifest": transformed_manifest.name,
                    "count": mismatch_count,
                    "duration_ms": duration_ms,
                    "context_id": str(context.context_id),
                },
            )

    def inject_transformation_adapter(
        self,
        context: CompilationContext,
        manifest: WorkflowManifestSpec,
        mismatch: ContractMismatch,
    ) -> WorkflowManifestSpec:
        """Synthesizes a single adapter task node and rewires dependency links.

        The returned manifest is a new immutable model. The original manifest
        and its task nodes are never mutated.
        """

        with tracer.start_as_current_span(
            "AdapterSynthesizer.inject_transformation_adapter"
        ) as span:
            span.set_attribute(
                "adapter.producer_id",
                mismatch.producer_id,
            )
            span.set_attribute(
                "adapter.consumer_id",
                mismatch.consumer_id,
            )

            adapter_id = f"adapter_{mismatch.producer_id}_to_{mismatch.consumer_id}"
            action_name = f"auto_adapter_{adapter_id}"

            consumer_task = next(
                (task for task in manifest.tasks if task.id == mismatch.consumer_id),
                None,
            )

            if consumer_task is None:
                error_message = (
                    "Adapter synthesis failed: consumer task "
                    f"'{mismatch.consumer_id}' not found in "
                    "manifest tasks."
                )

                span.set_status(
                    Status(
                        StatusCode.ERROR,
                        error_message,
                    )
                )

                logger.error(
                    error_message,
                    extra={
                        "event_type": "adapter_synthesis.missing_consumer",
                        "consumer_id": mismatch.consumer_id,
                        "producer_id": mismatch.producer_id,
                        "context_id": str(context.context_id),
                    },
                )

                raise AdapterSynthesisError(
                    error_message,
                    details={
                        "consumer_id": mismatch.consumer_id,
                        "producer_id": mismatch.producer_id,
                    },
                )

            if context.registry is None:
                error_message = "Action registry is unavailable during adapter synthesis."

                span.set_status(
                    Status(
                        StatusCode.ERROR,
                        error_message,
                    )
                )

                raise AdapterSynthesisError(
                    error_message,
                    details={
                        "adapter_id": adapter_id,
                        "consumer_id": mismatch.consumer_id,
                    },
                )

            adapter_node = TaskNodeSpec(
                id=adapter_id,
                action=action_name,
                depends_on=(mismatch.producer_id,),
            )

            if not context.registry.has_action(action_name):
                context.registry.register(
                    action_name=action_name,
                    callable_func=lambda data, **kwargs: data,
                    input_schema=mismatch.actual_type,
                    output_schema=mismatch.expected_type,
                )

            updated_tasks: list[TaskNodeSpec] = []

            for task in manifest.tasks:
                if task.id != consumer_task.id:
                    updated_tasks.append(task)
                    continue

                updated_dependencies = tuple(
                    adapter_id if dependency == mismatch.producer_id else dependency
                    for dependency in task.depends_on
                )

                updated_tasks.append(
                    task.model_copy(
                        update={
                            "depends_on": updated_dependencies,
                        }
                    )
                )

            updated_tasks.append(adapter_node)

            transformed_manifest = manifest.model_copy(
                update={
                    "tasks": tuple(updated_tasks),
                }
            )

            logger.debug(
                "Injected adapter node '%s' between producer '%s' and consumer '%s'",
                adapter_id,
                mismatch.producer_id,
                mismatch.consumer_id,
                extra={
                    "event_type": "adapter_synthesis.node_injected",
                    "adapter_id": adapter_id,
                    "producer_id": mismatch.producer_id,
                    "consumer_id": mismatch.consumer_id,
                    "context_id": str(context.context_id),
                },
            )

            return transformed_manifest
