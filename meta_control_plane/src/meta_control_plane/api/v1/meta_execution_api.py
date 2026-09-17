import uuid
from fastapi import APIRouter, Depends, HTTPException, status
import redis.asyncio as aioredis

from meta_control_plane.api.schemas.meta_tool_schemas import RetryStepRequest, RetryStepResponse

router = APIRouter(prefix="/api/v1/execution", tags=["Control Plane - Execution"])


# Redis connection dependency
async def get_redis():
    client = aioredis.from_url("redis://localhost:6379/0", encoding="utf-8", decode_responses=True)
    try:
        yield client
    finally:
        await client.close()


@router.post(
    "/retry",
    response_model=RetryStepResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry step with parameter overrides",
)
async def retry_step(
        payload: RetryStepRequest,
        redis_client: aioredis.Redis = Depends(get_redis),
) -> RetryStepResponse:
    """Triggers step re-execution with patched configuration guarded by distributed idempotency locking[cite: 4]."""
    lock_key = f"idempotency:retry:{payload.idempotency_key}"

    # Set lock with 300-second TTL if key does not exist
    acquired = await redis_client.set(lock_key, "PROCESSING", nx=True, ex=300)

    if not acquired:
        existing_status = await redis_client.get(lock_key)
        return RetryStepResponse(
            status=existing_status or "PROCESSING",
            run_id=payload.run_id,
            step_id=payload.step_id,
            retry_attempt_id="cached_execution",
            idempotency_cached=True,
        )

    try:
        attempt_id = f"retry_{uuid.uuid4().hex[:8]}"
        # Dispatch isolated re-execution to task queue...

        await redis_client.set(lock_key, "ACCEPTED", ex=300)
        return RetryStepResponse(
            status="ACCEPTED",
            run_id=payload.run_id,
            step_id=payload.step_id,
            retry_attempt_id=attempt_id,
            idempotency_cached=False,
        )
    except Exception as exc:
        await redis_client.delete(lock_key)
        raise HTTPException(status_code=500, detail=f"Step retry dispatch failed: {str(exc)}")