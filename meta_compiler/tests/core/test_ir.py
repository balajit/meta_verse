"""Immutable IR value objects and canonical hashing."""

import pytest

from meta_compiler.core.immutable import ImmutableDict
from meta_compiler.core.ir import EdgeIR, ManifestIR, NodeIR
from meta_compiler.exceptions import ManifestSyntaxError


def _sample_manifest() -> ManifestIR:
    node_a = NodeIR(id="a", type="produce", attributes={"mode": "fast"})
    node_b = NodeIR(id="b", type="consume", inputs=["a"])
    edge = EdgeIR(source="a", target="b", attributes={"label": "feed"})
    return ManifestIR(
        namespace="ns",
        name="wf",
        nodes=(node_a, node_b),
        edges=(edge,),
        attributes={"owner": "team"},
    )


def test_node_ir_attributes_are_deep_frozen() -> None:
    node = NodeIR(id="a", type="t", attributes={"nested": {"k": 1}})
    assert isinstance(node.attributes, ImmutableDict)
    with pytest.raises(TypeError):
        node.attributes["nested"] = {}  # type: ignore[index]


def test_node_ir_inputs_tuple_normalization() -> None:
    node = NodeIR(id="a", type="t", inputs=["x", "y"])
    assert isinstance(node.inputs, tuple)
    assert node.inputs == ("x", "y")


def test_ir_round_trip_preserves_identity() -> None:
    ir = _sample_manifest()
    restored = ManifestIR.from_dict(ir.to_dict())
    assert restored.namespace == ir.namespace
    assert restored.name == ir.name
    assert [n.id for n in restored.nodes] == ["a", "b"]
    assert restored.edges[0].source == "a"
    assert restored.compute_canonical_hash() == ir.compute_canonical_hash()


def test_canonical_hash_changes_when_node_attribute_changes() -> None:
    base = _sample_manifest()
    changed = ManifestIR(
        namespace="ns",
        name="wf",
        nodes=(NodeIR(id="a", type="produce", attributes={"mode": "slow"}),),
        edges=(),
        attributes={"owner": "team"},
    )
    assert base.compute_canonical_hash() != changed.compute_canonical_hash()


def test_manifest_ir_from_dict_computes_hash() -> None:
    ir = _sample_manifest()
    restored = ManifestIR.from_dict(ir.to_dict())
    assert restored.manifest_hash == restored.compute_canonical_hash()
    assert restored.manifest_hash is not None


def test_node_ir_from_dict_rejects_missing_keys() -> None:
    with pytest.raises(ManifestSyntaxError):
        NodeIR.from_dict({"type": "t"})


def test_manifest_ir_from_dict_rejects_non_dict() -> None:
    with pytest.raises(ManifestSyntaxError):
        ManifestIR.from_dict("nope")  # type: ignore[arg-type]
