import asyncio
import json
import logging
from typing import Any, Dict
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class HeuristicCacheManager:
    """Shared Redis cache for updating global hyperparameter tuning state upon verified step recovery[cite: 7]."""

    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

    async def get_heuristics(self, step_id: str) -> Dict[str, Any]:
        """Fetches historical tuning heuristics for a target step[cite: 7]."""
        data = await self.redis.get(f"heuristics:{step_id}")
        return json.loads(data) if data else {}

    async def sync_successful_recovery(self, step_id: str, applied_config: Dict[str, Any]):
        """Persists updated parameter heuristics following verified step recovery[cite: 7]."""
        key = f"heuristics:{step_id}"
        current = await self.get_heuristics(step_id)

        if "retry_boost_factor" in applied_config:
            new_multiplier = max(current.get("vram_multiplier", 1.0), applied_config["retry_boost_factor"])
            current["vram_multiplier"] = new_multiplier

        current["last_recovery_timestamp"] = asyncio.get_event_loop().time()
        await self.redis.set(key, json.dumps(current), ex=86400)  # 24h retention
        logger.info(f"Synchronized heuristic cache for step [{step_id}] -> {current}")