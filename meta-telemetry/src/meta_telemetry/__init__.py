"""Root exports for meta_telemetry package."""

from meta_telemetry.exceptions import (
    LoggingFormattingError,
    SpanExtractionError,
    TelemetryError,
)
from meta_telemetry.logging import DateSeqRotatingFileHandler, StructuredJsonFormatter
from meta_telemetry.tracing import get_tracer, trace_span

__all__ = [
    "DateSeqRotatingFileHandler",
    "StructuredJsonFormatter",
    "get_tracer",
    "trace_span",
    "TelemetryError",
    "SpanExtractionError",
    "LoggingFormattingError",
]