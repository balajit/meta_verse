from __future__ import annotations

import unittest.mock as mock

import pytest
from pydantic import ValidationError

from meta_service_generator.diagnostics import DiagnosticEngine, DiagnosticReport
from meta_service_generator.exceptions import GeneratorError


class CustomGeneratorError(GeneratorError):
    def __init__(
            self,
            message: str,
            stage: str = "parsing",
            error_code: str = "ERR_PARSE_FAILED",
            location: str = "/entities/0",
            severity: str = "error",
            suggested_resolution: str = "Fix schema syntax.",
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.error_code = error_code
        self.location = location
        self.severity = severity
        self.suggested_resolution = suggested_resolution


class TestDiagnosticReportModel:
    def test_report_defaults_and_validation(self) -> None:
        report = DiagnosticReport(
            stage="codegen",
            error_code="ERR_001",
            message="Failed to generate code.",
            suggested_resolution="Check template.",
        )

        assert report.generation_status == "failed"
        assert report.severity == "fatal"
        assert report.location == "global"

    def test_report_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            DiagnosticReport(
                stage="codegen",
                error_code="ERR_001",
                message="Failed",
                suggested_resolution="Fix",
                extra_arg="invalid",  # type: ignore[call-arg]
            )


class TestDiagnosticEngine:
    def test_create_report_from_generator_error(self) -> None:
        engine = DiagnosticEngine(json_mode=False)
        exc = CustomGeneratorError(
            message="Invalid field format",
            severity="warning",
        )

        report = engine.create_report_from_exception(exc)

        assert report.generation_status == "failed"
        assert report.stage == "parsing"
        assert report.error_code == "ERR_PARSE_FAILED"
        assert report.severity == "warning"
        assert report.location == "/entities/0"
        assert report.suggested_resolution == "Fix schema syntax."

    def test_create_report_from_generator_error_invalid_severity_fallback(self) -> None:
        engine = DiagnosticEngine()
        exc = CustomGeneratorError(
            message="Bad severity test",
            severity="invalid_severity_type",
        )

        report = engine.create_report_from_exception(exc)
        assert report.severity == "fatal"

    def test_create_report_from_unhandled_system_exception(self) -> None:
        engine = DiagnosticEngine()
        sys_exc = RuntimeError("System memory exhausted")

        mock_span = mock.Mock()
        mock_span.is_recording.return_value = True

        with mock.patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            report = engine.create_report_from_exception(sys_exc)

        mock_span.record_exception.assert_called_once_with(sys_exc)
        assert report.error_code == "ERR_UNHANDLED_SYSTEM_EXCEPTION"
        assert report.stage == "system_execution"
        assert report.message == "System memory exhausted"

    def test_emit_json_mode(self) -> None:
        engine = DiagnosticEngine(json_mode=True)
        report = DiagnosticReport(
            stage="stage1",
            error_code="ERR_JSON_EMIT",
            message="Test emit",
            suggested_resolution="None",
        )

        with mock.patch.object(engine.console, "print_json") as mock_print_json:
            engine.emit(report)
            mock_print_json.assert_called_once()

    def test_emit_rich_panel_mode(self) -> None:
        engine = DiagnosticEngine(json_mode=False)

        fatal_report = DiagnosticReport(
            stage="stage1",
            error_code="ERR_FATAL",
            message="Fatal error",
            severity="fatal",
            suggested_resolution="None",
        )
        warning_report = DiagnosticReport(
            stage="stage1",
            error_code="ERR_WARN",
            message="Warning event",
            severity="warning",
            suggested_resolution="None",
        )

        with mock.patch.object(engine.console, "print") as mock_print:
            engine.emit(fatal_report)
            engine.emit(warning_report)
            assert mock_print.call_count == 2