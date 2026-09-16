from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

class StaleWorkerError(Exception):
    """Raised when worker lease generation or version ID is stale."""
    pass

class WorkerFenceToken(BaseModel):
    worker_id: str
    lease_generation: int = Field(..., ge=0)
    version_id: int = Field(..., ge=0)

class DualLockFencing:
    @staticmethod
    def verify_fence(current: WorkerFenceToken, recorded: WorkerFenceToken) -> bool:
        if current.lease_generation < recorded.lease_generation or current.version_id < recorded.version_id:
            logger.warning("stale_worker_fenced_out", current=current.model_dump(), recorded=recorded.model_dump())
            raise StaleWorkerError("Worker fence rejected: current lease or version is stale compared to database state.")
        logger.debug("worker_fence_verified", worker_id=current.worker_id, lease_generation=current.lease_generation)
        return True