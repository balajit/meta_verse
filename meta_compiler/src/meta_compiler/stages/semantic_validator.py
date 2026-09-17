"""Manifest semantic validator checking internal workflow invariants pre-graph construction."""

import logging
import time
from typing import Any

from meta_compiler.core.action_registry import ActionRegistry
from meta_compiler.core.context import CompilationContext
from meta_compiler.core.models import WorkflowManifestSpec
from meta_compiler.exceptions import MetaCompilerError
from meta_compiler.stages.base import BaseCompilerStage

logger = logging.getLogger("meta_compiler.validators.manifest_validator")


class ManifestSemanticError(MetaCompilerError):
    """Raised when intra-manifest semantic rules or artifact linkages are violated."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message=message, details=details)


class SemanticValidatorStage(BaseCompilerStage):
    """Pipeline stage running semantic invariant validation on the compiled manifest."""

    def run(self, context: CompilationContext, registry: ActionRegistry) -> None:
        manifest = context.manifest_spec
        if not isinstance(manifest, WorkflowManifestSpec) or not manifest.tasks:
            logger.debug(
                "Skipping semantic validation for context %s (no manifest tasks)",
                context.context_id,
            )
            return
        ManifestSemanticValidator().validate(manifest)


class ManifestSemanticValidator:
    """Validates intra-manifest dependencies, artifact linkage, and static contract types."""

    def validate(self, manifest: WorkflowManifestSpec) -> None:
        """Executes full semantic invariant suite on parsed WorkflowManifestSpec.

        Raises:
            ManifestSemanticError: If any semantic rule is violated.
        """
        start_time = time.perf_counter()
        logger.debug(
            "Starting semantic validation for manifest '%s/%s'",
            manifest.namespace,
            manifest.name,
            extra={
                "event": "manifest_validation.start",
                "namespace": manifest.namespace,
                "name": manifest.name,
            },
        )

        task_map = {task.id: task for task in manifest.tasks}
        task_ids = set(task_map.keys())

        # Dependency & Provenance Verification
        for task in manifest.tasks:
            # Verify explicit dependencies exist and no self-references
            for dep_id in task.depends_on:
                if dep_id not in task_ids:
                    logger.error(
                        "Task '%s' references unresolvable dependency '%s'",
                        task.id,
                        dep_id,
                        extra={
                            "event": "manifest_validation.unknown_dep",
                            "task_id": task.id,
                            "dep_id": dep_id,
                        },
                    )
                    raise ManifestSemanticError(
                        message=f"Task '{task.id}' specifies unknown dependency '{dep_id}'.",
                        details={"task_id": task.id, "missing_dependency": dep_id},
                    )
                if dep_id == task.id:
                    logger.error(
                        "Task '%s' lists self in dependencies",
                        task.id,
                        extra={"event": "manifest_validation.self_dep", "task_id": task.id},
                    )
                    raise ManifestSemanticError(
                        message=f"Task '{task.id}' cannot list itself in 'depends_on'.",
                        details={"task_id": task.id},
                    )

            # Verify input artifact sources and type bounds
            for artifact_input in task.inputs:
                if not artifact_input.source:
                    continue  # Unbound external input

                src_task_id = artifact_input.source.task_id
                src_artifact_name = artifact_input.source.artifact_name

                if src_task_id not in task_ids:
                    logger.error(
                        "Input artifact '%s' in task '%s' references missing source task '%s'",
                        artifact_input.name,
                        task.id,
                        src_task_id,
                        extra={
                            "event": "manifest_validation.missing_source_task",
                            "task_id": task.id,
                            "artifact": artifact_input.name,
                            "source_task": src_task_id,
                        },
                    )
                    raise ManifestSemanticError(
                        message=f"Input '{artifact_input.name}' in task '{task.id}' references non-existent source task '{src_task_id}'.",
                        details={
                            "task_id": task.id,
                            "artifact": artifact_input.name,
                            "source_task": src_task_id,
                        },
                    )

                src_task = task_map[src_task_id]
                src_outputs = {out.name: out for out in src_task.outputs}

                if src_artifact_name not in src_outputs:
                    logger.error(
                        "Input artifact '%s' in task '%s' references missing output artifact '%s' on task '%s'",
                        artifact_input.name,
                        task.id,
                        src_artifact_name,
                        src_task_id,
                        extra={
                            "event": "manifest_validation.missing_output_artifact",
                            "task_id": task.id,
                            "artifact": artifact_input.name,
                            "source_task": src_task_id,
                            "source_artifact": src_artifact_name,
                        },
                    )
                    raise ManifestSemanticError(
                        message=f"Input '{artifact_input.name}' in task '{task.id}' references missing output artifact '{src_artifact_name}' on task '{src_task_id}'.",
                        details={
                            "task_id": task.id,
                            "artifact": artifact_input.name,
                            "source_task": src_task_id,
                            "source_artifact": src_artifact_name,
                        },
                    )

                # Direct Type Contract Comparison
                target_output = src_outputs[src_artifact_name]
                if artifact_input.type != target_output.type:
                    logger.error(
                        "Type mismatch between source artifact '%s.%s' (%s) and target artifact '%s.%s' (%s)",
                        src_task_id,
                        src_artifact_name,
                        target_output.type,
                        task.id,
                        artifact_input.name,
                        artifact_input.type,
                        extra={
                            "event": "manifest_validation.type_mismatch",
                            "source_task": src_task_id,
                            "source_artifact": src_artifact_name,
                            "source_type": target_output.type,
                            "target_task": task.id,
                            "target_artifact": artifact_input.name,
                            "target_type": artifact_input.type,
                        },
                    )
                    raise ManifestSemanticError(
                        message=f"Type mismatch on link between '{src_task_id}.{src_artifact_name}' ({target_output.type}) and '{task.id}.{artifact_input.name}' ({artifact_input.type}).",
                        details={
                            "source_task": src_task_id,
                            "source_artifact": src_artifact_name,
                            "source_type": target_output.type,
                            "target_task": task.id,
                            "target_artifact": artifact_input.name,
                            "target_type": artifact_input.type,
                        },
                    )

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Semantic validation completed successfully in %.2fms",
            duration_ms,
            extra={
                "event": "manifest_validation.success",
                "duration_ms": duration_ms,
                "task_count": len(manifest.tasks),
            },
        )
