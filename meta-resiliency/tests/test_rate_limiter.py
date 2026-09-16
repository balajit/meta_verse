"""Unit tests for rate limiter decorator covering sync, async, and error propagation."""

import pytest
from meta_resiliency.exceptions import RateLimitExceededError
from meta_resiliency.rate_limiter import rate_limiter


def test_rate_limiter_sync() -> None:
    @rate_limiter(max_calls=2, period_seconds=1.0, limiter_name="sync_rl_test")
    def sync_fn(fail: bool = False) -> str:
        if fail:
            raise ValueError("Sync error")
        return "ok"

    assert sync_fn() == "ok"
    with pytest.raises(ValueError):
        sync_fn(fail=True)

    with pytest.raises(RateLimitExceededError):
        sync_fn()


@pytest.mark.asyncio
async def test_rate_limiter_async() -> None:
    @rate_limiter(max_calls=1, period_seconds=1.0, limiter_name="async_rl_test")
    async def async_fn(fail: bool = False) -> str:
        if fail:
            raise RuntimeError("Async error")
        return "ok"

    with pytest.raises(RuntimeError):
        await async_fn(fail=True)

    with pytest.raises(RateLimitExceededError):
        await async_fn()