"""Unit tests for bulkhead decorator covering sync and async capacity bounds."""

import asyncio
import threading
import time
import pytest
from meta_resiliency.bulkhead import bulkhead
from meta_resiliency.exceptions import BulkheadFullError


def test_bulkhead_sync() -> None:
    @bulkhead(max_concurrent=1, bulkhead_name="sync_bh_test")
    def sync_fn(fail: bool = False) -> str:
        if fail:
            raise ValueError("Sync bulkhead error")
        return "ok"

    assert sync_fn() == "ok"
    with pytest.raises(ValueError):
        sync_fn(fail=True)


def test_bulkhead_sync_saturation() -> None:
    @bulkhead(max_concurrent=1, bulkhead_name="sync_sat_test")
    def slow_fn() -> str:
        time.sleep(0.1)
        return "ok"

    t = threading.Thread(target=slow_fn)
    t.start()
    time.sleep(0.02)

    with pytest.raises(BulkheadFullError):
        slow_fn()

    t.join()


@pytest.mark.asyncio
async def test_bulkhead_async() -> None:
    @bulkhead(max_concurrent=1, bulkhead_name="async_bh_test")
    async def async_fn(fail: bool = False) -> str:
        if fail:
            raise RuntimeError("Async bulkhead error")
        return "ok"

    assert await async_fn() == "ok"
    with pytest.raises(RuntimeError):
        await async_fn(fail=True)


@pytest.mark.asyncio
async def test_bulkhead_async_saturation() -> None:
    @bulkhead(max_concurrent=1, bulkhead_name="async_sat_test")
    async def slow_async_fn() -> str:
        await asyncio.sleep(0.1)
        return "ok"

    task = asyncio.create_task(slow_async_fn())
    await asyncio.sleep(0.02)

    with pytest.raises(BulkheadFullError):
        await slow_async_fn()

    await task