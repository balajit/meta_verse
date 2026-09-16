from __future__ import annotations

import asyncio
import os
from pathlib import Path

from meta_service_generator.exceptions import CodeGenerationError
from meta_service_generator.local_telemetry import get_logger
from meta_telemetry import get_tracer, trace_span
from pydantic import BaseModel, ConfigDict, Field

logger = get_logger("meta_service_generator.verification.package")
tracer = get_tracer("meta_service_generator.verification.package")

DEFAULT_PACKAGE_TIMEOUT_SECONDS = 45.0
_MAX_OUTPUT_BYTES = 4 * 1024 * 1024


class PackageVerificationResult(BaseModel):
    """Immutable result status for pyproject configuration and dependency tree validation."""

    is_valid: bool = Field(
        ...,
        description="True if pyproject.toml is valid and buildable.",
    )
    build_output: str = Field(
        default="",
        description="Standard output from build verification.",
    )
    error_output: str | None = Field(
        default=None,
        description="Standard error details if build failed.",
    )
    exit_code: int | None = Field(
        default=0,
        description="Package build subprocess exit code.",
    )
    timed_out: bool = Field(
        default=False,
        description="True when package build exceeded the configured timeout.",
    )

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )


class PackageVerifier:
    """Verifies pyproject.toml validity, dependency resolution, and package buildability."""

    def __init__(
        self,
        timeout_seconds: float = DEFAULT_PACKAGE_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")

        self._timeout_seconds = timeout_seconds

    @trace_span("verification.package.verify_package")
    async def verify_package(
        self,
        project_root: Path,
    ) -> PackageVerificationResult:
        """Executes pyproject validation, dependency sync, and package build verification using uv."""
        self._validate_project_root(project_root)

        pyproject_path = project_root / "pyproject.toml"

        if not pyproject_path.exists():
            raise CodeGenerationError(
                message=f"Missing pyproject.toml in generated project root: {project_root}",
                location=str(project_root),
                error_code="ERR_MISSING_PYPROJECT",
                suggested_resolution="Ensure pyproject.toml template is correctly rendered during file synthesis.",
            )

        if not pyproject_path.is_file():
            raise CodeGenerationError(
                message=f"pyproject.toml is not a regular file: {pyproject_path}",
                location=str(pyproject_path),
                error_code="ERR_INVALID_PYPROJECT",
                suggested_resolution="Ensure pyproject.toml is generated as a regular file.",
            )

        try:
            pyproject_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as err:
            raise CodeGenerationError(
                message=f"Unable to read generated pyproject.toml: {err}",
                location=str(pyproject_path),
                error_code="ERR_PYPROJECT_READ_FAILED",
                suggested_resolution="Regenerate pyproject.toml with valid UTF-8 content.",
            ) from err

        logger.info(
            "Syncing project dependencies and verifying package build.",
            extra={
                "project_root": str(project_root),
                "timeout_seconds": self._timeout_seconds,
            },
        )

        env = self._build_environment()

        # Step 1: Sync dependencies into the isolated project virtualenv
        sync_process = await asyncio.create_subprocess_exec(
            "uv",
            "sync",
            "--extra",
            "dev",
            cwd=project_root,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        sync_stdout, sync_stderr = await sync_process.communicate()

        if sync_process.returncode != 0:
            sync_err_str = self._decode_output(sync_stderr) or self._decode_output(sync_stdout)
            logger.error(
                "Dependency synchronization failed.",
                extra={"project_root": str(project_root), "exit_code": sync_process.returncode},
            )
            return PackageVerificationResult(
                is_valid=False,
                build_output=self._decode_output(sync_stdout),
                error_output=f"uv sync failed: {sync_err_str}",
                exit_code=sync_process.returncode,
            )

        # Step 2: Build package wheel/sdist
        process: asyncio.subprocess.Process | None = None

        try:
            process = await asyncio.create_subprocess_exec(
                "uv",
                "build",
                cwd=project_root,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self._timeout_seconds,
            )

            stdout_str = self._decode_output(stdout)
            stderr_str = self._decode_output(stderr)

            if process.returncode == 0:
                logger.info(
                    "Package build verification passed successfully.",
                    extra={
                        "project_root": str(project_root),
                        "exit_code": process.returncode,
                    },
                )

                return PackageVerificationResult(
                    is_valid=True,
                    build_output=stdout_str,
                    error_output=stderr_str or None,
                    exit_code=process.returncode,
                )

            logger.error(
                "Package build verification failed.",
                extra={
                    "project_root": str(project_root),
                    "exit_code": process.returncode,
                },
            )

            return PackageVerificationResult(
                is_valid=False,
                build_output=stdout_str,
                error_output=(
                    stderr_str
                    or stdout_str
                    or f"Package build exited with code {process.returncode}."
                ),
                exit_code=process.returncode,
            )

        except asyncio.TimeoutError:
            if process is not None:
                await self._terminate_process(process)

            message = f"Package build process timed out after {self._timeout_seconds:.1f} seconds."

            logger.error(
                "Package build verification timed out.",
                extra={
                    "project_root": str(project_root),
                    "timeout_seconds": self._timeout_seconds,
                },
            )

            return PackageVerificationResult(
                is_valid=False,
                build_output="",
                error_output=message,
                exit_code=-1,
                timed_out=True,
            )

        except FileNotFoundError as err:
            raise CodeGenerationError(
                message="Unable to execute 'uv' for package verification.",
                location=str(project_root),
                error_code="ERR_PACKAGE_VERIFICATION_TOOL_MISSING",
                suggested_resolution="Install uv and ensure it is available on PATH.",
            ) from err

        except OSError as err:
            raise CodeGenerationError(
                message=f"Operating-system error during package verification: {err}",
                location=str(project_root),
                error_code="ERR_PACKAGE_VERIFICATION_PROCESS_ERROR",
                suggested_resolution="Verify subprocess execution permissions and generated-project filesystem access.",
            ) from err

    @trace_span("verification.package.enforce_package_validity")
    async def enforce_package_validity(
        self,
        project_root: Path,
    ) -> PackageVerificationResult:
        """Evaluates package validity and raises CodeGenerationError on failure."""
        result = await self.verify_package(project_root)

        if not result.is_valid:
            raise CodeGenerationError(
                message=f"Package build verification failed: {result.error_output}",
                location="pyproject.toml",
                error_code="ERR_PACKAGE_BUILD_FAILED",
                suggested_resolution="Verify pyproject.toml dependency definitions, build configuration, and generated package metadata.",
                details={
                    "exit_code": result.exit_code,
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
                error_code="ERR_PACKAGE_PROJECT_ROOT_INVALID",
                suggested_resolution="Pass an absolute generated-project root path.",
            )

        if not project_root.exists() or not project_root.is_dir():
            raise CodeGenerationError(
                message=f"Generated project root is missing or invalid: '{project_root}'.",
                location=str(project_root),
                error_code="ERR_PACKAGE_PROJECT_ROOT_MISSING",
                suggested_resolution="Generate the project before package verification.",
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