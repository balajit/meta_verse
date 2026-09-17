"""Compilation context state container for threading pipeline execution state."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel

from meta_compiler.core.action_registry import ActionRegistry
from meta_compiler.core.models import (
    CompiledExecutionGraph,
    ExecutionPlan,
    NodeExecutionMetadata,
    WorkflowManifestSpec,
)
from meta_compiler.core.telemetry import get_tracer

logger = logging.getLogger("meta_compiler.core.context")
tracer = get_tracer("meta_compiler.core.context")


@dataclass
class CompilationContext:
    """Carries state, raw schemas, dynamic models, execution plans, and flags across stages."""

    raw_input: Any
    context_id: UUID = field(default_factory=uuid4)
    record_id: UUID | None = None
    manifest_spec: WorkflowManifestSpec | None = None
    execution_plan: ExecutionPlan | None = None
    raw_schemas: dict[str, dict] = field(default_factory=dict)
    schema_dir: Path | None = None  # type: ignore[assignment]
    schema_file_index: dict[str, Path] = field(default_factory=dict)  # type: ignore[assignment]  # action_key -> Path
    db_payload: dict[str, Any] = field(default_factory=dict)
    compiled_models: dict[str, type[BaseModel]] = field(default_factory=dict)
    registry: ActionRegistry = field(default_factory=ActionRegistry)
    metadata: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[Any] = field(default_factory=list)

    # Reprocessing & Self-Healing State Flags
    requires_reprocessing: bool = False
    reprocess_counter: int = 0
    max_reprocess_attempts: int = 3

    def register_compiled_models(self) -> None:
        """Injects dynamically compiled Pydantic models directly into the ActionRegistry."""
        with tracer.start_as_current_span("CompilationContext.register_compiled_models") as span:
            span.set_attribute("context.id", str(self.context_id))
            span.set_attribute("context.model_count", len(self.compiled_models))

            logger.debug(
                "Registering %d compiled models into ActionRegistry for context %s",
                len(self.compiled_models),
                self.context_id,
                extra={"event": "context.register_models", "context_id": str(self.context_id)},
            )
            for entity_name, model_cls in self.compiled_models.items():
                action_key = entity_name.lower()
                if not self.registry.has_action(action_key):
                    self.registry.register(
                        action_name=action_key,
                        callable_func=lambda **kwargs: kwargs,
                        input_schema=model_cls,
                        output_schema=model_cls,
                    )

    def to_compiled_graph(self) -> CompiledExecutionGraph:
        """Constructs an immutable CompiledExecutionGraph artifact from context state."""
        with tracer.start_as_current_span("CompilationContext.to_compiled_graph") as span:
            span.set_attribute("context.id", str(self.context_id))

            if not self.manifest_spec:
                err_msg = f"Attempted to build CompiledExecutionGraph without manifest_spec on context {self.context_id}"
                span.set_status(Status(StatusCode.ERROR, err_msg))
                logger.error(
                    "%s",
                    err_msg,
                    extra={"event": "context.missing_manifest", "context_id": str(self.context_id)},
                )
                raise ValueError(
                    "Cannot construct CompiledExecutionGraph without a compiled manifest_spec."
                )

            dependent_node_ids: set[str] = {
                dep_id for task in self.manifest_spec.tasks for dep_id in task.depends_on
            }

            nodes: dict[str, NodeExecutionMetadata] = {}
            for task in self.manifest_spec.tasks:
                output_type_str = "None"
                if task.outputs:
                    first_out = task.outputs[0]
                    output_type_str = getattr(first_out, "type", str(first_out))

                nodes[task.id] = NodeExecutionMetadata(
                    node_id=task.id,
                    inputs=[inp.name for inp in task.inputs],
                    output_type=output_type_str,
                    is_terminal=task.id not in dependent_node_ids,
                )

            logger.info(
                "Compiled execution graph created for manifest '%s' (%d nodes)",
                self.manifest_spec.name,
                len(nodes),
                extra={"event": "context.to_graph_success", "context_id": str(self.context_id)},
            )

            return CompiledExecutionGraph(
                manifest_id=str(self.context_id),
                namespace=self.manifest_spec.namespace,
                name=self.manifest_spec.name,
                version=self.manifest_spec.version,
                nodes=nodes,
                db_record_id=str(self.record_id or "unpersisted"),
                metadata=self.metadata,
            )
