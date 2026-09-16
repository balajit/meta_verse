from __future__ import annotations

import asyncio
import os
from pathlib import Path

from meta_service_generator.exceptions import CodeGenerationError
from meta_service_generator.local_telemetry import get_logger
from meta_telemetry import get_tracer, trace_span
from pydantic import BaseModel, ConfigDict, Field

logger = get_logger("meta_service_generator.verification.tests")
tracer = get_tracer("meta_service_generator.verification.tests")

DEFAULT_TEST_TIMEOUT_SECONDS = 90.0
_MAX_OUTPUT_BYTES = 8 * 1024 * 1024


class TestSuiteExecutionResult(BaseModel):
    """Immutable result summary for synthesized test suite execution."""

    passed: bool = Field(
        ...,
        description="True if all synthesized tests passed.",
    )
    exit_code: int | None = Field(
        ...,
        description="Pytest process exit code.",
    )
    stdout: str = Field(
        default="",
        description="Standard output from pytest execution.",
    )
    stderr: str = Field(
        default="",
        description="Standard error output from pytest execution.",
    )
    timed_out: bool = Field(
        default=False,
        description="True when pytest exceeded the configured timeout.",
    )

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )


class TestSuiteVerifier:
    """Executes synthesized pytest suite inside an isolated subprocess and reports results."""

    def __init__(
        self,
        timeout_seconds: float = DEFAULT_TEST_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")

        self._timeout_seconds = timeout_seconds

    @trace_span("verification.tests.run_test_suite")
    async def run_test_suite(
        self,
        project_root: Path,
    ) -> TestSuiteExecutionResult:
        """Runs pytest on generated tests/ directory in target project."""
        self._validate_project_root(project_root)

        tests_dir = project_root / "tests"

        if not tests_dir.exists():
            raise CodeGenerationError(
                message=(
                    "Missing tests directory in generated project root: "
                    f"{project_root}"
                ),
                location=str(project_root),
                error_code="ERR_MISSING_TESTS_DIR",
                suggested_resolution=(
                    "Ensure test suite templates are rendered during "
                    "the generation pipeline."
                ),
            )

        if not tests_dir.is_dir():
            raise CodeGenerationError(
                message=f"Generated tests path is not a directory: '{tests_dir}'.",
                location=str(tests_dir),
                error_code="ERR_INVALID_TESTS_DIR",
                suggested_resolution=(
                    "Ensure tests/ is emitted as a directory."
                ),
            )

        test_files = sorted(
            path
            for path in tests_dir.rglob("test_*.py")
            if not path.is_symlink()
        )

        if not test_files:
            raise CodeGenerationError(
                message=f"No generated pytest files found under '{tests_dir}'.",
                location=str(tests_dir),
                error_code="ERR_NO_GENERATED_TESTS",
                suggested_resolution=(
                    "Ensure the test generation phase emits at least one test_*.py file."
                ),
            )

        logger.info(
            "Executing synthesized pytest suite.",
            extra={
                "project_root": str(project_root),
                "test_file_count": len(test_files),
                "timeout_seconds": self._timeout_seconds,
            },
        )

        command = [
            "uv",
            "run",
            "pytest",
            str(tests_dir),
            "-v",
            "-o",
            "asyncio_mode=auto",
        ]

        process: asyncio.subprocess.Process | None = None

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=project_root,
                env=self._build_environment(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self._timeout_seconds,
            )

            stdout_str = self._decode_output(stdout)
            stderr_str = self._decode_output(stderr)
            passed = process.returncode == 0

            if passed:
                logger.info(
                    "Synthesized pytest suite executed successfully.",
                    extra={
                        "exit_code": process.returncode,
                        "test_file_count": len(test_files),
                    },
                )
            else:
                logger.error(
                    "Synthesized pytest suite failed.",
                    extra={
                        "exit_code": process.returncode,
                        "test_file_count": len(test_files),
                        "stdout": stdout_str,
                        "stderr": stderr_str,
                    },
                )

            return TestSuiteExecutionResult(
                passed=passed,
                exit_code=process.returncode,
                stdout=stdout_str,
                stderr=stderr_str,
            )

        except asyncio.TimeoutError:
            if process is not None:
                await self._terminate_process(process)

            message = (
                f"Pytest execution timed out after "
                f"{self._timeout_seconds:.1f} seconds."
            )

            logger.error(
                "Synthesized pytest suite timed out.",
                extra={
                    "project_root": str(project_root),
                    "timeout_seconds": self._timeout_seconds,
                },
            )

            return TestSuiteExecutionResult(
                passed=False,
                exit_code=-1,
                stdout="",
                stderr=message,
                timed_out=True,
            )

        except FileNotFoundError as err:
            raise CodeGenerationError(
                message="Unable to execute 'uv' for generated test verification.",
                location="tests/",
                error_code="ERR_TEST_VERIFICATION_TOOL_MISSING",
                suggested_resolution=(
                    "Install uv and ensure it is available on PATH."
                ),
            ) from err

        except OSError as err:
            raise CodeGenerationError(
                message=(
                    f"Operating-system error during pytest execution: {err}"
                ),
                location="tests/",
                error_code="ERR_TEST_VERIFICATION_PROCESS_ERROR",
                suggested_resolution=(
                    "Verify subprocess permissions and generated-project filesystem access."
                ),
            ) from err

        except Exception as err:
            logger.exception(
                "Unexpected generated test execution failure.",
                extra={
                    "project_root": str(project_root),
                    "exception_type": type(err).__name__,
                },
            )

            raise CodeGenerationError(
                message=f"Unexpected generated test execution failure: {err}",
                location="tests/",
                error_code="ERR_TEST_VERIFICATION_INTERNAL",
                suggested_resolution=(
                    "Inspect pytest execution and generated test configuration."
                ),
            ) from err

    @trace_span("verification.tests.enforce_test_suite_pass")
    async def enforce_test_suite_pass(
        self,
        project_root: Path,
    ) -> TestSuiteExecutionResult:
        """Evaluates test suite execution and raises CodeGenerationError on any test failures."""
        result = await self.run_test_suite(project_root)

        if not result.passed:
            if result.exit_code == 4:
                resolution = (
                    "Pytest collected 0 tests. Ensure generated test functions "
                    "in tests/ begin with 'test_' (e.g., 'async def test_*()')."
                )
                message = "Pytest found test files but collected zero test functions (exit code 4)."
            else:
                resolution = (
                    "Review pytest stdout/stderr diagnostics and correct "
                    "generated application behavior."
                )
                message = (
                    "Synthesized test suite execution failed with "
                    f"exit code {result.exit_code}."
                )

            raise CodeGenerationError(
                message=message,
                location="tests/",
                error_code="ERR_TEST_SUITE_EXECUTION_FAILED",
                suggested_resolution=resolution,
                details={
                    "exit_code": result.exit_code,
                    "timed_out": result.timed_out,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
            )

        return result

    @staticmethod
    def _validate_project_root(project_root: Path) -> None:
        if not project_root.is_absolute():
            raise CodeGenerationError(
                message=f"Project root must be absolute: '{project_root}'.",
                location=str(project_root),
                error_code="ERR_TEST_PROJECT_ROOT_INVALID",
                suggested_resolution=(
                    "Pass an absolute generated-project root path."
                ),
            )

        if not project_root.exists() or not project_root.is_dir():
            raise CodeGenerationError(
                message=(
                    f"Generated project root is missing or invalid: "
                    f"'{project_root}'."
                ),
                location=str(project_root),
                error_code="ERR_TEST_PROJECT_ROOT_MISSING",
                suggested_resolution=(
                    "Generate the project before executing test verification."
                ),
            )

    @staticmethod
    def _build_environment() -> dict[str, str]:
        environment = dict(os.environ)
        # Remove parent virtualenv to let 'uv' target the generated project's .venv
        environment.pop("VIRTUAL_ENV", None)
        environment.setdefault("PYTHONUNBUFFERED", "1")
        return environment

    @staticmethod
    def _decode_output(value: bytes) -> str:
        if len(value) > _MAX_OUTPUT_BYTES:
            value = value[:_MAX_OUTPUT_BYTES]

        return value.decode(
            encoding="utf-8",
            errors="replace",
        ).strip()

    @staticmethod
    async def _terminate_process(
        process: asyncio.subprocess.Process,
    ) -> None:
        if process.returncode is not None:
            return

        try:
            process.kill()
        except ProcessLookupError:
            return

        try:
            await asyncio.wait_for(
                process.communicate(),
                timeout=5.0,
            )
        except (asyncio.TimeoutError, OSError):
            pass