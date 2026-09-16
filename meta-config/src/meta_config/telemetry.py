"""Telemetry integration for meta-config using meta-telemetry."""

from contextlib import contextmanager
import logging
from typing import Any, Dict, Generator
from meta_telemetry import get_tracer

__all__ = [
    "logger",
    "tracer",
    "trace_config_span",
    "log_config_event",
    "log_config_error",
]

# Standard library logger; structured JSON formatting is handled at the application root level
logger = logging.getLogger("meta_config")

# Tracer initialized using meta_telemetry's public API
tracer: Any | None
try:
    tracer = get_tracer("meta_config")
except Exception:
    tracer = None


@contextmanager
def trace_config_span(span_name: str) -> Generator[Any, None, None]:
    """Trace configuration operations using OpenTelemetry spans when available."""
    if tracer and hasattr(tracer, "start_as_current_span"):
        with tracer.start_as_current_span(span_name) as span:
            yield span
    else:
        yield None


def log_config_event(event_type: str, status: str, metadata: Dict[str, Any]) -> None:
    """Emit a structured log for configuration lifecycle events without leaking secrets."""
    safe_metadata = {
        k: v for k, v in metadata.items()
        if "password" not in k.lower() and "secret" not in k.lower()
    }
    logger.info(
        "Configuration event recorded",
        extra={
            "event_type": event_type,
            "status": status,
            "metadata": safe_metadata,
        },
    )


def log_config_error(event_type: str, error: Exception, metadata: Dict[str, Any]) -> None:
    """Emit a structured error log with actionable root-cause metadata."""
    logger.error(
        "Configuration error encountered during boot",
        extra={
            "event_type": event_type,
            "status": "failed",
            "error_type": error.__class__.__name__,
            "error_message": str(error),
            "metadata": metadata,
        },
        exc_info=True,
    )