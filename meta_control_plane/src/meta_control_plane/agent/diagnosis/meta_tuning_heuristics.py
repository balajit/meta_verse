import logging
from typing import Any, Dict, Optional
from pydantic import BaseModel

from meta_control_plane.agent.diagnosis.meta_failure_classifier import FailureCategory, FailureDiagnosis
from meta_control_plane.api.schemas.meta_mutation_schemas import (
    BypassNodeOperation,
    DynamicNodeSpec,
    InjectFallbackOperation,
    MutationSpec,
)
from meta_control_plane.events.meta_telemetry_drivers import TelemetryContext

logger = logging.getLogger(__name__)


class ParameterOverridePlan(BaseModel):
    action_type: str  # "RETRY_WITH_OVERRIDE" or "REPLAN_DAG"
    override_config: Dict[str, Any] = {}
    mutation_spec: Optional[MutationSpec] = None


class HeuristicsEngine:
    """Calculates dynamic resource overrides (1.5x dynamic boost) or DAG mutation specs based on diagnosis and telemetry."""

    def compute_plan(
        self,
        diagnosis: FailureDiagnosis,
        context: TelemetryContext,
        cached_heuristics: Optional[Dict[str, Any]] = None,
    ) -> ParameterOverridePlan:
        cached_heuristics = cached_heuristics or {}

        # 1. Transient Infra Failures -> Parameter Overrides (1.5x VRAM Boost)
        if diagnosis.category == FailureCategory.TRANSIENT_INFRASTRUCTURE:
            current_vram = context.resource_metrics.get("vram_usage_bytes", 16 * 1024 * 1024 * 1024)
            current_cpu = context.resource_metrics.get("cpu_utilization", 1.0)

            # Apply historical scaling multiplier or default to 1.5x
            scale_factor = cached_heuristics.get("vram_multiplier", 1.5)
            target_vram = int(current_vram * scale_factor)

            logger.info(f"Calculated resource override: VRAM scaled by {scale_factor:.1f}x -> {target_vram} bytes")

            return ParameterOverridePlan(
                action_type="RETRY_WITH_OVERRIDE",
                override_config={
                    "vram_limit_bytes": target_vram,
                    "allocated_cores": max(2, int(current_cpu * 2)),
                    "retry_boost_factor": scale_factor,
                },
            )

        # 2. Deterministic Data Failures -> DAG Replanning[cite: 7]
        if diagnosis.category == FailureCategory.DETERMINISTIC_DATA:
            # Bypass non-critical steps (e.g. visualization) vs injecting fallbacks for pipeline steps[cite: 7]
            if "visualiz" in context.step_id.lower() or "plot" in context.step_id.lower():
                logger.info(f"Bypassing non-critical step: {context.step_id}[cite: 7]")
                mutation = MutationSpec(
                    operations=[
                        BypassNodeOperation(
                            target_node_id=context.step_id,
                            mock_output_artifacts={"status": "BYPASSED", "reason": "Non-critical step bypassed"},
                        )
                    ],
                    agent_reasoning=f"Bypassed non-critical step {context.step_id} following deterministic data fault[cite: 7].",
                )
            else:
                logger.info(f"Injecting fallback node for failed step: {context.step_id}[cite: 7]")
                fallback = DynamicNodeSpec(
                    node_id=f"{context.step_id}_fallback",
                    handler="meta_control_plane.handlers.fallback_sanitizer",
                    inputs={"source_artifact": context.input_artifacts.get("input_uri", "")},
                )
                mutation = MutationSpec(
                    operations=[
                        InjectFallbackOperation(
                            failed_node_id=context.step_id,
                            fallback_node=fallback,
                        )
                    ],
                    agent_reasoning=f"Spliced fallback sanitizer for step {context.step_id} schema mismatch[cite: 7].",
                )

            return ParameterOverridePlan(
                action_type="REPLAN_DAG",
                mutation_spec=mutation,
            )

        raise ValueError(f"Unhandled or unrecoverable failure category: {diagnosis.category}")