"""Limits-backed rate limiters for sync and async execution boundaries."""

import asyncio
from functools import wraps
from typing import Any, Callable, TypeVar, cast
import limits
from limits import parse
from limits.strategies import MovingWindowRateLimiter
from limits.storage import MemoryStorage

from meta_resiliency.exceptions import RateLimitExceededError
from meta_resiliency.telemetry import get_resilience_tracer, log_resilience_error, mark_span_error

F = TypeVar("F", bound=Callable[..., Any])

_storage = MemoryStorage()
_limiter = MovingWindowRateLimiter(_storage)


def rate_limiter(
    max_calls: int = 100,
    period_seconds: float = 1.0,
    limiter_name: str = "default_limiter",
) -> Callable[[F], F]:
    """Decorator enforcing throughput constraints using open-source limits framework."""
    rate_string = f"{max_calls} per {int(period_seconds)} second" if period_seconds >= 1.0 else f"{max_calls}/{int(period_seconds * 1000)} ms"
    rate_item = parse(rate_string)

    def decorator(func: F) -> F:
        is_async = asyncio.iscoroutinefunction(func)
        tracer = get_resilience_tracer()

        if is_async:
            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with tracer.start_as_current_span(f"rate_limiter:{limiter_name}") as span:
                    if span and span.is_recording():
                        span.set_attribute("rate_limiter.name", limiter_name)
                        span.set_attribute("rate_limiter.max_calls", max_calls)

                    if not _limiter.hit(rate_item, limiter_name):
                        err = RateLimitExceededError(
                            f"Rate limit '{limiter_name}' exceeded ({max_calls} calls per {period_seconds}s).",
                            context={
                                "limiter_name": limiter_name,
                                "max_calls": max_calls,
                                "period_seconds": period_seconds,
                            },
                        )
                        mark_span_error(span, err)
                        log_resilience_error("rate_limit_exceeded", err, err.context)
                        raise err

                    try:
                        return await func(*args, **kwargs)
                    except Exception as exc:
                        mark_span_error(span, exc)
                        raise

            return cast(F, async_wrapper)

        else:
            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                with tracer.start_as_current_span(f"rate_limiter:{limiter_name}") as span:
                    if span and span.is_recording():
                        span.set_attribute("rate_limiter.name", limiter_name)
                        span.set_attribute("rate_limiter.max_calls", max_calls)

                    if not _limiter.hit(rate_item, limiter_name):
                        err = RateLimitExceededError(
                            f"Rate limit '{limiter_name}' exceeded ({max_calls} calls per {period_seconds}s).",
                            context={
                                "limiter_name": limiter_name,
                                "max_calls": max_calls,
                                "period_seconds": period_seconds,
                            },
                        )
                        mark_span_error(span, err)
                        log_resilience_error("rate_limit_exceeded", err, err.context)
                        raise err

                    try:
                        return func(*args, **kwargs)
                    except Exception as exc:
                        mark_span_error(span, exc)
                        raise

            return cast(F, sync_wrapper)

    return decorator