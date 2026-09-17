import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from meta_builder_brain.lineage.cache import CacheGuard
from meta_builder_brain.lineage.closure import LineageClosureResolver

@pytest.mark.asyncio
async def test_cache_guard_operations():
    cache = CacheGuard()
    await cache.set("key1", "value1")
    assert await cache.get("key1") == "value1"

    await cache.invalidate("key1")
    assert await cache.get("key1") is None

    await cache.set("key2", "value2")
    await cache.clear()
    assert await cache.get("key2") is None


@pytest.mark.asyncio
async def test_lineage_closure_resolver(async_session: AsyncSession):
    resolver = LineageClosureResolver(async_session)
    await resolver.register_relation(
        ancestor_id="global", descendant_id="industry_fintech", depth=1
    )
    await resolver.register_relation(
        ancestor_id="industry_fintech", descendant_id="custom_client", depth=1
    )

    ancestors = await resolver.resolve_ancestors("custom_client")
