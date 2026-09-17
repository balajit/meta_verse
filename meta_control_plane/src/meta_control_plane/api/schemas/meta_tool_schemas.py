from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CapabilitiesGuardrail(BaseModel):
    is_read_only: bool = False
    requires_idempotency_key: bool = False
    max_execution_timeout_sec: int = 300


class InspectManifestRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(..., description="Unique workflow execution identifier")
    step_id: str = Field(..., description="Target DAG step node identifier")
    depth: int = Field(default=1, ge=1, le=5, description="Traversal depth for dependency tree inspection")


class InspectManifestResponse(BaseModel):
    run_id: str
    step_id: str
    graph_state: Dict[str, Any]
    artifacts: Dict[str, Any]
    execution_logs: List[str]
    telemetry_metrics: Dict[str, Any]


class RetryStepRequest(BaseModel):
    run_id: str
    step_id: str
    idempotency_key: str = Field(..., min_length=16, description="Cryptographic idempotency token")
    override_config: Dict[str, Any] = Field(default_factory=dict, description="Patched resource/execution parameters")


class RetryStepResponse(BaseModel):
    status: str
    run_id: str
    step_id: str
    retry_attempt_id: str
    idempotency_cached: bool = False


class MutationOperation(BaseModel):
    op: str = Field(..., pattern="^(prune|inject_fallback|update_dependency)$")
    target_node_id: str
    node_payload: Optional[Dict[str, Any]] = None


class MutationSpec(BaseModel):
    operations: List[MutationOperation]
    preserve_upstream_state: bool = True


class ReplanDAGRequest(BaseModel):
    run_id: str
    failed_step_id: str
    mutation_spec: MutationSpec


class ReplanDAGResponse(BaseModel):
    status: str
    run_id: str
    snapshot_id: str
    mutated_nodes: List[str]