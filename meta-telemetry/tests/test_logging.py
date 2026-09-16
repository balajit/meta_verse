import json
import logging
from pathlib import Path
import re
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from meta_telemetry.logging import DateSeqRotatingFileHandler, StructuredJsonFormatter


def test_structured_json_formatter_basic():
    formatter = StructuredJsonFormatter(service_name="test_service", environment="test")
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="/tmp/test.py",
        lineno=42,
        msg="User %s logged in",
        args=("alice",),
        exc_info=None,
    )

    output = formatter.format(record)
    data = json.loads(output)

    assert data["level"] == "INFO"
    assert data["logger"] == "test_logger"
    assert data["message"] == "User alice logged in"
    assert data["service"]["name"] == "test_service"
    assert data["service"]["environment"] == "test"
    assert data["code"]["line"] == 42


def test_structured_json_formatter_with_extra_and_non_serializable():
    formatter = StructuredJsonFormatter()

    class UnserializableClass:
        def __str__(self) -> str:
            return "custom_object"

    record = logging.LogRecord(
        name="test_logger",
        level=logging.WARNING,
        pathname="/tmp/test.py",
        lineno=10,
        msg="Warning event",
        args=(),
        exc_info=None,
    )
    record.__dict__["custom_obj"] = UnserializableClass()
    record.__dict__["numeric_val"] = 100

    output = formatter.format(record)
    data = json.loads(output)

    assert data["extra"]["custom_obj"] == "custom_object"
    assert data["extra"]["numeric_val"] == 100


def test_structured_json_formatter_injects_otel_trace_context():
    provider = TracerProvider()
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("test_tracer")

    formatter = StructuredJsonFormatter()

    with tracer.start_as_current_span("test_span") as span:
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="/tmp/test.py",
            lineno=20,
            msg="Inside span",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)

        span_context = span.get_span_context()
        expected_trace_id = f"{span_context.trace_id:032x}"
        expected_span_id = f"{span_context.span_id:016x}"

        assert data["trace_id"] == expected_trace_id
        assert data["span_id"] == expected_span_id


def test_timestamped_date_seq_cascade(tmp_path: Path):
    app_name = "meta_app_builder"
    max_bytes = 100  # Trigger rotation quickly

    handler = DateSeqRotatingFileHandler(
        base_dir=tmp_path,
        app_name=app_name,
        max_bytes=max_bytes,
    )
    logger = logging.getLogger("test_timestamp_cascade")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    logger.info("BATCH_1_LOG_DATA_00000_00000_00000_00000_00000")
    logger.info("BATCH_1_LOG_DATA_11111_11111_11111_11111_11111")

    logger.info("BATCH_2_LOG_DATA_22222_22222_22222_22222_22222")
    logger.info("BATCH_2_LOG_DATA_33333_33333_33333_33333_33333")

    logger.info("BATCH_3_LOG_DATA_44444_44444_44444_44444_44444")

    handler.close()

    log_files = sorted(tmp_path.glob("meta_app_builder_*.log"))
    assert len(log_files) >= 3

    pattern = re.compile(r"meta_app_builder_\d{6}_\d{6}(_v\d+)?\.log")
    for file_path in log_files:
        assert pattern.match(file_path.name), f"Filename {file_path.name} does not match ddmmyy_hhmmss standard"

    v1_files = list(tmp_path.glob("*_v1.log"))
    assert len(v1_files) > 0
    assert "BATCH_2" in v1_files[0].read_text()