from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from meta_service_generator.exceptions import IRBuilderError
from meta_service_generator.local_telemetry import get_logger
from meta_service_generator.manifest.schema import (
    EntitySpec,
    ManifestSpec,
)
from meta_telemetry import get_tracer, trace_span


logger = get_logger(
    "meta_service_generator.analysis.relationships"
)
tracer = get_tracer(
    "meta_service_generator.analysis.relationships"
)


@dataclass(frozen=True, slots=True)
class RelationshipEdge:
    """Immutable directional relationship edge used by graph analysis."""

    source_entity: str
    target_entity: str
    cardinality: str
    foreign_key: str | None
    foreign_key_nullable: bool
    relationship_name: str


class RelationshipGraph:
    """Builds and manages directional relationship adjacency lists for entities [source: 3]."""

    _ERROR_UNKNOWN_TARGET: Final[str] = (
        "ERR_RELATIONSHIP_UNKNOWN_TARGET"
    )

    _ERROR_UNKNOWN_FK: Final[str] = (
        "ERR_RELATIONSHIP_UNKNOWN_FOREIGN_KEY"
    )

    _ERROR_DUPLICATE_ENTITY: Final[str] = (
        "ERR_RELATIONSHIP_DUPLICATE_ENTITY"
    )

    def __init__(
        self,
        manifest: ManifestSpec,
    ) -> None:
        if not isinstance(
            manifest,
            ManifestSpec,
        ):
            raise TypeError(
                "manifest must be a ManifestSpec instance."
            )

        self._manifest = manifest

        self._entity_map: dict[
            str,
            EntitySpec,
        ] = self._index_entities(
            manifest
        )

        self._adjacency: dict[
            str,
            set[str],
        ] = {
            entity.name: set()
            for entity in manifest.entities
        }

        self._edges: list[
            RelationshipEdge
        ] = []

        self._outgoing_edges: dict[
            str,
            list[RelationshipEdge],
        ] = {
            entity.name: []
            for entity in manifest.entities
        }

        self._edges_by_pair: dict[
            tuple[str, str],
            list[RelationshipEdge],
        ] = {}

        self._build_graph()

    @property
    def adjacency(
        self,
    ) -> dict[str, frozenset[str]]:
        """Return a read-only snapshot of the graph adjacency structure."""
        return {
            entity: frozenset(
                targets
            )
            for entity, targets in self._adjacency.items()
        }

    @property
    def edges(
        self,
    ) -> tuple[RelationshipEdge, ...]:
        """Return immutable relationship edges."""
        return tuple(
            self._edges
        )

    @property
    def entity_names(
        self,
    ) -> frozenset[str]:
        """Return all graph entity names."""
        return frozenset(
            self._entity_map
        )

    @trace_span("analysis.relationships.build_graph")
    def _build_graph(
        self,
    ) -> None:
        for entity in self._manifest.entities:
            for relationship in entity.relationships:
                target_entity = self._entity_map.get(
                    relationship.target_entity
                )

                if target_entity is None:
                    raise IRBuilderError(
                        message=(
                            f"Relationship '{relationship.name}' on entity "
                            f"'{entity.name}' references unknown target entity "
                            f"'{relationship.target_entity}'."
                        ),
                        location=(
                            f"entities/{entity.name}/"
                            f"relationships/{relationship.name}/target_entity"
                        ),
                        error_code=self._ERROR_UNKNOWN_TARGET,
                        suggested_resolution=(
                            "Define the target entity before referencing it "
                            "from a relationship."
                        ),
                    )

                fk_nullable = (
                    self._resolve_foreign_key_nullability(
                        entity_name=entity.name,
                        relationship_name=relationship.name,
                        foreign_key=relationship.foreign_key,
                        attributes=entity.attributes,
                    )
                )

                edge = RelationshipEdge(
                    source_entity=entity.name,
                    target_entity=relationship.target_entity,
                    cardinality=str(
                        relationship.cardinality
                    ),
                    foreign_key=relationship.foreign_key,
                    foreign_key_nullable=fk_nullable,
                    relationship_name=relationship.name,
                )

                self._adjacency[
                    entity.name
                ].add(
                    relationship.target_entity
                )

                self._edges.append(
                    edge
                )

                self._outgoing_edges[
                    entity.name
                ].append(
                    edge
                )

                self._edges_by_pair.setdefault(
                    (
                        entity.name,
                        relationship.target_entity,
                    ),
                    [],
                ).append(
                    edge
                )

        logger.info(
            "Relationship graph constructed.",
            extra={
                "event_type": (
                    "analysis.relationships.graph_constructed"
                ),
                "entity_count": len(
                    self._adjacency
                ),
                "edge_count": len(
                    self._edges
                ),
            },
        )

    @staticmethod
    def _index_entities(
        manifest: ManifestSpec,
    ) -> dict[str, EntitySpec]:
        entity_map: dict[
            str,
            EntitySpec,
        ] = {}

        for entity in manifest.entities:
            if entity.name in entity_map:
                raise IRBuilderError(
                    message=(
                        f"Duplicate entity name "
                        f"'{entity.name}'."
                    ),
                    location=f"entities/{entity.name}",
                    error_code=(
                        "ERR_RELATIONSHIP_DUPLICATE_ENTITY"
                    ),
                    suggested_resolution=(
                        "Entity names must be unique within "
                        "a manifest."
                    ),
                )

            entity_map[
                entity.name
            ] = entity

        return entity_map

    @staticmethod
    def _resolve_foreign_key_nullability(
        *,
        entity_name: str,
        relationship_name: str,
        foreign_key: str | None,
        attributes: tuple[object, ...] | list[object],
    ) -> bool:
        if foreign_key is None:
            return True

        for attribute in attributes:
            if getattr(
                attribute,
                "name",
                None,
            ) == foreign_key:
                return bool(
                    getattr(
                        attribute,
                        "nullable",
                        False,
                    )
                )

        raise IRBuilderError(
            message=(
                f"Relationship '{relationship_name}' on entity "
                f"'{entity_name}' references foreign key "
                f"'{foreign_key}', but that attribute does not exist."
            ),
            location=(
                f"entities/{entity_name}/"
                f"relationships/{relationship_name}/foreign_key"
            ),
            error_code=(
                "ERR_RELATIONSHIP_UNKNOWN_FOREIGN_KEY"
            ),
            suggested_resolution=(
                f"Define attribute '{foreign_key}' on entity "
                f"'{entity_name}' or remove the foreign_key declaration."
            ),
        )

    def get_dependencies(
        self,
        entity_name: str,
    ) -> frozenset[str]:
        """Return immutable dependency targets for an entity."""
        if entity_name not in self._adjacency:
            raise IRBuilderError(
                message=(
                    f"Unknown entity '{entity_name}' requested "
                    "from relationship graph."
                ),
                location=f"entities/{entity_name}",
                error_code="ERR_RELATIONSHIP_UNKNOWN_ENTITY",
                suggested_resolution=(
                    "Request relationship dependencies only for "
                    "entities declared in the manifest."
                ),
            )

        return frozenset(
            self._adjacency[entity_name]
        )

    def get_outgoing_edges(
        self,
        entity_name: str,
    ) -> tuple[RelationshipEdge, ...]:
        """Return all outgoing relationship edges for an entity."""
        if entity_name not in self._outgoing_edges:
            raise IRBuilderError(
                message=(
                    f"Unknown entity '{entity_name}' requested "
                    "from relationship graph."
                ),
                location=f"entities/{entity_name}",
                error_code="ERR_RELATIONSHIP_UNKNOWN_ENTITY",
                suggested_resolution=(
                    "Request relationship edges only for "
                    "entities declared in the manifest."
                ),
            )

        return tuple(
            self._outgoing_edges[
                entity_name
            ]
        )

    def get_edge(
        self,
        source_entity: str,
        target_entity: str,
    ) -> RelationshipEdge | None:
        """Return a matching relationship edge, if one exists."""
        if source_entity not in self._adjacency:
            raise IRBuilderError(
                message=(
                    f"Unknown source entity "
                    f"'{source_entity}' requested from relationship graph."
                ),
                location=f"entities/{source_entity}",
                error_code="ERR_RELATIONSHIP_UNKNOWN_ENTITY",
                suggested_resolution=(
                    "Use an entity declared in the manifest."
                ),
            )

        if target_entity not in self._adjacency:
            raise IRBuilderError(
                message=(
                    f"Unknown target entity "
                    f"'{target_entity}' requested from relationship graph."
                ),
                location=f"entities/{target_entity}",
                error_code="ERR_RELATIONSHIP_UNKNOWN_ENTITY",
                suggested_resolution=(
                    "Use an entity declared in the manifest."
                ),
            )

        edges = self._edges_by_pair.get(
            (
                source_entity,
                target_entity,
            ),
            (),
        )

        return (
            edges[0]
            if edges
            else None
        )