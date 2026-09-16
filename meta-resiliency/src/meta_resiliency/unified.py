"""Unified composite resilience policy decorator combining retry, breaker, rate limiter, and bulkhead."""

from typing import Any, Callable, Tuple, Type, TypeVar
from meta_resiliency.bulkhead import bulkhead
from meta_resiliency.circuit_breaker import circuit_breaker
from meta_resiliency.rate_limiter import rate_limiter
from meta_resiliency.retries import retry

F = TypeVar("F", bound=Callable[..., Any])


def resilience_policy(
    policy_name: str = "unified_resilience_policy",
    max_attempts: int = 3,
    min_backoff: float = 0.1,
    max_backoff: float = 2.0,
    circuit_failure_threshold: int = 5,
    circuit_recovery_timeout: float = 30.0,
    rate_max_calls: int = 100,
    rate_period_seconds: float = 1.0,
    bulkhead_max_concurrent: int = 50,
    retry_exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """Applies Bulkhead -> RateLimiter -> CircuitBreaker -> Retries layer sequence."""

    def decorator(func: F) -> F:
        wrapped = retry(
            max_attempts=max_attempts,
            min_backoff=min_backoff,
            max_backoff=max_backoff,
            retry_exceptions=retry_exceptions,
            retry_name=f"{policy_name}_retry",
        )(func)

        wrapped = circuit_breaker(
            name=f"{policy_name}_cb",
            failure_threshold=circuit_failure_threshold,
            recovery_timeout=circuit_recovery_timeout,
            expected_exceptions=retry_exceptions,
        )(wrapped)

        wrapped = rate_limiter(
            max_calls=rate_max_calls,
            period_seconds=rate_period_seconds,
            limiter_name=f"{policy_name}_rate",
        )(wrapped)

        wrapped = bulkhead(
            max_concurrent=bulkhead_max_concurrent,
            bulkhead_name=f"{policy_name}_bulkhead",
        )(wrapped)

        return wrapped

    return decorator