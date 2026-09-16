"""Tests for context isolation, async tasks, and threads."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import pytest

from meta_context import (
    ContextNotSetError,
    ContextScopeError,
    TenantContext,
    bind_async_executor,
    bind_context,
    capture_snapshot,
    get_correlation_id,
    get_tenant_context,
    run_with_context,
)


def test_correlation_id_auto_generation() -> None:
    with bind_context() as scope:
        cid = get_correlation_id()
        assert cid is not None
        assert len(cid) == 36
    assert get_correlation_id() is None


def test_explicit_correlation_id() -> None:
    custom_id = "test-corr-id-12345"
    with bind_context(correlation_id=custom_id):
        assert get_correlation_id() == custom_id
    assert get_correlation_id() is None


def test_required_correlation_id_raises() -> None:
    with pytest.raises(ContextNotSetError):
        get_correlation_id(required=True)


@pytest.mark.asyncio
async def test_asyncio_task_isolation() -> None:
    async def task_worker(tenant_id: str) -> str | None:
        tenant = TenantContext(tenant_id=tenant_id)
        with bind_context(tenant_context=tenant):
            await asyncio.sleep(0.01)
            active = get_tenant_context()
            return active.tenant_id if active else None

    results = await asyncio.gather(
        task_worker("tenant_A"),
        task_worker("tenant_B"),
        task_worker("tenant_C"),
    )
    assert results == ["tenant_A", "tenant_B", "tenant_C"]


def test_thread_pool_executor_propagation() -> None:
    tenant = TenantContext(tenant_id="thread_tenant")
    with bind_context(tenant_context=tenant):
        snapshot = capture_snapshot()

    def thread_target() -> str | None:
        return run_with_context(snapshot, lambda: get_tenant_context().tenant_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(thread_target)
        assert future.result() == "thread_tenant"


def test_bound_executor_wrapper() -> None:
    tenant = TenantContext(tenant_id="executor_tenant")
    with bind_context(tenant_context=tenant):
        with ThreadPoolExecutor(max_workers=1) as pool:
            bound_pool = bind_async_executor(pool)
            future = bound_pool.submit(lambda: get_tenant_context().tenant_id)
            assert future.result() == "executor_tenant"


def test_scope_double_reset_raises() -> None:
    with bind_context() as scope:
        scope.reset()
        with pytest.raises(ContextScopeError):
            scope.reset()