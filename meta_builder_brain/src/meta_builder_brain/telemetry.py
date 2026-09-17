"""src/meta_builder_brain/telemetry.py
Telemetry setup and tracing utilities for Meta Builder Brain.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Callable, Optional, TypeVar
from functools import wraps

from meta_telemetry.logging import StructuredJsonFormatter
from meta_telemetry.tracing import trace_span
from meta_builder_brain.exceptions import TelemetryInitError

F = TypeVar("F", bound=Callable[..., Any])


def setup_telemetry(
    log_level: str = "INFO",
    log_file_path: Optional[str] = None,
) -> None:
    """Configures root logger handlers and formatting with fallback recovery."""
    root_logger = logging.getLogger()

    try:
        root_logger.setLevel(log_level.upper())
    except (ValueError, AttributeError) as exc:
        raise TelemetryInitError(f"Invalid log level specified: '{log_level}'") from exc

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(StructuredJsonFormatter())
    root_logger.addHandler(stream_handler)

    if log_file_path:
        try:
            directory = os.path.dirname(log_file_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            file_handler = logging.FileHandler(log_file_path)
            file_handler.setFormatter(StructuredJsonFormatter())
            root_logger.addHandler(file_handler)
        except (OSError, IOError) as exc:
            root_logger.warning(
                f"Failed to initialize file logger at path '{log_file_path}'. Falling back to stdout."
            )
            raise TelemetryInitError(
                f"Cannot write logs to file path '{log_file_path}': {exc}"
            ) from exc


def with_trace(span_name: str) -> Callable[[F], F]:
    """Decorator wrapping functions in a telemetry trace span."""

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return trace_span(name=span_name)(func)(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator