from __future__ import annotations

import asyncio
import logging
from typing import Dict, List

import networkx as nx

from meta_application_builder.spec_governance.schemas.rfc7807_error import (
    ProblemDetails,
    ValidationErrorDetail,
)

logger = logging.getLogger("meta_application_builder.spec_governance.topology")


class GovernanceTopologyError(Exception):
    """Raised when dependency topological validation detects cycles or unresolved edges."""

    def __init__(self, problem: ProblemDetails) -> None:
        super().__init__(problem.detail)
        self.problem = problem


class DependencyTopologyEngine:
    """Phase B Validator: Analyzes dependency networks using NetworkX for cycle detection and topological ordering."""

    @classmethod
    def _validate_and_sort_sync(cls, dependency_map: Dict[str, List[str]], instance_uri: str) -> List[str]:
        """Synchronous core logic for NetworkX evaluation."""
        logger.info("Building NetworkX dependency graph across %d nodes.", len(dependency_map))
        dag = nx.DiGraph()

        for node, deps in dependency_map.items():
            dag.add_node(node)
            for dep in deps:
                dag.add_edge(node, dep)

        if not nx.is_directed_acyclic_graph(dag):
            cycles = list(nx.simple_cycles(dag))
            logger.error("Circular dependency detected in graph: %s", cycles)
            cycle_str = " -> ".join(cycles[0]) if cycles else "Unknown"
            problem = ProblemDetails.create(
                status=422,
                title="Circular Dependency Error",
                detail=f"Circular specification dependency cycle detected: {cycle_str}",
                instance=instance_uri,
                invalid_params=[
                    ValidationErrorDetail(
                        field_path="dependencies",
                        code="MBR-008",
                        message=f"Cycle sequence: {cycle_str}",
                    )
                ],
            )
            raise GovernanceTopologyError(problem)

        sorted_nodes = list(nx.topological_sort(dag))
        sorted_nodes.reverse()
        logger.info("Topological sorting successful. Execution order: %s", sorted_nodes)
        return sorted_nodes

    @classmethod
    async def validate_and_sort(cls, dependency_map: Dict[str, List[str]], instance_uri: str) -> List[str]:
        """
        Constructs a NetworkX DiGraph asynchronously, executes O(V+E) cycle detection,
        and returns a topologically sorted deployment list.
        """
        # FIX: Offload CPU-heavy topology sorting to background thread
        return await asyncio.to_thread(cls._validate_and_sort_sync, dependency_map, instance_uri)