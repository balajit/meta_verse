from enum import Enum
from typing import Any, Dict, List, Literal, Union
from pydantic import BaseModel, ConfigDict, Field, model_validator


class MutationType(str, Enum):
    PRUNE_BRANCH = "prune_branch"
    INJECT_FALLBACK = "inject_fallback"
    UPDATE_DEPENDENCIES = "update_dependencies"
    BYPASS_NODE = "bypass_node"


class DynamicNodeSpec(BaseModel):
    """Specifies a new node to be dynamically injected into the live DAG[cite: 4]."""
    node_id: str = Field(..., description="Unique identifier for the dynamic node")
    handler: str = Field(..., description="Import path or identifier for the step execution handler")
    inputs: Dict[str, Any] = Field(default_factory=dict, description="Input parameters or artifact bindings")
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    resource_limits: Dict[str, Any] = Field(
        default_factory=lambda: {"cpu": "1000m", "memory": "2Gi"},
        description="Container or task resource bounds",
    )


class PruneBranchOperation(BaseModel):
    """Prunes dead or unreachable downstream execution branches[cite: 4]."""
    op: Literal[MutationType.PRUNE_BRANCH] = MutationType.PRUNE_BRANCH
    target_node_id: str = Field(..., description="Root node of the subgraph branch to prune")
    prune_recursive: bool = Field(default=True, description="Recursively prune unreferenced downstream nodes")


class InjectFallbackOperation(BaseModel):
    """Splices a dynamic fallback node to replace or bypass a failed step[cite: 4]."""
    op: Literal[MutationType.INJECT_FALLBACK] = MutationType.INJECT_FALLBACK
    failed_node_id: str = Field(..., description="Failed node ID being mitigated")
    fallback_node: DynamicNodeSpec = Field(..., description="Complete spec of the fallback node to insert")
    reroute_downstream: bool = Field(default=True, description="Automatically rebind downstream dependencies")


class UpdateDependencyOperation(BaseModel):
    """Re-wires upstream node dependencies dynamically without touching completed nodes[cite: 4]."""
    op: Literal[MutationType.UPDATE_DEPENDENCIES] = MutationType.UPDATE_DEPENDENCIES
    target_node_id: str = Field(..., description="Node whose upstream dependencies are being updated")
    new_upstream_node_ids: List[str] = Field(..., min_length=1, description="Replacement list of parent node IDs")


class BypassNodeOperation(BaseModel):
    """Bypasses non-critical steps (e.g., visualization) by injecting mock completion artifacts[cite: 4]."""
    op: Literal[MutationType.BYPASS_NODE] = MutationType.BYPASS_NODE
    target_node_id: str = Field(..., description="Non-critical node to bypass")
    mock_output_artifacts: Dict[str, Any] = Field(..., description="Synthesized output payload satisfying downstream schema")


# Polymorphic operation type
MutationOperation = Union[
    PruneBranchOperation,
    InjectFallbackOperation,
    UpdateDependencyOperation,
    BypassNodeOperation,
]


class MutationSpec(BaseModel):
    """Root contract for dynamic DAG replanning requests[cite: 4]."""
    model_config = ConfigDict(extra="forbid")

    operations: List[MutationOperation] = Field(
        ...,
        min_length=1,
        description="Ordered sequence of atomic graph mutations",
    )
    preserve_upstream_state: bool = Field(
        default=True,
        description="Enforces strict immutability on completed upstream nodes[cite: 4]",
    )
    agent_reasoning: str = Field(
        ...,
        min_length=10,
        description="Triage agent root-cause explanation driving this graph mutation[cite: 4]",
    )

    @model_validator(mode="after")
    def validate_no_duplicate_targets(self) -> "MutationSpec":
        """Ensures multiple destructive operations do not target the same node simultaneously."""
        targets = [op.target_node_id if hasattr(op, "target_node_id") else op.failed_node_id for op in self.operations]
        if len(targets) != len(set(targets)):
            raise ValueError("Mutation operations contains conflicting duplicate target node IDs")
        return self