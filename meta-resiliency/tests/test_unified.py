"""Unit tests for composite resilience policy decorator."""

import pytest
from meta_resiliency.unified import resilience_policy


def test_unified_policy_sync() -> None:
    @resilience_policy(policy_name="sync_policy", max_attempts=2, min_backoff=0.01, max_backoff=0.02)
    def sync_fn() -> str:
        return "unified ok"

    assert sync_fn() == "unified ok"


@pytest.mark.asyncio
async def test_unified_policy_async() -> None:
    @resilience_policy(policy_name="async_policy", max_attempts=2, min_backoff=0.01, max_backoff=0.02)
    async def async_fn() -> str:
        return "async unified ok"

    assert await async_fn() == "async unified ok"