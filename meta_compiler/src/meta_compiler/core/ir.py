"""Domain Intermediate Representation (IR) contracts for meta_compiler.

Provides immutable, strictly-typed value objects representing workflow nodes,
edges, and full manifests with deterministic canonical SHA-256 hashing.
Zero external dependencies on SQLAlchemy, NetworkX, Hamilton, or PyYAML.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field, replace
from typing import Any, Self

from meta_compiler.core.immutable import ImmutableDict, freeze_value
from meta_compiler.exceptions import ManifestSyntaxError

logger = logging.getLogger("meta_compiler.core.ir")


@dataclass(frozen=True)
class NodeIR:
    """Canonical, immutable intermediate representation of a workflow node."""

    id: str
    type: str
    inputs: tuple[str, ...] = field(default_factory=tuple)
    attributes: dict[str, Any] = field(default_factory=dict)
    disabled: bool = False

    def __post_init__(self) -> None:
        """Enforces immutable tuple conversion and deep-freezes mutable fields."""
        if isinstance(self.inputs, list):
            object.__setattr__(self, "inputs", tuple(self.inputs))
        if not isinstance(self.attributes, ImmutableDict):
            object.__setattr__(self, "attributes", freeze_value(self.attributes))

    def to_dict(self) -> dict[str, Any]:
        """Serializes NodeIR instance to a primitive dictionary."""
        return {
            "id": self.id,
            "type": self.type,
            "inputs": list(self.inputs),
            "attributes": dict(self.attributes),
            "disabled": self.disabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NodeIR":
        """Deserializes a primitive dictionary into a validated NodeIR instance."""
        if not isinstance(data, dict):
            raise ManifestSyntaxError(
                f"NodeIR deserialization expects a dict, got {type(data).__name__}",
                details={"received_type": type(data).__name__},
            )

        try:
            node_id = data["id"]
            node_type = data["type"]
        except KeyError as err:
            raise ManifestSyntaxError(
                f"NodeIR payload missing mandatory key: '{err.args[0]}'",
                details={"missing_key": err.args[0], "payload": data},
            ) from err

        inputs_raw = data.get("inputs", [])
        if not isinstance(inputs_raw, (list, tuple)):
            raise ManifestSyntaxError(
                f"NodeIR 'inputs' field must be a list/tuple, got {type(inputs_raw).__name__}",
                details={"node_id": node_id, "received_type": type(inputs_raw).__name__},
            )

        attributes_raw = data.get("attributes", {})
        if not isinstance(attributes_raw, dict):
            raise ManifestSyntaxError(
                f"NodeIR 'attributes' field must be a dict, got {type(attributes_raw).__name__}",
                details={"node_id": node_id, "received_type": type(attributes_raw).__name__},
            )

        return cls(
            id=str(node_id),
            type=str(node_type),
            inputs=tuple(str(i) for i in inputs_raw),
            attributes=dict(attributes_raw),
            disabled=bool(data.get("disabled", False)),
        )


@dataclass(frozen=True)
class EdgeIR:
    """Canonical, immutable intermediate representation of a dependency edge."""

    source: str
    target: str
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Deep-freezes the mutable ``attributes`` field."""
        if not isinstance(self.attributes, ImmutableDict):
            object.__setattr__(self, "attributes", freeze_value(self.attributes))

    def to_dict(self) -> dict[str, Any]:
        """Serializes EdgeIR instance to a primitive dictionary."""
        return {
            "source": self.source,
            "target": self.target,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EdgeIR":
        """Deserializes a primitive dictionary into a validated EdgeIR instance."""
        if not isinstance(data, dict):
            raise ManifestSyntaxError(
                f"EdgeIR deserialization expects a dict, got {type(data).__name__}",
                details={"received_type": type(data).__name__},
            )

        try:
            source = data["source"]
            target = data["target"]
        except KeyError as err:
            raise ManifestSyntaxError(
                f"EdgeIR payload missing mandatory key: '{err.args[0]}'",
                details={"missing_key": err.args[0], "payload": data},
            ) from err

        attributes_raw = data.get("attributes", {})
        if not isinstance(attributes_raw, dict):
            raise ManifestSyntaxError(
                f"EdgeIR 'attributes' field must be a dict, got {type(attributes_raw).__name__}",
                details={
                    "source": source,
                    "target": target,
                    "received_type": type(attributes_raw).__name__,
                },
            )

        return cls(
            source=str(source),
            target=str(target),
            attributes=dict(attributes_raw),
        )


@dataclass(frozen=True)
class ManifestIR:
    """Canonical, immutable intermediate representation of a full workflow manifest."""

    namespace: str
    name: str
    version: str = "1.0.0"
    nodes: tuple[NodeIR, ...] = field(default_factory=tuple)
    edges: tuple[EdgeIR, ...] = field(default_factory=tuple)
    attributes: dict[str, Any] = field(default_factory=dict)
    manifest_hash: str | None = None

    def __post_init__(self) -> None:
        """Enforces immutable tuple conversions and deep-freezes mutable fields."""
        if isinstance(self.nodes, list):
            object.__setattr__(self, "nodes", tuple(self.nodes))
        if isinstance(self.edges, list):
            object.__setattr__(self, "edges", tuple(self.edges))
        if not isinstance(self.attributes, ImmutableDict):
            object.__setattr__(self, "attributes", freeze_value(self.attributes))

    def compute_canonical_hash(self) -> str:
        """Computes a deterministic SHA-256 hash of the normalized manifest payload."""
        normalized_payload = {
            "namespace": self.namespace,
            "name": self.name,
            "version": self.version,
            "nodes": [n.to_dict() for n in sorted(self.nodes, key=lambda x: x.id)],
            "edges": [e.to_dict() for e in sorted(self.edges, key=lambda x: (x.source, x.target))],
            "attributes": dict(self.attributes),
        }
        serialized = json.dumps(normalized_payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def with_computed_hash(self) -> Self:
        """Returns a new ManifestIR copy with the canonical hash populated."""
        return replace(self, manifest_hash=self.compute_canonical_hash())

    def to_dict(self) -> dict[str, Any]:
        """Serializes ManifestIR instance and nested IR entities to a primitive dictionary."""
        return {
            "namespace": self.namespace,
            "name": self.name,
            "version": self.version,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "attributes": dict(self.attributes),
            "manifest_hash": self.manifest_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ManifestIR":
        """Deserializes a primitive dictionary into a validated, hash-computed ManifestIR instance."""
        if not isinstance(data, dict):
            raise ManifestSyntaxError(
                f"ManifestIR deserialization expects a dict, got {type(data).__name__}",
                details={"received_type": type(data).__name__},
            )

        try:
            namespace = data["namespace"]
            name = data["name"]
        except KeyError as err:
            raise ManifestSyntaxError(
                f"ManifestIR payload missing mandatory key: '{err.args[0]}'",
                details={"missing_key": err.args[0]},
            ) from err

        raw_nodes = data.get("nodes", [])
        if not isinstance(raw_nodes, (list, tuple)):
            raise ManifestSyntaxError(
                f"ManifestIR 'nodes' field must be a list/tuple, got {type(raw_nodes).__name__}",
                details={"received_type": type(raw_nodes).__name__},
            )

        parsed_nodes: list[NodeIR] = []
        for idx, item in enumerate(raw_nodes):
            if isinstance(item, NodeIR):
                parsed_nodes.append(item)
            elif isinstance(item, dict):
                parsed_nodes.append(NodeIR.from_dict(item))
            else:
                raise ManifestSyntaxError(
                    f"Invalid node object at index {idx}: expected dict or NodeIR, got {type(item).__name__}",
                    details={"index": idx, "type": type(item).__name__},
                )

        raw_edges = data.get("edges", [])
        if not isinstance(raw_edges, (list, tuple)):
            raise ManifestSyntaxError(
                f"ManifestIR 'edges' field must be a list/tuple, got {type(raw_edges).__name__}",
                details={"received_type": type(raw_edges).__name__},
            )

        parsed_edges: list[EdgeIR] = []
        for idx, item in enumerate(raw_edges):
            if isinstance(item, EdgeIR):
                parsed_edges.append(item)
            elif isinstance(item, dict):
                parsed_edges.append(EdgeIR.from_dict(item))
            else:
                raise ManifestSyntaxError(
                    f"Invalid edge object at index {idx}: expected dict or EdgeIR, got {type(item).__name__}",
                    details={"index": idx, "type": type(item).__name__},
                )

        attributes_raw = data.get("attributes", {})
        if not isinstance(attributes_raw, dict):
            raise ManifestSyntaxError(
                f"ManifestIR 'attributes' field must be a dict, got {type(attributes_raw).__name__}",
                details={"received_type": type(attributes_raw).__name__},
            )

        instance = cls(
            namespace=str(namespace),
            name=str(name),
            version=str(data.get("version", "1.0.0")),
            nodes=tuple(parsed_nodes),
            edges=tuple(parsed_edges),
            attributes=dict(attributes_raw),
            manifest_hash=data.get("manifest_hash"),
        )

        if not instance.manifest_hash:
            instance = instance.with_computed_hash()

        logger.debug(
            "Successfully deserialized ManifestIR '%s/%s' with hash %s",
            instance.namespace,
            instance.name,
            instance.manifest_hash,
        )
        return instance
