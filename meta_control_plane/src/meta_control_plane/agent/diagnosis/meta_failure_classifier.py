from enum import Enum
import re
from typing import List
from pydantic import BaseModel, Field

from meta_control_plane.events.meta_telemetry_drivers import TelemetryContext


class FailureCategory(str, Enum):
    TRANSIENT_INFRASTRUCTURE = "transient_infrastructure"  # Routes to parameter tuning / step retry[cite: 5]
    DETERMINISTIC_DATA = "deterministic_data"              # Routes to DAG replanning[cite: 5]
    UNRECOVERABLE_INVARIANT = "unrecoverable_invariant"    # Routes to human escalation[cite: 5]


class FailureDiagnosis(BaseModel):
    category: FailureCategory
    root_cause_summary: str
    suggested_action: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)


class FailureClassifierEngine:
    """Categorizes runtime step failures based on stack trace patterns and telemetry metrics[cite: 5]."""

    # Error signature matchers
    TRANSIENT_PATTERNS = [
        re.compile(r"OutOfMemoryError", re.IGNORECASE),
        re.compile(r"CUDA VRAM exhausted", re.IGNORECASE),
        re.compile(r"ConnectionResetError", re.IGNORECASE),
        re.compile(r"TimeoutError", re.IGNORECASE),
        re.compile(r"503 Service Unavailable", re.IGNORECASE),
    ]

    DATA_PATTERNS = [
        re.compile(r"ValidationError", re.IGNORECASE),
        re.compile(r"SchemaMismatch", re.IGNORECASE),
        re.compile(r"KeyError", re.IGNORECASE),
        re.compile(r"CorruptAssetException", re.IGNORECASE),
        re.compile(r"InvalidSpatialFormat", re.IGNORECASE),
    ]

    INVARIANT_PATTERNS = [
        re.compile(r"PermissionDenied", re.IGNORECASE),
        re.compile(r"Unauthorized", re.IGNORECASE),
        re.compile(r"InvalidToken", re.IGNORECASE),
        re.compile(r"SecurityContextMissing", re.IGNORECASE),
        re.compile(r"InvariantViolation", re.IGNORECASE),
    ]

    def classify(self, context: TelemetryContext) -> FailureDiagnosis:
        combined_logs = " ".join(context.stack_trace)

        # 1. Unrecoverable security / auth invariants
        for pattern in self.INVARIANT_PATTERNS:
            if pattern.search(combined_logs):
                return FailureDiagnosis(
                    category=FailureCategory.UNRECOVERABLE_INVARIANT,
                    root_cause_summary=f"Security/Auth invariant violation detected: {pattern.pattern}",
                    suggested_action="Escalate immediately to Ops with auth diagnostic context[cite: 5].",
                    confidence_score=0.99,
                )

        # 2. Transient infrastructure errors
        for pattern in self.TRANSIENT_PATTERNS:
            if pattern.search(combined_logs):
                return FailureDiagnosis(
                    category=FailureCategory.TRANSIENT_INFRASTRUCTURE,
                    root_cause_summary=f"Transient infra resource limit hit: {pattern.pattern}",
                    suggested_action="Route to retry_step with increased memory/timeout parameters[cite: 5].",
                    confidence_score=0.95,
                )

        # 3. Deterministic data errors
        for pattern in self.DATA_PATTERNS:
            if pattern.search(combined_logs):
                return FailureDiagnosis(
                    category=FailureCategory.DETERMINISTIC_DATA,
                    root_cause_summary=f"Deterministic schema or data error: {pattern.pattern}",
                    suggested_action="Route to replan_dag to splice dynamic validation/fallback node[cite: 5].",
                    confidence_score=0.90,
                )

        # Default fallback categorization
        return FailureDiagnosis(
            category=FailureCategory.TRANSIENT_INFRASTRUCTURE,
            root_cause_summary="Unrecognized error pattern; defaulting to transient infrastructure retry.",
            suggested_action="Attempt bounded retry with telemetry capture.",
            confidence_score=0.50,
        )