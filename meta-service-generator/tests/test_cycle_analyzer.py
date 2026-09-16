from types import SimpleNamespace
import pytest

from meta_service_generator.analysis.cycles import CycleAnalyzer
from meta_service_generator.analysis.relationships import RelationshipEdge, RelationshipGraph
from meta_service_generator.exceptions import IRBuilderError


def create_mock_manifest(entities_spec):
    entities = []
    for entity_name, rels in entities_spec.items():
        relationships = [
            SimpleNamespace(
                name=f"rel_{source}_{target}",
                target_entity=target,
                cardinality="one_to_many",
                foreign_key=fk,
            )
            for source, target, fk in rels
        ]
        # Attributes defining foreign keys
        attributes = [
            SimpleNamespace(name="fk_nullable", nullable=True),
            SimpleNamespace(name="fk_required", nullable=False),
        ]
        entities.append(
            SimpleNamespace(
                name=entity_name,
                relationships=relationships,
                attributes=attributes,
            )
        )
    return SimpleNamespace(entities=entities)


def test_acyclic_dependency_graph():
    manifest = create_mock_manifest({
        "User": [("User", "Post", "fk_required")],
        "Post": [("Post", "Comment", "fk_required")],
        "Comment": [],
    })
    graph = RelationshipGraph(manifest)
    analyzer = CycleAnalyzer(graph)

    result = analyzer.analyze()
    assert result == {"Comment": False, "Post": False, "User": False}


def test_resolvable_circular_dependency_with_nullable_fk():
    manifest = create_mock_manifest({
        "A": [("A", "B", "fk_required")],
        "B": [("B", "A", "fk_nullable")],  # Nullable FK resolves loop
    })
    graph = RelationshipGraph(manifest)
    analyzer = CycleAnalyzer(graph)

    result = analyzer.analyze()
    assert result == {"A": True, "B": True}


def test_unresolvable_circular_dependency_raises_error():
    manifest = create_mock_manifest({
        "A": [("A", "B", "fk_required")],
        "B": [("B", "A", "fk_required")],  # Both non-nullable FKs
    })
    graph = RelationshipGraph(manifest)
    analyzer = CycleAnalyzer(graph)

    with pytest.raises(IRBuilderError, match="Unresolvable circular dependency loop detected"):
        analyzer.analyze()


def test_cycle_graph_inconsistency_error(mocker):
    manifest = create_mock_manifest({
        "A": [("A", "B", "fk_nullable")],
        "B": [("B", "A", "fk_nullable")],
    })
    graph = RelationshipGraph(manifest)
    analyzer = CycleAnalyzer(graph)

    # Force internal index mutation to simulate graph inconsistency
    analyzer._edges_by_pair.clear()

    with pytest.raises(IRBuilderError, match="Cycle references relationship edge"):
        analyzer.analyze()