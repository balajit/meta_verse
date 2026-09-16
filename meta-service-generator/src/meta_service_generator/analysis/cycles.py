from __future__ import annotations

from collections.abc import Iterator

from meta_service_generator.analysis.relationships import (
    RelationshipEdge,
    RelationshipGraph,
)
from meta_service_generator.exceptions import IRBuilderError
from meta_service_generator.local_telemetry import get_logger
from meta_telemetry import get_tracer, trace_span


logger = get_logger(
    "meta_service_generator.analysis.cycles"
)
tracer = get_tracer(
    "meta_service_generator.analysis.cycles"
)


class CycleAnalyzer:
    """Detects dependency loops and evaluates if circular entity references are resolvable [source: 3]."""

    def __init__(
        self,
        graph: RelationshipGraph,
    ) -> None:
        if not isinstance(
            graph,
            RelationshipGraph,
        ):
            raise TypeError(
                "graph must be a RelationshipGraph instance."
            )

        self.graph = graph

        self._edges_by_pair: dict[
            tuple[str, str],
            tuple[RelationshipEdge, ...],
        ] = self._index_edges()

    def _index_edges(
        self,
    ) -> dict[
        tuple[str, str],
        tuple[RelationshipEdge, ...],
    ]:
        indexed: dict[
            tuple[str, str],
            list[RelationshipEdge],
        ] = {}

        for edge in self.graph.edges:
            indexed.setdefault(
                (
                    edge.source_entity,
                    edge.target_entity,
                ),
                [],
            ).append(edge)

        return {
            pair: tuple(edges)
            for pair, edges in indexed.items()
        }

    @trace_span("analysis.cycles.analyze")
    def analyze(self) -> dict[str, bool]:
        """
        Returns a mapping of entity_name -> is_in_circular_dependency.
        Raises IRBuilderError if an unresolvable mutual non-nullable loop exists [source: 3].
        """
        circular_entities: set[str] = set()
        visited: set[str] = set()
        active: set[str] = set()
        path: list[str] = []
        path_positions: dict[str, int] = {}
        cycles_found: set[tuple[str, ...]] = set()

        # Explicit DFS frames replace recursive calls so graph depth is not
        # constrained by Python's interpreter recursion limit.
        #
        # Frame:
        #   node
        #   ordered neighbors
        #   next neighbor index
        Frame = tuple[str, tuple[str, ...], int]

        for root in sorted(self.graph.adjacency):
            if root in visited:
                continue

            stack: list[Frame] = [
                (
                    root,
                    tuple(
                        sorted(
                            self.graph.get_dependencies(root)
                        )
                    ),
                    0,
                )
            ]

            visited.add(root)
            active.add(root)
            path.append(root)
            path_positions[root] = len(path) - 1

            while stack:
                node, neighbors, neighbor_index = stack[-1]

                if neighbor_index >= len(neighbors):
                    stack.pop()

                    active.discard(node)

                    position = path_positions.pop(
                        node,
                        None,
                    )

                    if position is not None:
                        if position == len(path) - 1:
                            path.pop()
                        else:
                            # This branch should not occur for a valid DFS
                            # stack, but retain an explicit guard rather than
                            # silently corrupting traversal state.
                            del path[position]

                            for index in range(
                                position,
                                len(path),
                            ):
                                path_positions[path[index]] = index

                    continue

                neighbor = neighbors[neighbor_index]

                stack[-1] = (
                    node,
                    neighbors,
                    neighbor_index + 1,
                )

                if neighbor not in visited:
                    visited.add(neighbor)
                    active.add(neighbor)
                    path.append(neighbor)
                    path_positions[neighbor] = (
                        len(path) - 1
                    )

                    stack.append(
                        (
                            neighbor,
                            tuple(
                                sorted(
                                    self.graph.get_dependencies(
                                        neighbor
                                    )
                                )
                            ),
                            0,
                        )
                    )

                    continue

                if neighbor not in active:
                    continue

                cycle_start = path_positions.get(
                    neighbor
                )

                if cycle_start is None:
                    raise IRBuilderError(
                        message=(
                            "Cycle traversal state became inconsistent "
                            f"while processing '{node}' -> '{neighbor}'."
                        ),
                        location=f"entities/{node}",
                        error_code="ERR_CYCLE_TRAVERSAL_STATE",
                        suggested_resolution=(
                            "Rebuild the relationship graph from a "
                            "validated manifest."
                        ),
                    )

                cycle = tuple(
                    path[cycle_start:]
                )

                canonical_cycle = (
                    self._canonicalize_cycle(
                        cycle
                    )
                )

                cycles_found.add(
                    canonical_cycle
                )

        ordered_cycles = tuple(
            sorted(
                cycles_found,
                key=lambda cycle: (
                    len(cycle),
                    cycle,
                ),
            )
        )

        for cycle in ordered_cycles:
            circular_entities.update(
                cycle
            )

            if self._is_unresolvable(cycle):
                cycle_display = " -> ".join(
                    (*cycle, cycle[0])
                )

                logger.error(
                    "Unresolvable relationship cycle detected.",
                    extra={
                        "event_type": (
                            "analysis.cycles.unresolvable_cycle"
                        ),
                        "cycle": list(cycle),
                        "cycle_size": len(cycle),
                    },
                )

                raise IRBuilderError(
                    message=(
                        "Unresolvable circular dependency loop detected "
                        f"between entities: {cycle_display}."
                    ),
                    location=f"entities/{cycle[0]}",
                    error_code="ERR_UNRESOLVABLE_CIRCULAR_DEPENDENCY",
                    suggested_resolution=(
                        "Set at least one foreign key attribute in the cycle "
                        "to 'nullable: true' to break insertion deadlocks."
                    ),
                    details={
                        "cycle": list(cycle),
                        "cycle_size": len(cycle),
                    },
                )

        result = {
            entity: entity in circular_entities
            for entity in sorted(
                self.graph.adjacency
            )
        }

        logger.info(
            "Relationship cycle analysis completed.",
            extra={
                "event_type": "analysis.cycles.completed",
                "entity_count": len(result),
                "cycle_count": len(ordered_cycles),
                "circular_entity_count": len(
                    circular_entities
                ),
            },
        )

        return result

    @staticmethod
    def _canonicalize_cycle(
        cycle: tuple[str, ...],
    ) -> tuple[str, ...]:
        """
        Normalize a directed cycle so equivalent rotations are represented once.
        """
        if not cycle:
            return ()

        rotations = tuple(
            cycle[index:] + cycle[:index]
            for index in range(len(cycle))
        )

        return min(
            rotations
        )

    def _is_unresolvable(
        self,
        cycle: tuple[str, ...],
    ) -> bool:
        """
        A cycle is unresolvable if every relationship edge participating
        in the cycle has a non-nullable foreign key.
        """
        if not cycle:
            return False

        for source, target in self._cycle_edges(
            cycle
        ):
            edges = self._edges_by_pair.get(
                (
                    source,
                    target,
                ),
                (),
            )

            if not edges:
                raise IRBuilderError(
                    message=(
                        f"Cycle references relationship edge "
                        f"'{source} -> {target}', but no graph edge exists."
                    ),
                    location=f"entities/{source}",
                    error_code="ERR_CYCLE_GRAPH_INCONSISTENCY",
                    suggested_resolution=(
                        "Rebuild the relationship graph from a "
                        "validated manifest."
                    ),
                    details={
                        "source_entity": source,
                        "target_entity": target,
                        "cycle": list(cycle),
                    },
                )

            if any(
                edge.foreign_key_nullable
                for edge in edges
            ):
                return False

        return True

    @staticmethod
    def _cycle_edges(
        cycle: tuple[str, ...],
    ) -> Iterator[tuple[str, str]]:
        for index, source in enumerate(
            cycle
        ):
            target = cycle[
                (index + 1) % len(cycle)
            ]

            yield source, target