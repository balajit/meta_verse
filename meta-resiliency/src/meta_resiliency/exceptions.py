"""Domain exception hierarchy for meta-resiliency."""

from typing import Any, Dict, Optional


class ResilienceError(Exception):
    """Base exception for all resilience errors with structured context support."""

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}


class CircuitBreakerOpenError(ResilienceError):
    """Raised when an operation is attempted while the circuit breaker is open."""


class RateLimitExceededError(ResilienceError):
    """Raised when an operation exceeds defined throughput limits."""


class MaxRetriesExceededError(ResilienceError):
    """Raised when retry attempts are exhausted without success."""


class BulkheadFullError(ResilienceError):
    """Raised when execution is rejected due to saturated bulkhead capacity."""


class ResilienceTimeoutError(ResilienceError):
    """Raised when execution exceeds allocated timeout bounds."""