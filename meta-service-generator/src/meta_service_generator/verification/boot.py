from __future__ import annotations

import asyncio
import os
from pathlib import Path

from meta_service_generator.exceptions import CodeGenerationError
from meta_telemetry import get_tracer, trace_span
from pydantic import BaseModel, ConfigDict, Field
from meta_service_generator.local_telemetry import get_logger

logger = get_logger("meta_service_generator.verification.boot")

tracer = get_tracer("meta_service_generator.verification.boot")

DEFAULT_BOOT_TIMEOUT_SECONDS = 30.0
_MAX_OUTPUT_BYTES = 2 * 1024 * 1024


class BootVerificationResult(BaseModel):
    """Immutable result status for application startup dynamic verification [source: 3]."""

    success: bool = Field(
        ...,
        description="True when application import and lifespan startup completed successfully.",
    )
    output: str = Field(
        default="",
        description="Captured standard output from the boot subprocess.",
    )
    error_output: str | None = Field(
        default=None,
        description="Captured standard error or verification failure details.",
    )
    exit_code: int|None = Field(
        default=0,
        description="Subprocess exit code. -1 indicates the process could not complete normally.",
    )
    timed_out: bool = Field(
        default=False,
        description="True when the subprocess exceeded the configured timeout.",
    )

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )


class BootVerifier:
    """Verifies dynamic FastAPI application boot inside an isolated subprocess context [source: 3]."""

    def __init__(
        self,
        timeout_seconds: float = DEFAULT_BOOT_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")

        self._timeout_seconds = timeout_seconds

    @trace_span("verification.boot.verify_application_boot")
    async def verify_application_boot(
        self,
        project_root: Path,
        package_name: str,
    ) -> BootVerificationResult:
        """Executes app instantiation and lifespan verification in isolated subprocess [source: 3]."""
        self._validate_project_root(project_root)
        self._validate_package_name(package_name)

        boot_script = (
            "import asyncio\n"
            f"from {package_name}.main import app\n"
            "\n"
            "async def test_boot():\n"
            "    print('BOOT_INITIALIZING', flush=True)\n"
            "    async with app.router.lifespan_context(app):\n"
            "        print('BOOT_SUCCESSFUL', flush=True)\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    asyncio.run(test_boot())\n"
        )

        command = [
            "uv",
            "run",
            "python",
            "-c",
            boot_script,
        ]

        logger.info(
            "Starting application boot verification.",
            extra={
                "project_root": str(project_root),
                "package_name": package_name,
                "timeout_seconds": self._timeout_seconds,
            },
        )

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

            successful = (
                process.returncode == 0
                and "BOOT_SUCCESSFUL" in stdout_str
            )

            if successful:
                logger.info(
                    "Application boot verification succeeded.",
                    extra={
                        "package_name": package_name,
                        "exit_code": process.returncode,
                    },
                )

                return BootVerificationResult(
                    success=True,
                    output=stdout_str,
                    error_output=stderr_str or None,
                    exit_code=process.returncode,
                )

            error_message = (
                stderr_str
                or stdout_str
                or "Application boot process exited without BOOT_SUCCESSFUL."
            )

            logger.error(
                "Application boot verification failed.",
                extra={
                    "package_name": package_name,
                    "exit_code": process.returncode,
                    "error_output": error_message,
                },
            )

            return BootVerificationResult(
                success=False,
                output=stdout_str,
                error_output=error_message,
                exit_code=process.returncode,
            )

        except asyncio.TimeoutError:
            await self._terminate_process(process)

            message = (
                "Application boot verification timed out after "
                f"{self._timeout_seconds:.1f} seconds."
            )

            logger.error(
                "Application boot verification timed out.",
                extra={
                    "package_name": package_name,
                    "timeout_seconds": self._timeout_seconds,
                },
            )

            return BootVerificationResult(
                success=False,
                output="",
                error_output=message,
                exit_code=-1,
                timed_out=True,
            )

        except FileNotFoundError as err:
            raise CodeGenerationError(
                message="Unable to execute 'uv' for application boot verification.",
                location=str(project_root),
                error_code="ERR_BOOT_VERIFICATION_TOOL_MISSING",
                suggested_resolution=(
                    "Install uv and ensure it is available on PATH before "
                    "running generated-project verification."
                ),
            ) from err

        except OSError as err:
            raise CodeGenerationError(
                message=(
                    "Operating-system error occurred while starting "
                    f"application boot verification: {err}"
                ),
                location=str(project_root),
                error_code="ERR_BOOT_VERIFICATION_PROCESS_ERROR",
                suggested_resolution=(
                    "Verify the generated project directory exists and "
                    "the verification process can execute subprocesses."
                ),
            ) from err

        except Exception as err:
            logger.exception(
                "Unexpected application boot verification failure.",
                extra={
                    "package_name": package_name,
                    "exception_type": type(err).__name__,
                },
            )

            raise CodeGenerationError(
                message=(
                    f"Unexpected application boot verification failure: {err}"
                ),
                location=package_name,
                error_code="ERR_BOOT_VERIFICATION_INTERNAL",
                suggested_resolution=(
                    "Inspect the generated application's import and lifespan "
                    "startup path."
                ),
            ) from err

    @staticmethod
    def _validate_project_root(project_root: Path) -> None:
        if not project_root.is_absolute():
            raise CodeGenerationError(
                message=f"Project root must be absolute: '{project_root}'.",
                location=str(project_root),
                error_code="ERR_BOOT_PROJECT_ROOT_INVALID",
                suggested_resolution=(
                    "Pass an absolute generated-project root path."
                ),
            )

        if not project_root.exists():
            raise CodeGenerationError(
                message=f"Generated project root does not exist: '{project_root}'.",
                location=str(project_root),
                error_code="ERR_BOOT_PROJECT_ROOT_MISSING",
                suggested_resolution=(
                    "Generate the project before executing boot verification."
                ),
            )

        if not project_root.is_dir():
            raise CodeGenerationError(
                message=f"Generated project root is not a directory: '{project_root}'.",
                location=str(project_root),
                error_code="ERR_BOOT_PROJECT_ROOT_NOT_DIRECTORY",
                suggested_resolution=(
                    "Pass the generated project's directory."
                ),
            )

    @staticmethod
    def _validate_package_name(package_name: str) -> None:
        if not package_name.strip():
            raise CodeGenerationError(
                message="Generated package name must not be empty.",
                location="package_name",
                error_code="ERR_BOOT_PACKAGE_NAME_EMPTY",
                suggested_resolution=(
                    "Provide the generated Python package name."
                ),
            )

        parts = package_name.split(".")

        if any(not part.isidentifier() for part in parts):
            raise CodeGenerationError(
                message=(
                    f"Invalid generated Python package name: '{package_name}'."
                ),
                location="package_name",
                error_code="ERR_BOOT_PACKAGE_NAME_INVALID",
                suggested_resolution=(
                    "Use a valid dotted Python module path."
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