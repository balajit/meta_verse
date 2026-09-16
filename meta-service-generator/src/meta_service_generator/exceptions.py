from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Literal

Severity = Literal["fatal", "error", "warning"]


def _freeze_detail_value(
    value: Any,
) -> Any:
    """
    Recursively freeze diagnostic metadata.

    Dictionaries become read-only mappings and collections become tuples.
    Scalar values are preserved.
    """
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _freeze_detail_value(item)
                for key, item in value.items()
            }
        )

    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_detail_value(item)
            for item in value
        )

    if isinstance(value, (set, frozenset)):
        return frozenset(
            _freeze_detail_value(item)
            for item in value
        )

    return value


class GeneratorError(Exception):
    """Root domain exception for all generator failures."""

    def __init__(
        self,
        message: str,
        stage: str = "pipeline_initialization",
        error_code: str = "ERR_GENERATOR_INTERNAL",
        location: str | None = None,
        severity: Severity = "fatal",
        suggested_resolution: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)

        self.message = message
        self.stage = stage
        self.error_code = error_code
        self.location = location
        self.severity = severity

        self.suggested_resolution = (
            suggested_resolution
            or "Review pipeline specification and target manifest files."
        )

        frozen_details = {
            str(key): _freeze_detail_value(value)
            for key, value in (details or {}).items()
        }

        self.details: Mapping[str, Any] = MappingProxyType(
            frozen_details
        )

    def to_diagnostic_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible diagnostic representation."""
        return {
            "generation_status": "failed",
            "stage": self.stage,
            "error_code": self.error_code,
            "message": self.message,
            "location": self.location or "global",
            "severity": self.severity,
            "suggested_resolution": self.suggested_resolution,
            "details": _thaw_detail_value(self.details),
        }


def _thaw_detail_value(value: Any) -> Any:
    """Convert immutable diagnostic containers into serializable values."""
    if isinstance(value, Mapping):
        return {
            str(key): _thaw_detail_value(item)
            for key, item in value.items()
        }

    if isinstance(value, tuple):
        return [
            _thaw_detail_value(item)
            for item in value
        ]

    if isinstance(value, frozenset):
        return [
            _thaw_detail_value(item)
            for item in value
        ]

    return value


class ConfigurationError(GeneratorError):
    """Generator startup/configuration failure."""

    def __init__(
        self,
        message: str,
        location: str | None = None,
        error_code: str = "ERR_CONFIGURATION_INVALID",
        suggested_resolution: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            stage="configuration_initialization",
            error_code=error_code,
            location=location,
            severity="fatal",
            suggested_resolution=(
                suggested_resolution
                or "Correct generator configuration before startup."
            ),
            details=details,
        )


class ManifestValidationError(GeneratorError):
    """Stage 1 manifest ingestion, schema, or reference-integrity failure."""

    def __init__(
        self,
        message: str,
        location: str | None = None,
        error_code: str = "ERR_STAGE1_MANIFEST_INVALID",
        suggested_resolution: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            stage="stage_1_manifest_validation",
            error_code=error_code,
            location=location,
            severity="fatal",
            suggested_resolution=(
                suggested_resolution
                or "Fix schema validation or referential integrity errors "
                "in manifest."
            ),
            details=details,
        )


class IRBuilderError(GeneratorError):
    """Stage 2 intermediate-representation translation failure."""

    def __init__(
        self,
        message: str,
        location: str | None = None,
        error_code: str = "ERR_STAGE2_IR_TRANSLATION",
        suggested_resolution: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            stage="stage_2_ir_translation",
            error_code=error_code,
            location=location,
            severity="fatal",
            suggested_resolution=(
                suggested_resolution
                or "Resolve invalid identifiers, references, or circular "
                "dependencies."
            ),
            details=details,
        )


class CodeGenerationError(GeneratorError):
    """Stage 3/4 synthesis, transformation, or formatting failure."""

    def __init__(
        self,
        message: str,
        location: str | None = None,
        error_code: str = "ERR_STAGE3_4_CODE_GEN",
        suggested_resolution: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            stage="stage_3_4_code_generation",
            error_code=error_code,
            location=location,
            severity="error",
            suggested_resolution=(
                suggested_resolution
                or "Verify Jinja2 rendering, LibCST transformations, "
                "and formatting."
            ),
            details=details,
        )


class VerificationError(GeneratorError):
    """Stage 6 generated-artifact verification failure."""

    def __init__(
        self,
        message: str,
        location: str | None = None,
        error_code: str = "ERR_STAGE6_VERIFICATION_FAILED",
        suggested_resolution: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            stage="stage_6_readiness_verification",
            error_code=error_code,
            location=location,
            severity="fatal",
            suggested_resolution=(
                suggested_resolution
                or "Inspect generated application boot logs or test "
                "suite failures."
            ),
            details=details,
        )