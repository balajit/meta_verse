"""
meta-resiliency core library package.
Provides battle-tested decorators for retries, circuit breakers, rate limits, and bulkheads.
"""

from meta_resiliency.bulkhead import bulkhead
from meta_resiliency.circuit_breaker import circuit_breaker
from meta_resiliency.config import ResilienceConfig
from meta_resiliency.exceptions import (
    BulkheadFullError,
    CircuitBreakerOpenError,
    MaxRetriesExceededError,
    RateLimitExceededError,
    ResilienceError,
    ResilienceTimeoutError,
)
from meta_resiliency.rate_limiter import rate_limiter
from meta_resiliency.retries import retry
from meta_resiliency.unified import resilience_policy

__version__ = "0.1.0"
__all__ = [
    "ResilienceConfig",
    "ResilienceError",
    "CircuitBreakerOpenError",
    "RateLimitExceededError",
    "MaxRetriesExceededError",
    "BulkheadFullError",
    "ResilienceTimeoutError",
    "circuit_breaker",
    "rate_limiter",
    "retry",
    "bulkhead",
    "resilience_policy",
    "__version__",
]