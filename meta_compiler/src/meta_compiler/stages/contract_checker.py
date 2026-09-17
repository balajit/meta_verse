"""Contract checker module for meta_compiler.

Enforces semantic edge contract compatibility (producer outputs -> consumer inputs)
and uses Apache Hamilton in-memory DAG representations to verify node dry-run execution.
"""

import logging
import re
import sys
import threading
import time
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Union, get_args, get_origin

from hamilton import driver as h_driver
from pydantic import BaseModel, ValidationError

from meta_compiler.core.action_registry import ActionRegistry
from meta_compiler.core.context import CompilationContext
from meta_compiler.core.models import WorkflowManifestSpec
from meta_compiler.exceptions import ContractValidationError
from meta_compiler.stages.base import BaseCompilerStage

logger = logging.getLogger("meta_compiler.contracts.contract_checker")
_HAMILTON_MODULE_LOCK = threading.RLock()


@dataclass(frozen=True)
class ContractMismatch:
    """Diagnostic metadata capturing incompatible task edge boundaries."""

    producer_id: str
    consumer_id: str
    producer_action: str
    consumer_action: str
    expected_type: type[Any]
    actual_type: type[Any]


class ContractCheckerStage(BaseCompilerStage):
    """Stage 4 Adapter: Read-only edge type verification and dry-run execution check."""

    def run(self, context: CompilationContext, registry: ActionRegistry) -> None:
        logger.debug(
            "Executing ContractCheckerStage for context %s",
            context.context_id,
            extra={"event": "stage.contract_checker.start", "context_id": str(context.context_id)},
        )
        context.registry = registry
        if context.manifest_spec and getattr(context.manifest_spec, "tasks", None):
            checker = ContractChecker(registry=registry)
            checker.verify_edge_contracts(context=context)

            # Only perform Hamilton dry-run pass if no pending contract mismatches exist
            if not context.diagnostics and context.execution_plan:
                checker.verify_node_contracts(
                    manifest=context.manifest_spec,
                    execution_plan=context.execution_plan,
                )


def is_type_compatible(
    producer_type: type[Any],
    consumer_type: type[Any],
    _depth: int = 0,
    _max_depth: int = 15,
) -> bool:
    """Evaluates type equality, subclassing, numeric promotion, covariance,
    and optional/nullable type assignability between producer outputs and consumer inputs.
    """
    if _depth > _max_depth:
        logger.warning(
            "Type compatibility check exceeded max recursion depth (%d)",
            _max_depth,
            extra={"event": "contract_check.max_depth_exceeded", "depth": _depth},
        )
        return False

    if consumer_type is Any or producer_type is Any:
        return True

    if producer_type == consumer_type:
        return True

    # Numeric promotion (int -> float)
    if producer_type is int and consumer_type is float:
        return True

    # Subclass / Structural model assignment
    try:
        if (
            isinstance(producer_type, type)
            and isinstance(consumer_type, type)
            and issubclass(producer_type, consumer_type)
        ):
            return True
    except TypeError as err:
        logger.debug(
            "Non-subclassable type encountered during compatibility check: %s",
            err,
            extra={"event": "contract_check.type_error_ignored"},
        )

    # Union & Optional types
    producer_origin = get_origin(producer_type)
    consumer_origin = get_origin(consumer_type)

    if consumer_origin is Union:
        consumer_args = get_args(consumer_type)
        return any(
            is_type_compatible(producer_type, arg, _depth=_depth + 1, _max_depth=_max_depth)
            for arg in consumer_args
        )

    if producer_origin is Union:
        producer_args = get_args(producer_type)
        return all(
            is_type_compatible(arg, consumer_type, _depth=_depth + 1, _max_depth=_max_depth)
            for arg in producer_args
        )

    # Generic Collections (list[T], dict[K, V])
    if producer_origin is not None and producer_origin is consumer_origin:
        p_args = get_args(producer_type)
        c_args = get_args(consumer_type)
        if len(p_args) == len(c_args):
            return all(
                is_type_compatible(p, c, _depth=_depth + 1, _max_depth=_max_depth)
                for p, c in zip(p_args, c_args)
            )

    return False


class ContractChecker:
    """Encapsulates semantic edge contract verification and Hamilton dry-run graph execution."""

    def __init__(self, registry: ActionRegistry) -> None:
        if registry is None:
            raise ContractValidationError(
                message="ActionRegistry instance is required for ContractChecker initialization.",
                details={"param": "registry", "reason": "cannot_be_none"},
            )
        self.registry = registry

    def verify_edge_contracts(self, context: CompilationContext) -> None:
        """Pure read-only diagnostic pass. Populates context.diagnostics without mutating AST."""
        manifest = context.manifest_spec
        if not manifest:
            return

        start_time = time.perf_counter()
        logger.debug(
            "Verifying edge contracts for workflow manifest '%s/%s'",
            manifest.namespace,
            manifest.name,
            extra={
                "event": "contract_check.edge_verify_start",
                "manifest.namespace": manifest.namespace,
                "manifest.name": manifest.name,
            },
        )

        task_map = {task.id: task for task in manifest.tasks}

        for consumer_task in manifest.tasks:
            try:
                consumer_spec = self.registry.resolve(consumer_task.action)
            except ContractValidationError as err:
                logger.error(
                    "Task '%s' references unregistered action '%s'",
                    consumer_task.id,
                    consumer_task.action,
                    extra={
                        "event": "contract_check.unregistered_action",
                        "task_id": consumer_task.id,
                        "action": consumer_task.action,
                    },
                )
                raise ContractValidationError(
                    message=f"Task '{consumer_task.id}' references unregistered action '{consumer_task.action}'",
                    details={"task_id": consumer_task.id, "action": consumer_task.action},
                ) from err

            for producer_id in consumer_task.depends_on:
                if producer_id not in task_map:
                    raise ContractValidationError(
                        message=f"Task '{consumer_task.id}' depends on non-existent producer task '{producer_id}'",
                        details={"task_id": consumer_task.id, "missing_producer_id": producer_id},
                    )

                producer_task = task_map[producer_id]
                try:
                    producer_spec = self.registry.resolve(producer_task.action)
                except ContractValidationError as err:
                    logger.error(
                        "Producer Task '%s' references unregistered action '%s'",
                        producer_id,
                        producer_task.action,
                        extra={
                            "event": "contract_check.unregistered_producer_action",
                            "producer_id": producer_id,
                            "action": producer_task.action,
                        },
                    )
                    raise ContractValidationError(
                        message=f"Producer task '{producer_id}' references unregistered action '{producer_task.action}'",
                        details={"producer_id": producer_id, "action": producer_task.action},
                    ) from err

                producer_output = producer_spec.output_schema or Any
                consumer_input = consumer_spec.input_schema or Any

                if not is_type_compatible(producer_output, consumer_input):
                    logger.warning(
                        "Edge contract mismatch recorded: Producer '%s' (%s) -> Consumer '%s' (%s)",
                        producer_id,
                        producer_output,
                        consumer_task.id,
                        consumer_input,
                        extra={
                            "event": "contract_check.edge_mismatch_detected",
                            "producer": producer_id,
                            "producer_output": str(producer_output),
                            "consumer": consumer_task.id,
                            "consumer_input": str(consumer_input),
                        },
                    )
                    context.diagnostics.append(
                        ContractMismatch(
                            producer_id=producer_id,
                            consumer_id=consumer_task.id,
                            producer_action=producer_task.action,
                            consumer_action=consumer_task.action,
                            expected_type=consumer_input,
                            actual_type=producer_output,
                        )
                    )
                    context.requires_reprocessing = True

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "Edge contract diagnostic pass completed in %.2fms for workflow '%s' (Mismatches: %d)",
            duration_ms,
            manifest.name,
            len(context.diagnostics),
            extra={
                "event": "contract_check.edge_verify_complete",
                "duration_ms": duration_ms,
                "manifest": manifest.name,
                "mismatch_count": len(context.diagnostics),
            },
        )

    def _generate_mock_output(self, task_id: str, out_type: type[Any]) -> Any:
        """Generates mock payloads for dry-run verification."""
        if out_type is None or out_type is type(None):
            return None
        if isinstance(out_type, type) and issubclass(out_type, BaseModel):
            try:
                return out_type.model_construct()
            except ValidationError as err:
                logger.warning(
                    "Pydantic construction failed for mock output node '%s': %s",
                    task_id,
                    err,
                    extra={
                        "event": "contract_check.mock_construct_validation_error",
                        "task_id": task_id,
                    },
                )
                return {}
            except Exception as err:
                logger.warning(
                    "Unexpected error generating Pydantic mock for node '%s': %s",
                    task_id,
                    err,
                    extra={
                        "event": "contract_check.mock_construct_unexpected_error",
                        "task_id": task_id,
                    },
                )
                return {}
        if out_type is str:
            return f"mock_output_{task_id}"
        if out_type is int:
            return 1
        if out_type is float:
            return 1.0
        if out_type is bool:
            return True
        if out_type is list or get_origin(out_type) is list:
            return []
        if out_type is dict or get_origin(out_type) is dict:
            return {}
        return {}

    def _generate_hamilton_module(self, manifest: WorkflowManifestSpec) -> tuple[ModuleType, str]:
        """Synthesizes a dynamic Hamilton execution module using ActionRegistry signatures.

        Hamilton discovers nodes via static source analysis, so the module is generated
        as real source and ``exec``-ed (instead of binding closures), ensuring every task
        node is discoverable and its output type enforced.
        """
        module_name = (
            f"dynamic_hamilton_manifest_{manifest.namespace}_{manifest.name}_{time.time_ns()}"
        )

        type_namespace: dict[str, Any] = {}
        mock_outputs: dict[str, Any] = {}
        source_lines = ["'''Synthetic Hamilton module for contract verification.'''", ""]

        def _type_expr(output_type: type[Any]) -> str:
            if output_type is None or output_type is type(None):
                return "None"
            if isinstance(output_type, type) and issubclass(output_type, BaseModel):
                type_namespace[output_type.__name__] = output_type
                return output_type.__name__
            return "object"

        for task in manifest.tasks:
            try:
                action_spec = self.registry.resolve(task.action)
            except ContractValidationError as err:
                logger.error(
                    "Task '%s' references unregistered action '%s' during Hamilton synthesis",
                    task.id,
                    task.action,
                    extra={
                        "event": "contract_check.hamilton_unregistered_action",
                        "task_id": task.id,
                    },
                )
                raise ContractValidationError(
                    message=f"Cannot generate Hamilton driver: Task '{task.id}' references unregistered action '{task.action}'",
                    details={"task_id": task.id, "action": task.action},
                ) from err

            out_type = action_spec.output_schema or object
            type_expr = _type_expr(out_type)
            mock_outputs[task.id] = self._generate_mock_output(task.id, out_type)

            params = ", ".join(f"{dep_id}: object" for dep_id in task.depends_on)
            def_name = re.sub(r"\W", "_", task.id) or "task"
            source_lines.append(f"def {def_name}({params}) -> {type_expr}:")
            source_lines.append(f"    return _MOCK_TASK_OUTPUTS['{task.id}']")
            source_lines.append("")

        source = "\n".join(source_lines)
        dynamic_module = ModuleType(module_name)
        # Hamilton introspects module attributes via inspect, which requires the
        # generated functions' __globals__ to be the module namespace itself.
        dynamic_module.__dict__["_MOCK_TASK_OUTPUTS"] = mock_outputs
        dynamic_module.__dict__.update(type_namespace)
        exec(compile(source, f"{module_name}.py", "exec"), dynamic_module.__dict__)

        with _HAMILTON_MODULE_LOCK:
            sys.modules[module_name] = dynamic_module

        return dynamic_module, module_name

    def build_hamilton_driver(self, manifest: WorkflowManifestSpec) -> tuple[h_driver.Driver, str]:
        """Compiles an in-memory Hamilton execution driver for the manifest along with module cleanup key."""
        logger.debug(
            "Building dynamic Hamilton driver for workflow '%s'",
            manifest.name,
            extra={"event": "contract_check.build_driver_start", "manifest": manifest.name},
        )
        try:
            dynamic_module, module_name = self._generate_hamilton_module(manifest)
            driver = h_driver.Builder().with_modules(dynamic_module).build()
            return driver, module_name
        except ContractValidationError:
            raise
        except Exception as err:
            logger.error(
                "Failed to build Hamilton execution driver: %s",
                err,
                extra={
                    "event": "contract_check.build_driver_failure",
                    "manifest": manifest.name,
                    "error": str(err),
                },
            )
            raise ContractValidationError(
                message=f"Failed to compile Hamilton graph driver: {err}",
                details={"manifest": manifest.name, "error": str(err)},
            ) from err

    def verify_node_contracts(
        self,
        manifest: WorkflowManifestSpec,
        execution_plan: Any,
    ) -> bool:
        """Performs a Hamilton dry-run pass stage-by-stage."""
        start_time = time.perf_counter()
        driver, module_name = self.build_hamilton_driver(manifest)

        try:
            flat_stage_nodes = [
                node for stage_nodes in execution_plan.stages for node in stage_nodes
            ]
            results = driver.execute(final_vars=flat_stage_nodes)

            for stage_idx, stage_nodes in enumerate(execution_plan.stages):
                for node in stage_nodes:
                    if node not in results:
                        raise ContractValidationError(
                            message=f"Contract verification failed at stage {stage_idx}: node '{node}' produced no output payload",
                            details={"stage": stage_idx, "missing_node": node},
                        )

            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "Successfully validated dry-run contracts for workflow '%s' in %.2fms",
                manifest.name,
                duration_ms,
                extra={
                    "event": "contract_check.verify_success",
                    "manifest": manifest.name,
                    "duration_ms": duration_ms,
                },
            )
            return True

        except ContractValidationError:
            raise
        except Exception as err:
            logger.error(
                "Payload contract dry-run failure for workflow '%s': %s",
                manifest.name,
                err,
                extra={
                    "event": "contract_check.dry_run_failure",
                    "manifest": manifest.name,
                    "error": str(err),
                },
            )
            raise ContractValidationError(
                message=f"Payload contract dry-run failure: {err}",
                details={"error": str(err)},
            ) from err
        finally:
            with _HAMILTON_MODULE_LOCK:
                sys.modules.pop(module_name, None)


def verify_node_contracts(
    manifest: WorkflowManifestSpec,
    execution_plan: Any,
    registry: ActionRegistry,
) -> bool:
    """Backward-compatible functional wrapper delegating to scoped ContractChecker instance."""
    checker = ContractChecker(registry=registry)
    return checker.verify_node_contracts(manifest=manifest, execution_plan=execution_plan)


def verify_edge_contracts(
    manifest: WorkflowManifestSpec,
    registry: ActionRegistry,
) -> list[ContractMismatch]:
    """Validates edge type compatibility across a compiled manifest.

    Raises :class:`ContractValidationError` for unregistered actions or
    unresolvable producer references, and returns any recorded edge
    ``ContractMismatch`` diagnostics for incompatible producer→consumer
    output/input type boundaries.
    """
    checker = ContractChecker(registry=registry)
    context = CompilationContext(
        raw_input=manifest,
        manifest_spec=manifest,
        registry=registry,
    )
    checker.verify_edge_contracts(context=context)
    return list(context.diagnostics)
