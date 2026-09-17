import asyncio
import logging
import redis.asyncio as aioredis

from meta_control_plane.agent.controller.meta_heuristic_cache import HeuristicCacheManager
from meta_control_plane.agent.diagnosis.meta_failure_classifier import FailureDiagnosis
from meta_control_plane.agent.diagnosis.meta_tuning_heuristics import HeuristicsEngine
from meta_control_plane.agent.tools.meta_replan_tool import ReplanDAGTool
from meta_control_plane.agent.tools.meta_retry_tool import RetryStepTool
from meta_control_plane.events.meta_telemetry_drivers import ManifestTelemetryDriver, TelemetryContext

logger = logging.getLogger(__name__)


class SensePlanActVerifyController:
    """Implements the Sense-Plan-Act-Verify closed-loop autonomous control loop[cite: 7]."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        control_plane_url: str = "http://localhost:8000",
    ):
        self.redis_url = redis_url
        self.retry_tool = RetryStepTool(base_url=control_plane_url)
        self.replan_tool = ReplanDAGTool(base_url=control_plane_url)
        self.heuristics_engine = HeuristicsEngine()
        self.telemetry_driver = ManifestTelemetryDriver(control_plane_base_url=control_plane_url)

    async def execute_triage_cycle(self, diagnosis: FailureDiagnosis, context: TelemetryContext) -> bool:
        """Executes full autonomous triage iteration[cite: 7]."""
        redis = aioredis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
        cache_manager = HeuristicCacheManager(redis)

        try:
            # Phase 1 & 2: Sense & Plan[cite: 7]
            cached_heuristics = await cache_manager.get_heuristics(context.step_id)
            plan = self.heuristics_engine.compute_plan(diagnosis, context, cached_heuristics)

            # Phase 3: Act[cite: 7]
            logger.info(f"Executing action [{plan.action_type}] for step {context.step_id}")
            if plan.action_type == "RETRY_WITH_OVERRIDE":
                exec_res = await self.retry_tool.run(
                    run_id=context.run_id,
                    step_id=context.step_id,
                    override_config=plan.override_config,
                )
            elif plan.action_type == "REPLAN_DAG":
                exec_res = await self.replan_tool.run(
                    run_id=context.run_id,
                    failed_step_id=context.step_id,
                    mutation_spec=plan.mutation_spec,
                )
            else:
                return False

            if not exec_res.success:
                logger.error(f"Action execution failed with HTTP status {exec_res.status_code}")
                return False

            # Phase 4: Verify & Feedback Sync[cite: 7]
            verified = await self._verify_recovery(context.run_id, context.step_id)
            if verified:
                logger.info(f"Verification succeeded for {context.step_id}. Updating heuristic cache[cite: 7].")
                if plan.action_type == "RETRY_WITH_OVERRIDE":
                    await cache_manager.sync_successful_recovery(context.step_id, plan.override_config)
                return True

            logger.warning(f"Verification polling window expired for step {context.step_id}")
            return False

        finally:
            await redis.close()

    async def _verify_recovery(self, run_id: str, step_id: str, retries: int = 5) -> bool:
        """Polls execution telemetry over a monitoring window[cite: 7]."""
        for check in range(retries):
            await asyncio.sleep(2.0)
            try:
                telemetry = await self.telemetry_driver.fetch_telemetry_context(run_id, step_id)
                status = telemetry.graph_state.get("status")
                if status in ("COMPLETED", "ACCEPTED"):
                    return True
                if status == "FAILED":
                    return False
            except Exception as exc:
                logger.warning(f"Recovery check {check + 1} failed: {exc}")

        return False