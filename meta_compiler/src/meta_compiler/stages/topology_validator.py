"""Topological validator and execution planner module for meta_compiler.

Builds NetworkX directed graph representations (upstream -> downstream) of compiled
workflow manifests, enforces acyclic guarantees, validates dependency existence, and
synthesizes immutable ExecutionPlan artifacts.
"""

import copy
import logging
import time
from typing import Literal, cast

import networkx as nx

from meta_compiler.core.action_registry import ActionRegistry
from meta_compiler.core.context import CompilationContext
from meta_compiler.core.models import ExecutionPlan, WorkflowManifestSpec
from meta_compiler.exceptions import CyclicGraphError, TopologyValidationError
from meta_compiler.stages.base import BaseCompilerStage

logger = logging.getLogger("meta_compiler.stages.topology_validator")


class TopologyValidatorStage(BaseCompilerStage):
    """Stage 3 Adapter: NetworkX DAG cycle detection and topological ordering synthesis."""

    def run(self, context: CompilationContext, registry: ActionRegistry) -> None:
        logger.debug(
            "Executing TopologyValidatorStage for context %s",
            context.context_id,
            extra={
                "event": "stage.topology_validator.start",
                "context_id": str(context.context_id),
            },
        )

        if (
            context.manifest_spec
            and isinstance(context.manifest_spec, WorkflowManifestSpec)
            and getattr(context.manifest_spec, "tasks", None)
        ):
            _, plan = validate_topology(context.manifest_spec)
            context.execution_plan = plan
            # added for debugging purposes
            context.metadata["execution_stages"] = [list(stage) for stage in plan.stages]


def validate_dependency_references(manifest: WorkflowManifestSpec) -> None:
    """Explicit pre-validation phase ensuring all dependency targets exist."""
    if not manifest.tasks:
        logger.warning(
            "Workflow manifest '%s/%s' contains no task definitions",
            manifest.namespace,
            manifest.name,
            extra={
                "event": "topology.empty_manifest",
                "namespace": manifest.namespace,
                "name": manifest.name,
            },
        )
        return

    declared_task_ids = {task.id for task in manifest.tasks}

    for task in manifest.tasks:
        unknown_deps = set(task.depends_on) - declared_task_ids
        if unknown_deps:
            missing_list = sorted(unknown_deps)
            logger.error(
                "Task '%s' references nonexistent upstream dependencies: %s",
                task.id,
                missing_list,
                extra={
                    "event": "topology.unresolvable_dependency",
                    "task_id": task.id,
                    "missing": missing_list,
                },
            )
            raise TopologyValidationError(
                message=f"Task '{task.id}' depends on unresolvable node ID(s): {missing_list}",
                details={"task_id": task.id, "missing_dependencies": missing_list},
            )


def build_networkx_graph(manifest: WorkflowManifestSpec) -> nx.DiGraph:
    """Constructs a NetworkX DiGraph from a compiled workflow manifest specification."""
    validate_dependency_references(manifest)
    graph = nx.DiGraph()

    for task in manifest.tasks:
        graph.add_node(
            task.id,
            action=task.action,
            inputs=[inp.model_dump() for inp in task.inputs],
            outputs=[out.model_dump() for out in task.outputs],
            params=copy.deepcopy(task.params),
        )

    for task in manifest.tasks:
        for dependency_id in task.depends_on:
            graph.add_edge(dependency_id, task.id)

    logger.debug(
        "Successfully constructed graph with %d nodes and %d edges",
        graph.number_of_nodes(),
        graph.number_of_edges(),
        extra={
            "event": "topology.graph_built",
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
        },
    )
    return graph


def assert_acyclic_topology(graph: nx.DiGraph) -> None:
    """Evaluates DAG integrity and raises CyclicGraphError if execution loops exist."""
    if not nx.is_directed_acyclic_graph(graph):
        try:
            orientation = cast(Literal["original", "reverse", "ignore"], "original")
            cycle = nx.find_cycle(graph, orientation=orientation)
            cycle_nodes = [edge[0] for edge in cycle] + [cycle[0][0]]
        except (nx.NetworkXNoCycle, nx.NetworkXError):
            cycle_nodes = list(graph.nodes)

        cycle_str = " -> ".join(cycle_nodes)
        logger.error(
            "Cyclic dependency detected in workflow graph: %s",
            cycle_str,
            extra={"event": "topology.cyclic_dependency", "cycle_nodes": cycle_nodes},
        )
        raise CyclicGraphError(
            message=f"Cyclic dependency loop detected: {cycle_str}",
            cycle_nodes=cycle_nodes,
        )


def compute_execution_plan(graph: nx.DiGraph) -> ExecutionPlan:
    """Synthesizes a structured, immutable ExecutionPlan compiler artifact."""
    assert_acyclic_topology(graph)

    if graph.number_of_nodes() == 0:
        return ExecutionPlan(
            graph_version="v1",
            stages=(),
            critical_path=(),
            roots=(),
            leaves=(),
        )

    try:
        stages = tuple(
            tuple(sorted(generation)) for generation in nx.topological_generations(graph)
        )
        roots = tuple(sorted([node for node, in_deg in graph.in_degree() if in_deg == 0]))
        leaves = tuple(sorted([node for node, out_deg in graph.out_degree() if out_deg == 0]))
        critical_path = tuple(nx.dag_longest_path(graph))

        return ExecutionPlan(
            graph_version="v1",
            stages=stages,
            critical_path=critical_path,
            roots=roots,
            leaves=leaves,
        )
    except nx.NetworkXError as err:
        logger.error(
            "Failed to compute topological execution plan: %s",
            err,
            extra={"event": "topology.plan_computation_error", "error": str(err)},
        )
        raise TopologyValidationError(
            message=f"Graph topological analysis failed: {err}",
            details={"error": str(err)},
        ) from err


def validate_topology(manifest: WorkflowManifestSpec) -> tuple[nx.DiGraph, ExecutionPlan]:
    """Executes topological verification and generates the runtime execution plan."""
    start_time = time.perf_counter()
    graph = build_networkx_graph(manifest)
    plan = compute_execution_plan(graph)
    duration_ms = (time.perf_counter() - start_time) * 1000

    logger.info(
        "Topology validation and execution plan generation completed in %.2fms",
        duration_ms,
        extra={
            "event": "topology.validation_success",
            "duration_ms": duration_ms,
            "stages": len(plan.stages),
        },
    )
    return graph, plan
