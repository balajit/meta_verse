from __future__ import annotations

import random

import structlog

logger = structlog.get_logger(__name__)

class RetryJitter:
    @staticmethod
    def calculate_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
        exponential_delay = min(max_delay, base_delay * (2 ** attempt))
        full_jitter_delay = random.uniform(0, exponential_delay)
        logger.debug("calculated_retry_jitter", attempt=attempt, delay=full_jitter_delay)
        return full_jitter_delay