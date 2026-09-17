import asyncio
from typing import Dict, Any, Optional

class CacheGuard:
    """Thread-safe and async-safe in-memory cache for precomputed graph lineage outcomes[cite: 1]."""

    def __init__(self) -> None:
        self._cache: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            return self._cache.get(key)

    async def set(self, key: str, value: Any) -> None:
        async with self._lock:
            self._cache[key] = value

    async def invalidate(self, key: str) -> None:
        async with self._lock:
            self._cache.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()