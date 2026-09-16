from types import MappingProxyType
import pytest

from meta_service_generator.exceptions import (
    CodeGenerationError,
    GeneratorError,
    IRBuilderError,
    ManifestValidationError,
    VerificationError,
)


def test_generator_error_initialization_and_dict_conversion():
    err = GeneratorError(
        message="Core failure",
        stage="custom_stage",
        error_code="ERR_CUSTOM",
        location="entities/User",
        severity="warning",
        suggested_resolution="Fix user entity",
        details={"key": "value"},
    )

    assert err.message == "Core failure"
    assert err.stage == "custom_stage"
    assert err.error_code == "ERR_CUSTOM"
    assert err.location == "entities/User"
    assert err.severity == "warning"
    assert isinstance(err.details, MappingProxyType)
    assert err.details["key"] == "value"

    diag = err.to_diagnostic_dict()
    assert diag == {
        "generation_status": "failed",
        "stage": "custom_stage",
        "error_code": "ERR_CUSTOM",
        "message": "Core failure",
        "location": "entities/User",
        "severity": "warning",
        "suggested_resolution": "Fix user entity",
    }


@pytest.mark.parametrize(
    "msg, stage, code, severity, expected_err",
    [
        ("", "stage_1", "ERR_1", "fatal", "message must not be empty"),
        ("Msg", "", "ERR_1", "fatal", "stage must not be empty"),
        ("Msg", "stage_1", "   ", "fatal", "error_code must not be empty"),
        ("Msg", "stage_1", "ERR_1", "invalid_severity", "severity must be one of"),
    ],
)
def test_generator_error_validation_guards(msg, stage, code, severity, expected_err):
    with pytest.raises(ValueError, match=expected_err):
        GeneratorError(
            message=msg,
            stage=stage,
            error_code=code,
            severity=severity,
        )


@pytest.mark.parametrize(
    "exception_cls, expected_stage, expected_code, expected_severity",
    [
        (ManifestValidationError, "stage_1_manifest_validation", "ERR_STAGE1_MANIFEST_INVALID", "fatal"),
        (IRBuilderError, "stage_2_ir_translation", "ERR_STAGE2_IR_TRANSLATION", "fatal"),
        (CodeGenerationError, "stage_3_4_code_generation", "ERR_STAGE3_4_CODE_GEN", "error"),
        (VerificationError, "stage_6_readiness_verification", "ERR_STAGE6_VERIFICATION_FAILED", "fatal"),
    ],
)
def test_derived_exceptions_hierarchy(exception_cls, expected_stage, expected_code, expected_severity):
    exc = exception_cls(message="Pipeline error")
    assert isinstance(exc, GeneratorError)
    assert exc.stage == expected_stage
    assert exc.error_code == expected_code
    assert exc.severity == expected_severity
    assert exc.suggested_resolution is not None