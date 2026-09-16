from __future__ import annotations

from typing import Any, Literal

from meta_service_generator.exceptions import GeneratorError, Severity
from meta_service_generator.local_telemetry import get_logger
from meta_telemetry import get_tracer, trace_span
from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console
from rich.panel import Panel

logger = get_logger("meta_service_generator.diagnostics")
tracer = get_tracer("meta_service_generator.diagnostics")


def _freeze_detail_value(
    value: Any,
) -> Any:
    """Recursively freeze diagnostic metadata."""
    if isinstance(value, dict):
        return {
            key: _freeze_detail_value(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return tuple(
            _freeze_detail_value(item)
            for item in value
        )

    if isinstance(value, set):
        return frozenset(
            _freeze_detail_value(item)
            for item in value
        )

    if isinstance(value, tuple):
        return tuple(
            _freeze_detail_value(item)
            for item in value
        )

    return value


class DiagnosticReport(BaseModel):
    """Immutable machine-readable generator diagnostic contract."""

    generation_status: Literal[
        "failed",
        "success",
        "in_progress",
    ] = Field(default="failed")

    stage: str = Field(min_length=1)
    error_code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    location: str = Field(default="global", min_length=1)
    severity: Severity = Field(default="fatal")
    suggested_resolution: str = Field(min_length=1)

    event_type: str = Field(
        default="generator.failure",
        min_length=1,
    )

    details: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )

    def model_post_init(
        self,
        __context: Any,
    ) -> None:
        """Freeze nested diagnostic metadata after Pydantic validation."""
        object.__setattr__(
            self,
            "details",
            _freeze_detail_value(dict(self.details)),
        )


class DiagnosticEngine:
    """Converts domain failures to deterministic console or JSON diagnostics."""

    def __init__(
        self,
        json_mode: bool = False,
        console: Console | None = None,
    ) -> None:
        self.json_mode = json_mode
        self.console = console or Console(stderr=True)

    @trace_span("diagnostics.process_error")
    def create_report_from_exception(
        self,
        exc: Exception,
    ) -> DiagnosticReport:
        if isinstance(exc, GeneratorError):
            report = DiagnosticReport(
                generation_status="failed",
                stage=exc.stage,
                error_code=exc.error_code,
                message=exc.message,
                location=exc.location or "global",
                severity=exc.severity,
                suggested_resolution=exc.suggested_resolution,
                event_type="generator.domain_failure",
                details=dict(exc.details),
            )
        else:
            report = DiagnosticReport(
                generation_status="failed",
                stage="system_execution",
                error_code="ERR_UNHANDLED_SYSTEM_EXCEPTION",
                message=(
                    str(exc)
                    or "An unhandled execution crash occurred."
                ),
                location="internal",
                severity="fatal",
                suggested_resolution=(
                    "Inspect Python stack trace and system runtime logs."
                ),
                event_type="generator.unhandled_exception",
                details={
                    "exception_type": type(exc).__name__,
                },
            )

        logger.error(
            "Generator diagnostic created.",
            extra={
                "event_type": report.event_type,
                "stage": report.stage,
                "error_code": report.error_code,
                "location": report.location,
                "severity": report.severity,
            },
        )

        return report

    @trace_span("diagnostics.emit")
    def emit(
        self,
        report: DiagnosticReport,
    ) -> None:
        if self.json_mode:
            self.console.print_json(
                report.model_dump_json(indent=2)
            )
            return

        status_color = (
            "red"
            if report.severity in ("fatal", "error")
            else "yellow"
        )

        content = (
            f"[bold {status_color}]Status:[/] "
            f"{report.generation_status.upper()}\n"
            f"[bold]Stage:[/] {report.stage}\n"
            f"[bold]Error Code:[/] {report.error_code}\n"
            f"[bold]Location:[/] {report.location}\n"
            f"[bold]Message:[/] {report.message}\n"
            f"[bold]Suggested Resolution:[/] "
            f"{report.suggested_resolution}"
        )

        self.console.print(
            Panel(
                content,
                title=(
                    f"[{status_color}]Generation Failure Report "
                    f"({report.error_code})[/]"
                ),
                border_style=status_color,
                expand=False,
            )
        )