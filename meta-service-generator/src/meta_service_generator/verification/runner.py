from __future__ import annotations

from pathlib import Path

from meta_service_generator.exceptions import CodeGenerationError
from meta_service_generator.verification.boot import (
    BootVerificationResult,
    BootVerifier,
)
from meta_service_generator.verification.imports import (
    ImportVerificationResult,
    ImportVerifier,
)
from meta_service_generator.verification.package import (
    PackageVerificationResult,
    PackageVerifier,
)
from meta_service_generator.verification.syntax import (
    SyntaxVerificationResult,
    SyntaxVerifier,
)
from meta_service_generator.verification.tests import (
    TestSuiteExecutionResult,
    TestSuiteVerifier,
)
from meta_service_generator.verification.typing import (
    TypeCheckResult,
    TypeVerifier,
)
from meta_telemetry import get_tracer, trace_span
from pydantic import BaseModel, ConfigDict, Field
from meta_service_generator.local_telemetry import get_logger

logger = get_logger("meta_service_generator.verification.runner")

tracer = get_tracer("meta_service_generator.verification.runner")


class VerificationPipelineResult(BaseModel):
    """Immutable result summary for the complete Stage 6 verification pipeline [source: 3]."""

    syntax_passed: bool = Field(
        ...,
        description="True when all generated Python files pass AST validation.",
    )
    package_passed: bool = Field(
        ...,
        description="True when generated package build succeeds.",
    )
    imports_passed: bool = Field(
        ...,
        description="True when every generated Python module imports successfully.",
    )
    typing_passed: bool = Field(
        ...,
        description="True when strict mypy verification succeeds.",
    )
    boot_passed: bool = Field(
        ...,
        description="True when application import and FastAPI lifespan startup succeed.",
    )
    tests_passed: bool = Field(
        ...,
        description="True when the generated pytest suite succeeds.",
    )
    syntax_results: tuple[SyntaxVerificationResult, ...] = Field(
        default=(),
        description="Immutable syntax verification results.",
    )
    package_result: PackageVerificationResult | None = Field(
        default=None,
        description="Package build verification result.",
    )
    import_results: tuple[ImportVerificationResult, ...] = Field(
        default=(),
        description="Immutable module import verification results.",
    )
    type_result: TypeCheckResult | None = Field(
        default=None,
        description="Static type verification result.",
    )
    boot_result: BootVerificationResult | None = Field(
        default=None,
        description="Application boot verification result.",
    )
    test_result: TestSuiteExecutionResult | None = Field(
        default=None,
        description="Generated test suite execution result.",
    )
    details: str = Field(
        ...,
        min_length=1,
        description="Human-readable verification summary.",
    )

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )


class VerificationRunner:
    """Orchestrates sequential execution of all generated-project verification gates [source: 3]."""

    def __init__(
        self,
        syntax_verifier: SyntaxVerifier | None = None,
        package_verifier: PackageVerifier | None = None,
        import_verifier: ImportVerifier | None = None,
        type_verifier: TypeVerifier | None = None,
        boot_verifier: BootVerifier | None = None,
        test_verifier: TestSuiteVerifier | None = None,
    ) -> None:
        self.syntax_verifier = syntax_verifier or SyntaxVerifier()
        self.package_verifier = package_verifier or PackageVerifier()
        self.import_verifier = import_verifier or ImportVerifier()
        self.type_verifier = type_verifier or TypeVerifier()
        self.boot_verifier = boot_verifier or BootVerifier()
        self.test_verifier = test_verifier or TestSuiteVerifier()

    @trace_span("verification.runner.run_pipeline")
    async def run_pipeline(
        self,
        project_root: Path,
        package_name: str,
    ) -> VerificationPipelineResult:
        """Runs all verification stages against synthesized service directory [source: 3]."""
        self._validate_inputs(
            project_root=project_root,
            package_name=package_name,
        )

        logger.info(
            "Starting complete generated-service verification pipeline.",
            extra={
                "project_root": str(project_root),
                "package_name": package_name,
            },
        )

        # 1. Syntax Check
        logger.info(
            "Verification gate 1/6: syntax.",
            extra={"project_root": str(project_root)},
        )

        syntax_results = self.syntax_verifier.verify_directory(
            project_root / "src"
        )

        # 2. Package Check
        logger.info(
            "Verification gate 2/6: package.",
            extra={"project_root": str(project_root)},
        )

        package_result = await self.package_verifier.verify_package(
            project_root
        )

        if not package_result.is_valid:
            raise CodeGenerationError(
                message=(
                    "Package build verification failed: "
                    f"{package_result.error_output}"
                ),
                location="pyproject.toml",
                error_code="ERR_PACKAGE_BUILD_FAILED",
                suggested_resolution=(
                    "Verify pyproject.toml, generated package metadata, "
                    "dependencies, and build configuration."
                ),
                details={
                    "exit_code": package_result.exit_code,
                    "timed_out": package_result.timed_out,
                },
            )

        # 3. Import Check
        logger.info(
            "Verification gate 3/6: imports.",
            extra={"package_name": package_name},
        )

        import_results = await self.import_verifier.verify_all_imports(
            project_root,
            package_name,
        )

        # 4. Type Check
        logger.info(
            "Verification gate 4/6: typing.",
            extra={"project_root": str(project_root)},
        )

        type_result = await self.type_verifier.verify_types(
            project_root
        )

        if not type_result.is_valid:
            issue_summary = self._format_type_failure(type_result)

            raise CodeGenerationError(
                message=f"Static type check failed: {issue_summary}",
                location="src/",
                error_code="ERR_TYPE_CHECK_FAILED",
                suggested_resolution=(
                    "Inspect synthesized type hints and schema model "
                    "signatures for compatibility."
                ),
                details={
                    "exit_code": type_result.exit_code,
                    "issue_count": len(type_result.issues),
                    "timed_out": type_result.timed_out,
                },
            )

        # 5. Boot Verification
        logger.info(
            "Verification gate 5/6: application boot.",
            extra={"package_name": package_name},
        )

        boot_result = await self.boot_verifier.verify_application_boot(
            project_root,
            package_name,
        )

        if not boot_result.success:
            raise CodeGenerationError(
                message=(
                    "Application boot verification failed: "
                    f"{boot_result.error_output}"
                ),
                location=package_name,
                error_code="ERR_BOOT_VERIFICATION_FAILED",
                suggested_resolution=(
                    "Verify application imports, settings configuration, "
                    "dependency initialization, and FastAPI lifespan startup."
                ),
                details={
                    "exit_code": boot_result.exit_code,
                    "timed_out": boot_result.timed_out,
                },
            )

        # 6. Pytest Test Suite Verification
        logger.info(
            "Verification gate 6/6: generated tests.",
            extra={"project_root": str(project_root)},
        )

        test_result = await self.test_verifier.run_test_suite(
            project_root
        )

        if not test_result.passed:
            raise CodeGenerationError(
                message=(
                    "Synthesized pytest suite execution failed with "
                    f"exit code {test_result.exit_code}."
                ),
                location="tests/",
                error_code="ERR_TEST_SUITE_FAILED",
                suggested_resolution=(
                    "Review generated test stdout/stderr and correct "
                    "generated application behavior."
                ),
                details={
                    "exit_code": test_result.exit_code,
                    "timed_out": test_result.timed_out,
                },
            )

        result = VerificationPipelineResult(
            syntax_passed=True,
            package_passed=True,
            imports_passed=True,
            typing_passed=True,
            boot_passed=True,
            tests_passed=True,
            syntax_results=syntax_results,
            package_result=package_result,
            import_results=import_results,
            type_result=type_result,
            boot_result=boot_result,
            test_result=test_result,
            details=(
                "All verification gates passed with zero human modifications "
                "required."
            ),
        )

        logger.info(
            "Complete generated-service verification pipeline passed.",
            extra={
                "project_root": str(project_root),
                "package_name": package_name,
                "syntax_files": len(syntax_results),
                "imported_modules": len(import_results),
                "type_issues": len(type_result.issues),
            },
        )

        return result

    @staticmethod
    def _validate_inputs(
        project_root: Path,
        package_name: str,
    ) -> None:
        if not project_root.is_absolute():
            raise CodeGenerationError(
                message=f"Project root must be absolute: '{project_root}'.",
                location=str(project_root),
                error_code="ERR_VERIFICATION_PROJECT_ROOT_INVALID",
                suggested_resolution=(
                    "Pass an absolute generated-project root path."
                ),
            )

        if not project_root.exists():
            raise CodeGenerationError(
                message=f"Generated project root does not exist: '{project_root}'.",
                location=str(project_root),
                error_code="ERR_VERIFICATION_PROJECT_ROOT_MISSING",
                suggested_resolution=(
                    "Generate the project before executing verification."
                ),
            )

        if not project_root.is_dir():
            raise CodeGenerationError(
                message=f"Generated project root is not a directory: '{project_root}'.",
                location=str(project_root),
                error_code="ERR_VERIFICATION_PROJECT_ROOT_INVALID",
                suggested_resolution=(
                    "Pass the generated project's directory."
                ),
            )

        if not package_name.strip():
            raise CodeGenerationError(
                message="Generated package name must not be empty.",
                location="package_name",
                error_code="ERR_VERIFICATION_PACKAGE_NAME_EMPTY",
                suggested_resolution=(
                    "Provide the generated Python package name."
                ),
            )

        if any(
            not part.isidentifier()
            for part in package_name.split(".")
        ):
            raise CodeGenerationError(
                message=f"Invalid generated package name '{package_name}'.",
                location="package_name",
                error_code="ERR_VERIFICATION_PACKAGE_NAME_INVALID",
                suggested_resolution=(
                    "Use a valid dotted Python package identifier."
                ),
            )

    @staticmethod
    def _format_type_failure(
        result: TypeCheckResult,
    ) -> str:
        if result.issues:
            return "; ".join(
                (
                    f"[{issue.file_path}:{issue.line_number}] "
                    f"{issue.message} [{issue.error_code}]"
                )
                for issue in result.issues[:5]
            )

        return result.raw_output or (
            "Mypy failed without a parseable diagnostic."
        )