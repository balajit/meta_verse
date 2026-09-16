"""Unit tests for circuit breaker decorator across sync and async callables."""

import time
import pytest
from meta_resiliency.circuit_breaker import circuit_breaker
from meta_resiliency.exceptions import CircuitBreakerOpenError


def test_circuit_breaker_decorator_sync() -> None:
    @circuit_breaker(name="sync_cb_unique_test", failure_threshold=2, recovery_timeout=0.05)
    def sync_fn(fail: bool) -> str:
        if fail:
            raise ValueError("Failure forced")
        return "success"

    assert sync_fn(fail=False) == "success"
    with pytest.raises(ValueError):
        sync_fn(fail=True)
    with pytest.raises(ValueError):
        sync_fn(fail=True)

    with pytest.raises(CircuitBreakerOpenError):
        sync_fn(fail=False)

    time.sleep(0.2)
    assert sync_fn(fail=False) == "success"


@pytest.mark.asyncio
async def test_circuit_breaker_decorator_async() -> None:
    @circuit_breaker(name="async_cb_unique_test", failure_threshold=1, recovery_timeout=0.05)
    async def async_fn(fail: bool) -> str:
        if fail:
            raise RuntimeError("Async fail")
        return "async success"

    with pytest.raises(RuntimeError):
        await async_fn(fail=True)

    with pytest.raises(CircuitBreakerOpenError):
        await async_fn(fail=False)

    time.sleep(0.2)
    assert await async_fn(fail=False) == "async success"