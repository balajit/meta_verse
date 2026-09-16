from __future__ import annotations

import asyncio

import structlog

logger = structlog.get_logger(__name__)

class PipelineWorker:
    def __init__(self, worker_id: str, heartbeat_interval: float = 10.0) -> None:
        self.worker_id = worker_id
        self.heartbeat_interval = heartbeat_interval
        self._running = False

    async def start(self) -> None:
        self._running = True
        logger.info("pipeline_worker_started", worker_id=self.worker_id)
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                logger.debug("pipeline_worker_heartbeat_sent", worker_id=self.worker_id)
            except asyncio.CancelledError:
                logger.info("pipeline_worker_cancelled", worker_id=self.worker_id)
                break
            except Exception as e:
                logger.error("pipeline_worker_loop_error", error=str(e))

    async def stop(self) -> None:
        self._running = False
        logger.info("pipeline_worker_stopped", worker_id=self.worker_id)