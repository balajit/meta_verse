`REFERENCE.md` required updates to fix parameter default mismatches in `DateSeqRotatingFileHandler` (specifically `backup_count` and `date_format`) and remove non-existent runtime dependency requirements [source: 9].

Below is the complete, updated `REFERENCE.md` file maintained in its original format [source: 9].

```markdown
# meta-telemetry Documentation

`meta-telemetry` provides OpenTelemetry API tracing and structured JSON logging for high-throughput platform services.

---

## 1. Architectural Overview & Boundaries

### Purpose

`meta-telemetry` provides standard OpenTelemetry context propagation and structured JSON logging [source: 9]. It equips services with tracing and log serialization while maintaining a zero-footprint backend configuration [source: 9].

### Separation of Responsibilities

`meta-telemetry` relies strictly on `opentelemetry-api` for instrumentation [source: 9]. It deliberately omits runtime backend initialization [source: 9]. Delegating tracer provider configuration (`TracerProvider`), span processing (`BatchSpanProcessor`, `SimpleSpanProcessor`), and exporter management (`OTLPSpanExporter`, `InMemorySpanExporter`) to the host application runtime or test framework (e.g., `opentelemetry-sdk`) ensures telemetry initialization remains isolated to application startup scripts [source: 9].


```

┌─────────────────────────────────────────────────────────────────┐
│                      Host Application / SDK                     │
│  (Configures TracerProvider, OTLP Exporters, Log Handlers)      │
└────────────────────────────────┬────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────┐
│                         meta-telemetry                          │
│  ┌─────────────────────────────┬─────────────────────────────┐  │
│  │    @trace_span Decorator    │   StructuredJsonFormatter   │  │
│  └──────────────┬──────────────┴──────────────┬──────────────┘  │
└─────────────────┼─────────────────────────────┼─────────────────┘
│                             │
▼                             ▼
opentelemetry-api Tracing           Python logging Pipeline

```

### Dependency Strategy

The library enforces minimal runtime dependencies (`opentelemetry-api>=1.27.0`) [source: 9]. This prevents dependency graph bloat and transitive library conflicts in microservice deployment images [source: 9].

---

## 2. Public API Reference

| Symbol | Type | Safe for Async? | Description |
| --- | --- | --- | --- |
| `trace_span` | Decorator | Yes | Wraps sync/async functions in OpenTelemetry spans with duration tracking. [source: 9] |
| `get_tracer` | Function | Yes | Retrieves an OpenTelemetry `Tracer` instance from the global provider. [source: 9] |
| `StructuredJsonFormatter` | Class | Yes | Formats `LogRecord` objects into structured JSON with OpenTelemetry trace context. [source: 9] |
| `DateSeqRotatingFileHandler` | Class | Thread-Safe | Subclass of `BaseRotatingHandler` supporting cascade sequence versioning (`_v1.log`). [source: 9] |
| `SpanExtractionError` | Exception | N/A | Raised on attribute extraction failures; includes `.to_dict()` for agent triage. [source: 9] |
| `LoggingFormattingError` | Exception | N/A | Raised when JSON formatting fails. [source: 9] |
| `TelemetryError` | Exception | N/A | Base exception class for the domain. [source: 9] |

### Signatures & Detailed Specifications

#### `get_tracer(name: str = "meta_telemetry") -> Tracer`

Retrieves an OpenTelemetry `Tracer` from the registered global `TracerProvider` [source: 9].

#### `trace_span(name: str | None = None, extract_attributes: Callable[[dict[str, Any]], dict[str, Any]] | None = None, tracer_name: str = "meta_telemetry") -> Callable[[F], F]`

Parametrized decorator for synchronous and asynchronous callables [source: 9].

* Automatically calculates `execution.duration_ms` [source: 9].
* Sets span status to `StatusCode.OK` on success or `StatusCode.ERROR` on unhandled exceptions [source: 9].
* Accepts an optional `extract_attributes` callback receiving a dictionary of bound parameters [source: 9].

#### `StructuredJsonFormatter(service_name: str = "meta_service", environment: str = "production", fmt: str | None = None, datefmt: str | None = None)`

Formats Python `logging.LogRecord` instances into standardized JSON strings [source: 9].

* Injects `trace_id`, `span_id`, and `trace_flags` when executed within an active OpenTelemetry context [source: 9].
* Captures top-level `extra` dict attributes passed to logging functions [source: 9].

#### `DateSeqRotatingFileHandler(base_dir: str | Path, app_name: str = "meta_app", max_bytes: int = 10485760, backup_count: int = 5, encoding: str = "utf-8", delay: bool = False, date_format: str = "%d%m%y_%H%M%S", use_utc: bool = True)`

Specialized file rotation handler extending `logging.handlers.BaseRotatingHandler` [source: 9].

* Rotates active logs based on date boundary transitions or exceeding `max_bytes` [source: 9].
* Cascades full log files through a downward versioning sequence (`_v1.log`, `_v2.log`) [source: 9].

#### `TelemetryError(message: str)`

Base domain exception for all errors raised within `meta-telemetry` [source: 9].

#### `SpanExtractionError(message: str, function_name: str | None = None, original_exception: Exception | None = None)`

Raised when `extract_attributes` encounters an error during argument binding or evaluation [source: 9].

* **Attributes:**
* `function_name`: Name of the targeted function [source: 9].
* `original_exception`: The underlying caught exception object [source: 9].


* **Methods:**
* `to_dict() -> dict[str, Any]`: Returns structured error context formatted as:
```python
{
    "error_type": "SpanExtractionError",
    "message": "...",
    "function_name": "target_func",
    "original_exception": "ValueError(...)"
}


```

#### `LoggingFormattingError(message: str, log_record_name: str, original_exception: Exception | None = None)`

Raised when `StructuredJsonFormatter` fails to serialize a `LogRecord` [source: 9].

* **Attributes:**
* `log_record_name`: Name of the log record logger [source: 9].
* `original_exception`: The underlying caught exception object [source: 9].

---

## 3. Canonical Integration Patterns

### Pattern A: Structured JSON Logging & Date-Seq File Rotation

The following complete module configures a standard Python logger with `StructuredJsonFormatter` and `DateSeqRotatingFileHandler` [source: 9].

```python
import logging
from pathlib import Path
from typing import Any
from meta_telemetry import StructuredJsonFormatter
from meta_telemetry.logging import DateSeqRotatingFileHandler


def configure_application_logging(
    log_directory: str | Path,
    service_name: str = "meta_service",
    environment: str = "production",
) -> logging.Logger:
    logger = logging.getLogger("meta_application")
    logger.setLevel(logging.INFO)

    file_handler = DateSeqRotatingFileHandler(
        base_dir=log_directory,
        app_name="meta_app",
        max_bytes=10 * 1024 * 1024,  # 10 MB
        backup_count=5,
        encoding="utf-8",
        date_format="%d%m%y_%H%M%S",
        use_utc=True,
    )

    json_formatter = StructuredJsonFormatter(
        service_name=service_name,
        environment=environment,
    )

    file_handler.setFormatter(json_formatter)
    logger.addHandler(file_handler)
    return logger


if __name__ == "__main__":
    app_logger = configure_application_logging("./logs")
    app_logger.info(
        "Application subsystem started",
        extra={"component": "ingestion_worker", "replica_id": 4},
    )


```

#### Log Cascade Mechanics

When rotation triggers via size (`max_bytes`) or date boundary change, `DateSeqRotatingFileHandler` performs the following sequence [source: 9]:

1. **Active Log Staging:** Closes current stream and renames active log file `meta_app_DDMMYY_HHMMSS.log` to temporary file `meta_app_DDMMYY_HHMMSS_tmp.log` [source: 9].
2. **Downward Cascade Shift:** Existing versioned archives are renamed incrementally from highest index down to lowest (`_vN.log` $\rightarrow$ `_v{N+1}.log`) [source: 9]. If `backup_count > 0` and index exceeds limit, older files are deleted (`unlink()`) [source: 9].
3. **Promotion:** Renames `meta_app_DDMMYY_HHMMSS_tmp.log` to `meta_app_DDMMYY_HHMMSS_v1.log` (representing the immediate previous state) [source: 9].
4. **Re-Initialization:** Re-opens a clean active log file `meta_app_DDMMYY_HHMMSS.log` [source: 9].

---

### Pattern B: Tracing Synchronous & Asynchronous Functions

```python
import asyncio
from typing import Any
from meta_telemetry import trace_span


def extract_user_context(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "user.id": params.get("user_id"),
        "user.role": params.get("role", "guest"),
    }


@trace_span(
    name="ExecuteSyncWork",
    extract_attributes=extract_user_context,
)
def execute_sync_work(user_id: str, role: str = "admin") -> dict[str, Any]:
    return {"status": "completed", "owner": user_id, "role": role}


@trace_span(
    name="ExecuteAsyncWork",
    extract_attributes=lambda params: {"item.id": params.get("item_id")},
)
async def execute_async_work(item_id: str) -> dict[str, Any]:
    await asyncio.sleep(0.05)
    return {"status": "processed", "item_id": item_id}


if __name__ == "__main__":
    sync_result = execute_sync_work(user_id="usr_9981", role="operator")
    async_result = asyncio.run(execute_async_work(item_id="item_404"))


```

* Execution automatically attaches span duration via `execution.duration_ms` [source: 9].
* Successful invocations complete with `Status(StatusCode.OK)` [source: 9]. Unhandled exceptions set `Status(StatusCode.ERROR)` and record the exception stack trace before propagating [source: 9].

---

## 4. Edge Cases, Failure Safeguards & Anti-Patterns

### Attribute Extractor Failures

If `extract_attributes` raises an exception during function parameter binding or parsing, `@trace_span` catches the failure, wraps it inside `SpanExtractionError`, and records it on the span via `span.record_exception(extraction_err)` [source: 9]. **The underlying function execution is guaranteed to continue without crashing due to telemetry collection failures.**

### Non-Serializable Objects in Logging

`StructuredJsonFormatter` routes unknown objects through an internal `_default_json_serializer` [source: 9]:

* `datetime.date` and `datetime.datetime` objects are converted to ISO-8601 strings [source: 9].
* `Exception` objects are serialized into structured objects: `{"type": "ExceptionName", "message": "..."}` [source: 9].
* Arbitrary complex objects fall back to `str(obj)` [source: 9].
* If `str(obj)` fails, the value is safely serialized as the literal string `"<unserializable_object>"` [source: 9].

### JSON Encoding Fallback

If top-level JSON encoding fails entirely during `json.dumps()`, `StructuredJsonFormatter` catches the exception and outputs a standardized error fallback payload [source: 9]. This guarantees log messages are never lost due to encoding errors [source: 9]:

```json
{
  "timestamp": "2026-09-03T12:00:00.000000+00:00",
  "level": "ERROR",
  "logger": "meta_telemetry.logging",
  "message": "Failed to format log record: <error_details>",
  "original_message": "<original_log_message>"
}


```

> **WARNING:** `DateSeqRotatingFileHandler` relies on file system renames for file cascade management [source: 9]. Using this handler across multiple concurrent OS processes accessing the same log directory without external file locking can cause file-rename contention. Use process-isolated log directories or single-process logging workers in concurrent process architectures.

### Explicit Anti-Patterns

```python
# ANTI-PATTERN 1: Instantiating TracerProvider inside telemetry consumer modules
from opentelemetry.sdk.trace import TracerProvider
from meta_telemetry import trace_span

# DO NOT DO THIS inside library code or domain logic modules:
# provider = TracerProvider()
# trace.set_tracer_provider(provider)


```

* **Correct Practice:** Global provider registration belongs strictly in application entrypoints or test execution fixtures [source: 9].

```python
# ANTI-PATTERN 2: Mismatched extract_attributes callable signatures
@trace_span(
    name="InvalidBinding",
    # DO NOT DO THIS: Assuming parameter key exists without handling signature binding exceptions
    extract_attributes=lambda params: {"key": params["non_existent_arg"]}
)
def compute_data(actual_arg: str) -> None:
    pass


```

* **Correct Practice:** Access arguments matching the targeted function signature or use `.get()` safely on the `params` parameter dictionary [source: 9].

```

```