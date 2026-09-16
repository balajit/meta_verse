from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

from meta_service_generator.exceptions import CodeGenerationError
from meta_telemetry import get_tracer, trace_span
from pydantic import BaseModel, ConfigDict, Field
from meta_service_generator.local_telemetry import get_logger

logger = get_logger("meta_service_generator.diagnostics")

tracer = get_tracer("meta_service_generator.verification.typing")

DEFAULT_TYPECHECK_TIMEOUT_SECONDS = 60.0
_MAX_OUTPUT_BYTES = 8 * 1024 * 1024


class TypeCheckIssue(BaseModel):
    """Detailed record of a single static type checking issue."""

    file_path: str = Field(
        ...,
        min_length=1,
        description="Path to file containing type error.",
    )
    line_number: int = Field(
        ...,
        ge=1,
        description="Line number of type error.",
    )
    error_code: str = Field(
        ...,
        min_length=1,
        description="Mypy error code key.",
    )
    message: str = Field(
        ...,
        min_length=1,
        description="Type error description.",
    )

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )


class TypeCheckResult(BaseModel):
    """Immutable result summary for static type checking."""

    is_valid: bool = Field(
        ...,
        description="True if mypy passed with zero type errors.",
    )
    issues: tuple[TypeCheckIssue, ...] = Field(
        default=(),
        description="Immutable collection of parsed mypy issues.",
    )
    raw_output: str = Field(
        default="",
        description="Raw output string from mypy execution.",
    )
    exit_code: int|None = Field(
        default=0,
        description="Mypy subprocess exit code.",
    )
    timed_out: bool = Field(
        default=False,
        description="True when mypy exceeded the configured timeout.",
    )

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )


class TypeVerifier:
    """Verifies static type compliance of synthesized codebase using mypy in isolated subprocesses."""

    MYPY_ERROR_PATTERN = re.compile(
        r"^(?P<file>[^:]+):"
        r"(?P<line>\d+):"
        r"\s+error:\s+"
        r"(?P<msg>.+?)"
        r"(?:\s+\[(?P<code>[^\]]+)\])?$"
    )

    def __init__(
        self,
        timeout_seconds: float = DEFAULT_TYPECHECK_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")

        self._timeout_seconds = timeout_seconds

    @trace_span("verification.typing.verify_types")
    async def verify_types(
        self,
        project_root: Path,
    ) -> TypeCheckResult:
        """Executes strict mypy type checking against the generated source directory."""
        self._validate_project_root(project_root)

        src_dir = project_root / "src"

        if not src_dir.exists():
            raise CodeGenerationError(
                message=f"Generated source directory does not exist: '{src_dir}'.",
                location=str(src_dir),
                error_code="ERR_TYPE_SOURCE_MISSING",
                suggested_resolution=(
                    "Generate source files before executing type verification."
                ),
            )

        if not src_dir.is_dir():
            raise CodeGenerationError(
                message=f"Generated source path is not a directory: '{src_dir}'.",
                location=str(src_dir),
                error_code="ERR_TYPE_SOURCE_INVALID",
                suggested_resolution=(
                    "Ensure generated source files are emitted under src/."
                ),
            )

        logger.info(
            "Executing strict mypy type checking.",
            extra={
                "source_directory": str(src_dir),
                "timeout_seconds": self._timeout_seconds,
            },
        )

        command = [
            "uv",
            "run",
            "mypy",
            "src/",
            "--strict",
            "--show-error-codes",
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
            combined_output = "\n".join(
                value
                for value in (stdout_str, stderr_str)
                if value
            )

            issues = self._parse_mypy_output(combined_output)
            is_valid = process.returncode == 0 and not issues

            if is_valid:
                logger.info(
                    "Static type verification passed.",
                    extra={
                        "exit_code": process.returncode,
                        "issue_count": 0,
                    },
                )
            else:
                logger.error(
                    "Static type verification failed.",
                    extra={
                        "exit_code": process.returncode,
                        "issue_count": len(issues),
                    },
                )

            return TypeCheckResult(
                is_valid=is_valid,
                issues=tuple(issues),
                raw_output=combined_output,
                exit_code=process.returncode,
            )

        except asyncio.TimeoutError:
            if process is not None:
                await self._terminate_process(process)

            message = (
                f"Mypy execution timed out after "
                f"{self._timeout_seconds:.1f} seconds."
            )

            logger.error(
                "Static type verification timed out.",
                extra={
                    "timeout_seconds": self._timeout_seconds,
                },
            )

            return TypeCheckResult(
                is_valid=False,
                issues=(),
                raw_output=message,
                exit_code=-1,
                timed_out=True,
            )

        except FileNotFoundError as err:
            raise CodeGenerationError(
                message="Unable to execute 'uv' for static type verification.",
                location="src/",
                error_code="ERR_TYPE_VERIFICATION_TOOL_MISSING",
                suggested_resolution=(
                    "Install uv and ensure it is available on PATH."
                ),
            ) from err

        except OSError as err:
            raise CodeGenerationError(
                message=(
                    f"Operating-system error during mypy execution: {err}"
                ),
                location="src/",
                error_code="ERR_TYPE_VERIFICATION_PROCESS_ERROR",
                suggested_resolution=(
                    "Verify subprocess execution permissions and generated-project access."
                ),
            ) from err

    def _parse_mypy_output(
        self,
        output: str,
    ) -> list[TypeCheckIssue]:
        issues: list[TypeCheckIssue] = []

        for line in output.splitlines():
            match = self.MYPY_ERROR_PATTERN.match(line.strip())

            if not match:
                continue

            error_code = match.group("code") or "unknown"

            issues.append(
                TypeCheckIssue(
                    file_path=match.group("file"),
                    line_number=int(match.group("line")),
                    message=match.group("msg"),
                    error_code=error_code,
                )
            )

        return issues

    @trace_span("verification.typing.enforce_type_safety")
    async def enforce_type_safety(
        self,
        project_root: Path,
    ) -> TypeCheckResult:
        """Evaluates static type safety and raises CodeGenerationError on failure."""
        result = await self.verify_types(project_root)

        if not result.is_valid:
            if result.issues:
                issue_summary = "; ".join(
                    (
                        f"[{issue.file_path}:{issue.line_number}] "
                        f"{issue.message} [{issue.error_code}]"
                    )
                    for issue in result.issues[:5]
                )
            else:
                issue_summary = result.raw_output or (
                    "Mypy failed without a parseable diagnostic."
                )

            raise CodeGenerationError(
                message=f"Static type check failed: {issue_summary}",
                location="src/",
                error_code="ERR_TYPE_CHECK_FAILED",
                suggested_resolution=(
                    "Inspect synthesized type hints and schema model "
                    "signatures for compatibility."
                ),
                details={
                    "exit_code": result.exit_code,
                    "issue_count": len(result.issues),
                    "timed_out": result.timed_out,
                },
            )

        return result

    @staticmethod
    def _validate_project_root(project_root: Path) -> None:
        if not project_root.is_absolute():
            raise CodeGenerationError(
                message=f"Project root must be absolute: '{project_root}'.",
                location=str(project_root),
                error_code="ERR_TYPE_PROJECT_ROOT_INVALID",
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
                error_code="ERR_TYPE_PROJECT_ROOT_MISSING",
                suggested_resolution=(
                    "Generate the project before executing type verification."
                ),
            )

    @staticmethod
    def _build_environment() -> dict[str, str]:
        environment = dict(os.environ)
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