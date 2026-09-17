"""NetworkX DAG processing engine and TreeResolver with topology validation."""

from __future__ import annotations

from typing import Dict, List, Set, Any, NamedTuple
import networkx as nx
from meta_telemetry import trace_span
from meta_builder_brain.exceptions import (
    DAGCycleError,
    DAGNodeNotFoundError,
    EmptyDAGError,
    InvalidURNError,
)


class DAGGraph(NamedTuple):
    execution_order: List[str]


class TreeResolver:
    """Resolves component dependency trees and validates URN formats."""

    @staticmethod
    def validate_urn(urn: str) -> Dict[str, str]:
        """Validates and parses standard blueprint URNs (urn:meta:bcr:<namespace>:<component>:<version>)."""
        if not isinstance(urn, str) or not urn.startswith("urn:meta:bcr:"):
            raise InvalidURNError(f"Invalid URN prefix in '{urn}'. Expected 'urn:meta:bcr:'.")

        parts = urn.split(":")
        if len(parts) != 6:
            raise InvalidURNError(
                f"Invalid URN structure '{urn}'. Expected format 'urn:meta:bcr:<namespace>:<component>:<version>'."
            )

        return {
            "namespace": parts[3],
            "component": parts[4],
            "version": parts[5],
        }

    @classmethod
    @trace_span(name="dag.build_and_validate_dag")
    def build_and_validate_dag(cls, components: Dict[str, List[str]]) -> DAGGraph:
        """Validates component URNs and builds dependency graph to return execution order."""
        engine = ComponentDAGEngine()

        for component_urn, dependencies in components.items():
            cls.validate_urn(component_urn)
            for dep in dependencies:
                cls.validate_urn(dep)
            engine.add_component(component_urn, dependencies)

        execution_order = engine.compute_execution_order()
        return DAGGraph(execution_order=execution_order)


class ComponentDAGEngine:
    """Manages dependency topological sorting and lineage graphs for blueprint components."""

    def __init__(self) -> None:
        self.graph: nx.DiGraph[str] = nx.DiGraph()

    @trace_span(name="dag.add_component")
    def add_component(self, component_urn: str, dependencies: List[str]) -> None:
        """Adds a component node and its directed dependency edges to the graph."""
        if not component_urn or not component_urn.strip():
            raise DAGNodeNotFoundError("Component URN identifier cannot be empty.")

        self.graph.add_node(component_urn)
        for dep_urn in dependencies:
            if not dep_urn or not dep_urn.strip():
                raise DAGNodeNotFoundError(f"Invalid dependency URN reference for '{component_urn}'.")
            self.graph.add_node(dep_urn)
            self.graph.add_edge(dep_urn, component_urn)

    @trace_span(name="dag.compute_execution_order")
    def compute_execution_order(self) -> List[str]:
        """Computes topological execution order for dependency processing."""
        if self.graph.number_of_nodes() == 0:
            raise EmptyDAGError("Cannot compute execution order on an empty graph.")

        try:
            return list(nx.topological_sort(self.graph))
        except nx.NetworkXUnfeasible as exc:
            cycles = list(nx.simple_cycles(self.graph))
            raise DAGCycleError(
                f"Cyclic dependency detected in component graph: {cycles}",
                payload={"cycles": cycles},
            ) from exc

    @trace_span(name="dag.get_upstream_dependencies")
    def get_upstream_dependencies(self, component_urn: str) -> Set[str]:
        """Retrieves all transitive upstream dependency URNs for a target component."""
        if component_urn not in self.graph:
            raise DAGNodeNotFoundError(f"Component '{component_urn}' not found in DAG engine.")

        try:
            return nx.ancestors(self.graph, component_urn)
        except nx.NetworkXError as exc:
            raise DAGNodeNotFoundError(f"Error querying ancestors for '{component_urn}': {exc}") from exc