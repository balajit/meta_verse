"""Pybreaker-backed circuit breaker implementation with telemetry integration."""

import asyncio
import datetime
from functools import wraps
from typing import Any, Callable, Tuple, Type, TypeVar, cast
import pybreaker

from meta_resiliency.exceptions import CircuitBreakerOpenError
from meta_resiliency.telemetry import (
    get_resilience_tracer,
    log_resilience_error,
    log_resilience_event,
    mark_span_error,
)

F = TypeVar("F", bound=Callable[..., Any])


class TelemetryCircuitBreakerListener(pybreaker.CircuitBreakerListener):
    """Listener bridge connecting pybreaker state transitions to OpenTelemetry and structured logging."""

    def state_change(self, cb: pybreaker.CircuitBreaker, old_state: Any, new_state: Any) -> None:
        if getattr(new_state, "name", None) == pybreaker.STATE_OPEN:
            # Synchronize timestamp using naive UTC to match pybreaker's internal clock evaluation
            setattr(cb, "_opened_at", datetime.datetime.utcnow())

        log_resilience_event(
            "circuit_breaker_state_change",
            str(getattr(new_state, "name", new_state)),
            {
                "circuit_name": cb.name,
                "previous_state": str(getattr(old_state, "name", old_state)),
                "failure_count": cb.fail_counter,
            },
        )


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    expected_exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """Decorator guarding function execution using a pybreaker CircuitBreaker state machine."""
    if not name or not name.strip():
        raise ValueError("Circuit breaker name must be a non-empty string.")
    if failure_threshold <= 0:
        raise ValueError("failure_threshold must be an integer greater than zero.")
    if recovery_timeout < 0:
        raise ValueError("recovery_timeout must be a non-negative number.")
    if not expected_exceptions:
        raise ValueError("expected_exceptions tuple must contain at least one Exception type.")

    breaker = pybreaker.CircuitBreaker(
        fail_max=failure_threshold,
        reset_timeout=recovery_timeout,
        exclude=[lambda exc: not isinstance(exc, expected_exceptions)],
        listeners=[TelemetryCircuitBreakerListener()],
        name=name,
    )

    def decorator(func: F) -> F:
        is_async = asyncio.iscoroutinefunction(func)
        tracer = get_resilience_tracer()

        if is_async:
            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with tracer.start_as_current_span(f"circuit_breaker:{name}") as span:
                    if span and span.is_recording():
                        span.set_attribute("circuit.name", name)
                        span.set_attribute("circuit.initial_state", str(breaker.current_state))
                        span.set_attribute("circuit.failure_threshold", failure_threshold)

                    try:
                        breaker.state.before_call(func, *args, **kwargs)
                    except pybreaker.CircuitBreakerError as cb_err:
                        err = CircuitBreakerOpenError(
                            f"Circuit breaker '{name}' is OPEN. Execution rejected.",
                            context={
                                "circuit_name": name,
                                "state": str(breaker.current_state),
                                "failure_threshold": failure_threshold,
                                "recovery_timeout": recovery_timeout,
                            },
                        )
                        mark_span_error(span, err)
                        log_resilience_error("circuit_breaker_rejected", err, err.context)
                        raise err from cb_err

                    try:
                        result = await func(*args, **kwargs)
                        breaker.state._handle_success()
                        if span and span.is_recording():
                            span.set_attribute("circuit.final_state", str(breaker.current_state))
                        return result
                    except Exception as exc:
                        try:
                            breaker.state._handle_error(exc, reraise=False)
                        except pybreaker.CircuitBreakerError:
                            pass
                        if span and span.is_recording():
                            span.set_attribute("circuit.final_state", str(breaker.current_state))
                        mark_span_error(span, exc)
                        raise

            return cast(F, async_wrapper)

        else:
            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                with tracer.start_as_current_span(f"circuit_breaker:{name}") as span:
                    if span and span.is_recording():
                        span.set_attribute("circuit.name", name)
                        span.set_attribute("circuit.initial_state", str(breaker.current_state))
                        span.set_attribute("circuit.failure_threshold", failure_threshold)

                    try:
                        breaker.state.before_call(func, *args, **kwargs)
                    except pybreaker.CircuitBreakerError as cb_err:
                        err = CircuitBreakerOpenError(
                            f"Circuit breaker '{name}' is OPEN. Execution rejected.",
                            context={
                                "circuit_name": name,
                                "state": str(breaker.current_state),
                                "failure_threshold": failure_threshold,
                                "recovery_timeout": recovery_timeout,
                            },
                        )
                        mark_span_error(span, err)
                        log_resilience_error("circuit_breaker_rejected", err, err.context)
                        raise err from cb_err

                    try:
                        result = func(*args, **kwargs)
                        breaker.state._handle_success()
                        if span and span.is_recording():
                            span.set_attribute("circuit.final_state", str(breaker.current_state))
                        return result
                    except Exception as exc:
                        try:
                            breaker.state._handle_error(exc, reraise=False)
                        except pybreaker.CircuitBreakerError:
                            pass
                        if span and span.is_recording():
                            span.set_attribute("circuit.final_state", str(breaker.current_state))
                        mark_span_error(span, exc)
                        raise

            return cast(F, sync_wrapper)

    return decorator