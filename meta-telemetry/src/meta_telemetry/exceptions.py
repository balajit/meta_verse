"""Domain exception hierarchy for meta_telemetry."""

from typing import Any, Optional


class TelemetryError(Exception):
    """Base exception for all meta_telemetry domain errors."""

    def to_dict(self) -> dict[str, Any]:
        """Returns structured metadata for agentic error triage."""
        return {
            "error_type": self.__class__.__name__,
            "message": str(self),
        }


class SpanExtractionError(TelemetryError):
    """Raised when attribute extraction for an OpenTelemetry span fails."""

    def __init__(
        self,
        message: str,
        function_name: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.function_name = function_name
        self.original_exception = original_exception

    def to_dict(self) -> dict[str, Any]:
        """Returns structured metadata for agentic error triage."""
        base_dict = super().to_dict()
        base_dict.update({
            "function_name": self.function_name,
            "original_exception": str(self.original_exception) if self.original_exception else None,
        })
        return base_dict


class LoggingFormattingError(TelemetryError):
    """Raised when JSON formatting of a log record fails."""

    def __init__(
        self,
        message: str,
        log_record_name: str,
        original_exception: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.log_record_name = log_record_name
        self.original_exception = original_exception

    def to_dict(self) -> dict[str, Any]:
        """Returns structured metadata for agentic error triage."""
        base_dict = super().to_dict()
        base_dict.update({
            "log_record_name": self.log_record_name,
            "original_exception": str(self.original_exception) if self.original_exception else None,
        })
        return base_dict