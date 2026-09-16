"""Unit tests for tenacity-backed retries covering sync, async, backoff callbacks, and exhaustion."""

import pytest
from meta_resiliency.exceptions import MaxRetriesExceededError
from meta_resiliency.retries import retry


def test_retry_sync_success_and_exhaustion() -> None:
    attempts = 0

    @retry(max_attempts=3, min_backoff=0.01, max_backoff=0.02, retry_name="sync_retry_test")
    def sync_fn() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ValueError("Transient error")
        return "recovered"

    assert sync_fn() == "recovered"

    @retry(max_attempts=2, min_backoff=0.01, max_backoff=0.02, retry_exceptions=(ValueError,), retry_name="sync_exhaust_test")
    def failing_fn() -> str:
        raise ValueError("Persistent error")

    with pytest.raises(MaxRetriesExceededError):
        failing_fn()

    @retry(max_attempts=2, min_backoff=0.01, max_backoff=0.02, retry_exceptions=(TypeError,), retry_name="sync_unhandled_test")
    def unhandled_fn() -> str:
        raise ValueError("Non-retryable error")

    with pytest.raises(ValueError):
        unhandled_fn()


@pytest.mark.asyncio
async def test_retry_async_success_and_exhaustion() -> None:
    attempts = 0

    @retry(max_attempts=3, min_backoff=0.01, max_backoff=0.02, retry_name="async_retry_test")
    async def async_fn() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise RuntimeError("Async transient error")
        return "async recovered"

    assert await async_fn() == "async recovered"

    @retry(max_attempts=2, min_backoff=0.01, max_backoff=0.02, retry_exceptions=(RuntimeError,), retry_name="async_exhaust_test")
    async def async_failing_fn() -> str:
        raise RuntimeError("Async persistent error")

    with pytest.raises(MaxRetriesExceededError):
        await async_failing_fn()

    @retry(max_attempts=2, min_backoff=0.01, max_backoff=0.02, retry_exceptions=(TypeError,), retry_name="async_unhandled_test")
    async def async_unhandled_fn() -> str:
        raise RuntimeError("Non-retryable async error")

    with pytest.raises(RuntimeError):
        await async_unhandled_fn()