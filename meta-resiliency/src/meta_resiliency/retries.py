"""Tenacity-backed retry decorator components with telemetry context propagation."""

import asyncio
from functools import wraps
from typing import Any, Callable, Tuple, Type, TypeVar, cast
from tenacity import (
    AsyncRetrying,
    RetryError,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)
from meta_resiliency.exceptions import MaxRetriesExceededError
from meta_resiliency.telemetry import get_resilience_tracer, log_resilience_error, log_resilience_event, mark_span_error

F = TypeVar("F", bound=Callable[..., Any])


def retry(
    max_attempts: int = 3,
    min_backoff: float = 0.1,
    max_backoff: float = 2.0,
    retry_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    retry_name: str = "default_retry",
) -> Callable[[F], F]:
    """Decorates sync or async callables with tenacity exponential backoff retries."""

    def decorator(func: F) -> F:
        is_async = asyncio.iscoroutinefunction(func)
        tracer = get_resilience_tracer()

        if is_async:
            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                attempt_count = 0

                def on_retry_callback(retry_state: Any) -> None:
                    nonlocal attempt_count
                    attempt_count = retry_state.attempt_number
                    exc = retry_state.outcome.exception() if retry_state.outcome else None
                    log_resilience_event(
                        event_type="retry_attempt",
                        status="retrying",
                        metadata={
                            "retry_name": retry_name,
                            "attempt": attempt_count,
                            "max_attempts": max_attempts,
                            "exception": str(exc) if exc else None,
                        },
                    )

                retrier = AsyncRetrying(
                    stop=stop_after_attempt(max_attempts),
                    wait=wait_exponential_jitter(initial=min_backoff, max=max_backoff),
                    retry=retry_if_exception_type(retry_exceptions),
                    before_sleep=on_retry_callback,
                    reraise=False,
                )

                with tracer.start_as_current_span(f"retry:{retry_name}") as span:
                    if span and span.is_recording():
                        span.set_attribute("retry.name", retry_name)
                        span.set_attribute("retry.max_attempts", max_attempts)
                    try:
                        async for attempt in retrier:
                            with attempt:
                                return await func(*args, **kwargs)
                    except RetryError as retry_err:
                        last_exc = retry_err.last_attempt.exception() if retry_err.last_attempt else retry_err
                        err = MaxRetriesExceededError(
                            f"Retry policy '{retry_name}' exhausted after {max_attempts} attempts: {last_exc}",
                            context={
                                "retry_name": retry_name,
                                "max_attempts": max_attempts,
                                "last_exception": str(last_exc),
                            },
                        )
                        mark_span_error(span, err)
                        log_resilience_error("retry_exhausted", err, err.context)
                        raise err from last_exc
                    except Exception as exc:
                        mark_span_error(span, exc)
                        raise

            return cast(F, async_wrapper)

        else:
            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                attempt_count = 0

                def on_retry_callback(retry_state: Any) -> None:
                    nonlocal attempt_count
                    attempt_count = retry_state.attempt_number
                    exc = retry_state.outcome.exception() if retry_state.outcome else None
                    log_resilience_event(
                        event_type="retry_attempt",
                        status="retrying",
                        metadata={
                            "retry_name": retry_name,
                            "attempt": attempt_count,
                            "max_attempts": max_attempts,
                            "exception": str(exc) if exc else None,
                        },
                    )

                retrier = Retrying(
                    stop=stop_after_attempt(max_attempts),
                    wait=wait_exponential_jitter(initial=min_backoff, max=max_backoff),
                    retry=retry_if_exception_type(retry_exceptions),
                    before_sleep=on_retry_callback,
                    reraise=False,
                )

                with tracer.start_as_current_span(f"retry:{retry_name}") as span:
                    if span and span.is_recording():
                        span.set_attribute("retry.name", retry_name)
                        span.set_attribute("retry.max_attempts", max_attempts)
                    try:
                        for attempt in retrier:
                            with attempt:
                                return func(*args, **kwargs)
                    except RetryError as retry_err:
                        last_exc = retry_err.last_attempt.exception() if retry_err.last_attempt else retry_err
                        err = MaxRetriesExceededError(
                            f"Retry policy '{retry_name}' exhausted after {max_attempts} attempts: {last_exc}",
                            context={
                                "retry_name": retry_name,
                                "max_attempts": max_attempts,
                                "last_exception": str(last_exc),
                            },
                        )
                        mark_span_error(span, err)
                        log_resilience_error("retry_exhausted", err, err.context)
                        raise err from last_exc
                    except Exception as exc:
                        mark_span_error(span, exc)
                        raise

            return cast(F, sync_wrapper)

    return decorator