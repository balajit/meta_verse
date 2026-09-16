from __future__ import annotations

from enum import IntEnum
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class DeltaPriority(IntEnum):
    BASE = 10
    SYSTEM = 50
    USER_OVERRIDE = 100


class SpecDelta(BaseModel):
    target_model: str
    priority: DeltaPriority = DeltaPriority.BASE
    field_patches: dict[str, Any] = Field(default_factory=dict)


class ManifestMergeConflictError(Exception):
    """Raised when conflicting patches of identical priority cannot be resolved."""
    pass


class ManifestMerger:
    @staticmethod
    def merge(deltas: list[SpecDelta]) -> dict[str, Any]:
        sorted_deltas = sorted(deltas, key=lambda d: d.priority)
        merged_state: dict[str, dict[str, Any]] = {}

        for delta in sorted_deltas:
            model = delta.target_model
            if model not in merged_state:
                merged_state[model] = {}

            for field_name, patch_value in delta.field_patches.items():
                if field_name in merged_state[model] and delta.priority == DeltaPriority.BASE:
                    logger.warning("manifest_merge_conflict_overwritten", model=model, field=field_name)
                merged_state[model][field_name] = patch_value

        logger.info("manifest_merged_successfully", models_processed=len(merged_state))
        return merged_state