from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from meta_telemetry import get_tracer, trace_span

__all__ = [
    "get_logger",
    "get_tracer",
    "trace_span",
]


_STANDARD_LOG_RECORD_FIELDS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
    }
)


class _JsonLogFormatter(logging.Formatter):
    """Serialize log records as deterministic JSON objects."""

    def format(
        self,
        record: logging.LogRecord,
    ) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                tz=timezone.utc,
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_FIELDS:
                continue

            if key.startswith("_"):
                continue

            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)

        if record.exc_info is not None:
            payload["exception"] = self.formatException(
                record.exc_info
            )

        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )


def get_logger(
    name: str,
) -> logging.Logger:
    """Return a standard Python Logger configured for structured log output.

    Bridge method to supply logging capabilities alongside meta_telemetry's tracer.
    """
    if not name or not name.strip():
        raise ValueError("Logger name must not be empty.")

    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_JsonLogFormatter())

        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False

    return logger