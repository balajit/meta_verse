"""OpenTelemetry tracer utilities and parametrized @trace_span decorator."""

import functools
import inspect
import time
from typing import Any, Callable, Optional, TypeVar, cast

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode, Tracer

from meta_telemetry.exceptions import SpanExtractionError

F = TypeVar("F", bound=Callable[..., Any])


def get_tracer(name: str = "meta_telemetry") -> Tracer:
    """Retrieves an OpenTelemetry tracer instance from the global provider."""
    return trace.get_tracer(name)


def trace_span(
    name: Optional[str] = None,
    extract_attributes: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None,
    tracer_name: str = "meta_telemetry",
) -> Callable[[F], F]:
    """Parametrized decorator wrapping sync and async functions in OpenTelemetry trace spans.

    Args:
        name: Optional explicit name for the span. Defaults to qualified function name.
        extract_attributes: Callable accepting bound function arguments and returning span attributes.
        tracer_name: Name of the tracer instance to retrieve.
    """

    def decorator(func: F) -> F:
        span_name = name or func.__qualname__
        tracer = get_tracer(tracer_name)
        cached_signature = inspect.signature(func) if extract_attributes else None

        def _extract_attrs_safely(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
            if not extract_attributes or not cached_signature:
                return {}
            try:
                bound_args = cached_signature.bind(*args, **kwargs)
                bound_args.apply_defaults()
                extracted = extract_attributes(bound_args.arguments)
                return extracted if isinstance(extracted, dict) else {}
            except Exception as err:
                raise SpanExtractionError(
                    message=f"Attribute extraction failed for function '{func.__name__}': {err}",
                    function_name=func.__name__,
                    original_exception=err,
                ) from err

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                start_time = time.perf_counter()
                with tracer.start_as_current_span(span_name) as span:
                    try:
                        attrs = _extract_attrs_safely(args, kwargs)
                        for key, val in attrs.items():
                            if val is not None:
                                span.set_attribute(key, val)
                    except SpanExtractionError as extraction_err:
                        span.record_exception(extraction_err)

                    try:
                        result = await func(*args, **kwargs)
                        duration_ms = (time.perf_counter() - start_time) * 1000
                        span.set_attribute("execution.duration_ms", round(duration_ms, 3))
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as exc:
                        duration_ms = (time.perf_counter() - start_time) * 1000
                        span.set_attribute("execution.duration_ms", round(duration_ms, 3))
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        raise

            return cast(F, async_wrapper)

        else:

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                start_time = time.perf_counter()
                with tracer.start_as_current_span(span_name) as span:
                    try:
                        attrs = _extract_attrs_safely(args, kwargs)
                        for key, val in attrs.items():
                            if val is not None:
                                span.set_attribute(key, val)
                    except SpanExtractionError as extraction_err:
                        span.record_exception(extraction_err)

                    try:
                        result = func(*args, **kwargs)
                        duration_ms = (time.perf_counter() - start_time) * 1000
                        span.set_attribute("execution.duration_ms", round(duration_ms, 3))
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as exc:
                        duration_ms = (time.perf_counter() - start_time) * 1000
                        span.set_attribute("execution.duration_ms", round(duration_ms, 3))
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        raise

            return cast(F, sync_wrapper)

    return decorator