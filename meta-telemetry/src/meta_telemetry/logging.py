"""Structured JSON logging formatter with OpenTelemetry context injection and file handling."""

import datetime
import json
import logging
from logging.handlers import BaseRotatingHandler
import os
from pathlib import Path
from typing import Any, Optional

from opentelemetry import trace

from meta_telemetry.exceptions import LoggingFormattingError


class DateSeqRotatingFileHandler(BaseRotatingHandler):
    """File handler writing to an active date-stamped log file and shifting full logs

    downward into versioned archives (_v1.log = prev current, _v2.log = prev prev current).

    File Naming Rules:
    - Active log:        {app_name}_{DDMMYY_HHMMSS}.log
    - Most recent prev:  {app_name}_{DDMMYY_HHMMSS}_v1.log
    - Older archives:    {app_name}_{DDMMYY_HHMMSS}_v2.log ... _v{N}.log
    """

    DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB

    def __init__(
        self,
        base_dir: str | Path,
        app_name: str = "meta_app",
        max_bytes: int = DEFAULT_MAX_BYTES,
        backup_count: int = 5,
        encoding: str = "utf-8",
        delay: bool = False,
        date_format: str = "%d%m%y_%H%M%S",
        use_utc: bool = True,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.app_name = app_name
        self.maxBytes = max_bytes
        self.backupCount = backup_count
        self.date_format = date_format
        self.use_utc = use_utc

        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._current_date_str = self._get_date_string()

        active_filepath = self._get_active_filepath(self._current_date_str)
        super().__init__(
            filename=str(active_filepath),
            mode="a",
            encoding=encoding,
            delay=delay,
        )

    def _get_date_string(self) -> str:
        if self.use_utc:
            now = datetime.datetime.now(datetime.timezone.utc)
        else:
            now = datetime.datetime.now()
        return now.strftime(self.date_format)

    def _get_active_filepath(self, date_str: str) -> Path:
        return self.base_dir / f"{self.app_name}_{date_str}.log"

    def _get_versioned_filepath(self, date_str: str, seq: int) -> Path:
        return self.base_dir / f"{self.app_name}_{date_str}_v{seq}.log"

    def _get_temp_filepath(self, date_str: str) -> Path:
        return self.base_dir / f"{self.app_name}_{date_str}_tmp.log"

    def _get_highest_sequence_number(self, date_str: str) -> int:
        seq = 1
        while self._get_versioned_filepath(date_str, seq).exists():
            seq += 1
        return seq - 1

    def shouldRollover(self, record: logging.LogRecord) -> bool:
        """Determines if a rollover is required due to date boundary change or file size."""
        if self.stream is None:
            self.stream = self._open()

        current_date = self._get_date_string()
        if current_date != self._current_date_str:
            return True

        if self.maxBytes > 0:
            msg = f"{self.format(record)}\n"
            self.stream.seek(0, os.SEEK_END)
            if self.stream.tell() + len(msg.encode(self.encoding or "utf-8")) >= self.maxBytes:
                return True

        return False

    def doRollover(self) -> None:
        """Executes downward log cascade safely."""
        if self.stream:
            self.stream.close()
            self.stream = None

        current_date = self._get_date_string()

        if current_date != self._current_date_str:
            self._current_date_str = current_date
            self.baseFilename = str(self._get_active_filepath(current_date))
        else:
            active_path = Path(self.baseFilename)
            if active_path.exists() and active_path.stat().st_size > 0:
                tmp_path = self._get_temp_filepath(current_date)

                if tmp_path.exists():
                    tmp_path.unlink()
                active_path.rename(tmp_path)

                highest_seq = self._get_highest_sequence_number(current_date)
                for i in range(highest_seq, 0, -1):
                    src_file = self._get_versioned_filepath(current_date, i)
                    dst_file = self._get_versioned_filepath(current_date, i + 1)

                    if self.backupCount > 0 and (i + 1) > self.backupCount:
                        if src_file.exists():
                            src_file.unlink()
                    else:
                        if src_file.exists():
                            src_file.rename(dst_file)

                v1_file = self._get_versioned_filepath(current_date, 1)
                if self.backupCount > 0 or not v1_file.exists():
                    tmp_path.rename(v1_file)
                elif tmp_path.exists():
                    tmp_path.unlink()

        if not self.delay:
            self.stream = self._open()


def _default_json_serializer(obj: Any) -> Any:
    """Fallback JSON serializer handling non-standard types safely."""
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    if isinstance(obj, Exception):
        return {"type": type(obj).__name__, "message": str(obj)}
    try:
        return str(obj)
    except Exception:
        return "<unserializable_object>"


class StructuredJsonFormatter(logging.Formatter):
    """Formatter outputting JSON logs enriched with trace_id, span_id, and service metadata."""

    RESERVED_LOG_RECORD_ATTRS = {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "module", "msecs",
        "msg", "name", "pathname", "process", "processName", "relativeCreated",
        "stack_info", "thread", "threadName", "taskName",
    }

    def __init__(
        self,
        service_name: str = "meta_service",
        environment: str = "production",
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
    ) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.service_name = service_name
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        """Formats a standard logging record into a structured JSON string."""
        now = datetime.datetime.fromtimestamp(record.created, tz=datetime.timezone.utc)

        log_payload: dict[str, Any] = {
            "timestamp": now.isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": {
                "name": self.service_name,
                "environment": self.environment,
            },
            "code": {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            },
        }

        span = trace.get_current_span()
        span_context = span.get_span_context()
        if span_context and span_context.is_valid:
            log_payload["trace_id"] = f"{span_context.trace_id:032x}"
            log_payload["span_id"] = f"{span_context.span_id:016x}"
            log_payload["trace_flags"] = int(span_context.trace_flags)

        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            log_payload["exception"] = {
                "details": record.exc_text,
            }

        extra_data: dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key not in self.RESERVED_LOG_RECORD_ATTRS:
                extra_data[key] = value

        if extra_data:
            log_payload["extra"] = extra_data

        try:
            return json.dumps(log_payload, default=_default_json_serializer, ensure_ascii=False)
        except Exception as err:
            formatting_err = LoggingFormattingError(
                message=f"Failed to serialize log record to JSON: {err}",
                log_record_name=record.name,
                original_exception=err,
            )
            fallback_payload = {
                "timestamp": now.isoformat(),
                "level": "ERROR",
                "logger": "meta_telemetry.logging",
                "message": f"Failed to format log record: {str(err)}",
                "original_message": record.getMessage(),
                "error_details": formatting_err.to_dict(),
            }
            return json.dumps(fallback_payload)