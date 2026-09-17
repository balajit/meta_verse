import logging
import time
from typing import Tuple
import redis.asyncio as aioredis

from meta_control_plane.agent.diagnosis.meta_failure_classifier import FailureCategory, FailureDiagnosis

logger = logging.getLogger(__name__)


class EscalationGuardEngine:
    """Enforces retry thresholds, execution patch budgets, and immediate escalation policies[cite: 6, 8]."""

    MAX_RESOURCE_RETRIES = 2  # Max 2 retries before DevOps escalation[cite: 8]
    MAX_PATCH_RUNTIME_SEC = 300.0  # Dynamic patch budget limit (300s)[cite: 8]

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

    async def evaluate_escalation(
        self, run_id: str, step_id: str, diagnosis: FailureDiagnosis
    ) -> Tuple[bool, str]:
        """Evaluates failure category and execution history against control plane threshold limits[cite: 6, 8]."""
        # 1. Permission / Auth failure -> Immediate escalation without retry[cite: 8]
        if diagnosis.category == FailureCategory.UNRECOVERABLE_INVARIANT:
            return True, f"Immediate escalation triggered by invariant violation: {diagnosis.root_cause_summary}"

        retry_key = f"escalation:retry_count:{run_id}:{step_id}"
        runtime_key = f"escalation:patch_start:{run_id}:{step_id}"

        # 2. Track resource exhaustion retry count[cite: 8]
        retry_count = await self.redis.incr(retry_key)
        if retry_count == 1:
            await self.redis.expire(retry_key, 86400)

        if retry_count > self.MAX_RESOURCE_RETRIES:
            return True, (
                f"Resource failure threshold exceeded ({retry_count - 1}/{self.MAX_RESOURCE_RETRIES} retries). "
                f"Escalating step [{step_id}] to DevOps[cite: 8]."
            )

        # 3. Track dynamic patch execution runtime budget ($>300\text{s}$)[cite: 8]
        start_time_bytes = await self.redis.get(runtime_key)
        now = time.time()

        if start_time_bytes is None:
            await self.redis.set(runtime_key, str(now), ex=3600)
        else:
            elapsed = now - float(start_time_bytes)
            if elapsed > self.MAX_PATCH_RUNTIME_SEC:
                return True, (
                    f"Dynamic patch runtime budget exceeded "
                    f"(${elapsed:.1f}\text{{s}} > {self.MAX_PATCH_RUNTIME_SEC}\text{{s}}$). "
                    f"Escalating step [{step_id}] to Ops[cite: 8]."
                )

        return False, ""