import asyncio
import json
import logging
from pydantic import BaseModel
import redis.asyncio as aioredis

from meta_control_plane.agent.diagnosis.meta_failure_classifier import FailureClassifierEngine
from meta_control_plane.events.meta_telemetry_drivers import ManifestTelemetryDriver

logger = logging.getLogger(__name__)


class WorkflowStepFailedEvent(BaseModel):
    event_id: str
    run_id: str
    step_id: str
    timestamp: float
    error_message: str


class WorkflowEventConsumer:
    """Async Pub/Sub subscriber intercepting WorkflowStepFailed event streams[cite: 5]."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        channel_name: str = "events:WorkflowStepFailed",
    ):
        self.redis_url = redis_url
        self.channel_name = channel_name
        self.telemetry_driver = ManifestTelemetryDriver()
        self.classifier = FailureClassifierEngine()
        self._is_running = False

    async def start(self):
        """Subscribes to failure topic and drives the telemetry gathering + diagnosis flow[cite: 5]."""
        redis = aioredis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
        pubsub = redis.pubsub()
        await pubsub.subscribe(self.channel_name)
        self._is_running = True
        logger.info(f"Subscribed to event channel: {self.channel_name}")

        try:
            while self._is_running:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message["type"] == "message":
                    await self._process_event(message["data"])
        finally:
            await pubsub.unsubscribe(self.channel_name)
            await redis.close()

    async def _process_event(self, raw_payload: str):
        """Pipeline execution: Parse Event -> Inspect Telemetry -> Classify Failure[cite: 5]."""
        try:
            event_data = json.loads(raw_payload)
            event = WorkflowStepFailedEvent(**event_data)
            logger.info(f"Intercepted failure event {event.event_id} for step {event.step_id}")

            # Step 1: Gather telemetry context via inspect_manifest
            telemetry_context = await self.telemetry_driver.fetch_telemetry_context(
                run_id=event.run_id, step_id=event.step_id
            )

            # Step 2: Classify failure root-cause
            diagnosis = self.classifier.classify(telemetry_context)
            logger.info(
                f"Diagnosed run {event.run_id} as [{diagnosis.category.value}] "
                f"(confidence: {diagnosis.confidence_score})"
            )

            # Step 3: Forward diagnosis payload to triage controller loop (Step 3)
            # await triage_controller.dispatch(diagnosis, telemetry_context)

        except Exception as exc:
            logger.error(f"Failed to process failure event stream: {str(exc)}", exc_info=True)

    def stop(self):
        self._is_running = False