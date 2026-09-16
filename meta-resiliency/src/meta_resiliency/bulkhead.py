"""AnyIO and threading-backed bulkhead isolation decorator for concurrency bounds."""

import asyncio
from functools import wraps
import threading
from typing import Any, Callable, TypeVar, cast
import anyio

from meta_resiliency.exceptions import BulkheadFullError
from meta_resiliency.telemetry import get_resilience_tracer, log_resilience_error, mark_span_error

F = TypeVar("F", bound=Callable[..., Any])


def bulkhead(
    max_concurrent: int = 50,
    bulkhead_name: str = "default_bulkhead",
) -> Callable[[F], F]:
    """Decorator enforcing max concurrent executions using AnyIO CapacityLimiter for async and BoundedSemaphore for sync."""
    async_limiter = anyio.CapacityLimiter(max_concurrent)
    sync_limiter = threading.BoundedSemaphore(max_concurrent)

    def decorator(func: F) -> F:
        is_async = asyncio.iscoroutinefunction(func)
        tracer = get_resilience_tracer()

        if is_async:
            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with tracer.start_as_current_span(f"bulkhead:{bulkhead_name}") as span:
                    if span and span.is_recording():
                        span.set_attribute("bulkhead.name", bulkhead_name)
                        span.set_attribute("bulkhead.max_concurrent", max_concurrent)

                    if async_limiter.borrowed_tokens >= max_concurrent:
                        err = BulkheadFullError(
                            f"Bulkhead '{bulkhead_name}' capacity saturated ({max_concurrent} max concurrent).",
                            context={"bulkhead_name": bulkhead_name, "max_concurrent": max_concurrent},
                        )
                        mark_span_error(span, err)
                        log_resilience_error("bulkhead_saturated", err, err.context)
                        raise err

                    async with async_limiter:
                        try:
                            return await func(*args, **kwargs)
                        except Exception as exc:
                            mark_span_error(span, exc)
                            raise

            return cast(F, async_wrapper)

        else:
            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                with tracer.start_as_current_span(f"bulkhead:{bulkhead_name}") as span:
                    if span and span.is_recording():
                        span.set_attribute("bulkhead.name", bulkhead_name)
                        span.set_attribute("bulkhead.max_concurrent", max_concurrent)

                    acquired = sync_limiter.acquire(blocking=False)
                    if not acquired:
                        err = BulkheadFullError(
                            f"Bulkhead '{bulkhead_name}' capacity saturated ({max_concurrent} max concurrent).",
                            context={"bulkhead_name": bulkhead_name, "max_concurrent": max_concurrent},
                        )
                        mark_span_error(span, err)
                        log_resilience_error("bulkhead_saturated", err, err.context)
                        raise err

                    try:
                        return func(*args, **kwargs)
                    except Exception as exc:
                        mark_span_error(span, exc)
                        raise
                    finally:
                        sync_limiter.release()

            return cast(F, sync_wrapper)

    return decorator