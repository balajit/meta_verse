from __future__ import annotations

import asyncio
import os
from pathlib import Path

from meta_service_generator.exceptions import CodeGenerationError
from meta_telemetry import get_tracer, trace_span
from pydantic import BaseModel, ConfigDict, Field

from meta_service_generator.local_telemetry import get_logger

logger = get_logger("meta_service_generator.verification.imports")

tracer = get_tracer("meta_service_generator.verification.imports")

DEFAULT_IMPORT_TIMEOUT_SECONDS = 15.0
_MAX_OUTPUT_BYTES = 2 * 1024 * 1024


class ImportVerificationResult(BaseModel):
    """Immutable result status for module import verification [source: 3]."""

    module_name: str = Field(
        ...,
        min_length=1,
        description="Python module being verified.",
    )
    is_importable: bool = Field(
        ...,
        description="True when the module imports successfully.",
    )
    error_output: str | None = Field(
        default=None,
        description="Captured import failure details.",
    )
    exit_code: int|None = Field(
        default=0,
        description="Subprocess exit code.",
    )
    timed_out: bool = Field(
        default=False,
        description="True when module import exceeded the configured timeout.",
    )

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )


class ImportVerifier:
    """Verifies dynamic import viability in isolated subprocesses using uv [source: 3]."""

    def __init__(
        self,
        timeout_seconds: float = DEFAULT_IMPORT_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")

        self._timeout_seconds = timeout_seconds

    @trace_span("verification.imports.verify_module_import")
    async def verify_module_import(
        self,
        project_root: Path,
        module_name: str,
    ) -> ImportVerificationResult:
        """Executes module import check inside isolated subprocess [source: 3]."""
        self._validate_project_root(project_root)
        self._validate_module_name(module_name)

        command = [
            "uv",
            "run",
            "python",
            "-c",
            f"import {module_name}",
        ]

        logger.info(
            "Starting module import verification.",
            extra={
                "module_name": module_name,
                "project_root": str(project_root),
                "timeout_seconds": self._timeout_seconds,
            },
        )

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

            if process.returncode == 0:
                logger.info(
                    "Module import verification succeeded.",
                    extra={
                        "module_name": module_name,
                        "exit_code": process.returncode,
                    },
                )

                return ImportVerificationResult(
                    module_name=module_name,
                    is_importable=True,
                    error_output=stderr_str or None,
                    exit_code=process.returncode,
                )

            error_message = (
                stderr_str
                or stdout_str
                or f"Module import exited with code {process.returncode}."
            )

            logger.error(
                "Module import verification failed.",
                extra={
                    "module_name": module_name,
                    "exit_code": process.returncode,
                },
            )

            return ImportVerificationResult(
                module_name=module_name,
                is_importable=False,
                error_output=error_message,
                exit_code=process.returncode,
            )

        except asyncio.TimeoutError:
            if process is not None:
                await self._terminate_process(process)

            message = (
                f"Import execution timed out after "
                f"{self._timeout_seconds:.1f} seconds."
            )

            logger.error(
                "Module import verification timed out.",
                extra={
                    "module_name": module_name,
                    "timeout_seconds": self._timeout_seconds,
                },
            )

            return ImportVerificationResult(
                module_name=module_name,
                is_importable=False,
                error_output=message,
                exit_code=-1,
                timed_out=True,
            )

        except FileNotFoundError as err:
            raise CodeGenerationError(
                message="Unable to execute 'uv' for module import verification.",
                location=module_name,
                error_code="ERR_IMPORT_VERIFICATION_TOOL_MISSING",
                suggested_resolution=(
                    "Install uv and ensure it is available on PATH."
                ),
            ) from err

        except OSError as err:
            raise CodeGenerationError(
                message=(
                    f"Operating-system error during import verification: {err}"
                ),
                location=module_name,
                error_code="ERR_IMPORT_VERIFICATION_PROCESS_ERROR",
                suggested_resolution=(
                    "Verify subprocess execution permissions and project path."
                ),
            ) from err

    @trace_span("verification.imports.verify_all_imports")
    async def verify_all_imports(
        self,
        project_root: Path,
        package_name: str,
    ) -> tuple[ImportVerificationResult, ...]:
        """Scans project package and verifies importability for all submodules [source: 3]."""
        self._validate_project_root(project_root)
        self._validate_module_name(package_name)

        src_dir = project_root / "src" / Path(*package_name.split("."))

        if not src_dir.exists():
            raise CodeGenerationError(
                message=(
                    f"Generated source package directory does not exist: "
                    f"'{src_dir}'."
                ),
                location=str(src_dir),
                error_code="ERR_IMPORT_SOURCE_PACKAGE_MISSING",
                suggested_resolution=(
                    "Ensure source package generation completed before "
                    "running import verification."
                ),
            )

        if not src_dir.is_dir():
            raise CodeGenerationError(
                message=(
                    f"Generated source package path is not a directory: "
                    f"'{src_dir}'."
                ),
                location=str(src_dir),
                error_code="ERR_IMPORT_SOURCE_PACKAGE_INVALID",
                suggested_resolution=(
                    "Ensure package_name points to the generated Python package."
                ),
            )

        python_files = sorted(
            path for path in src_dir.rglob("*.py")
            if not path.is_symlink()
        )

        if not python_files:
            raise CodeGenerationError(
                message=f"No Python modules found under '{src_dir}'.",
                location=str(src_dir),
                error_code="ERR_IMPORT_NO_MODULES",
                suggested_resolution=(
                    "Ensure the generation pipeline emitted Python source files."
                ),
            )

        results: list[ImportVerificationResult] = []

        for file_path in python_files:
            module_name = self._module_name_from_path(
                project_root=project_root,
                file_path=file_path,
            )

            result = await self.verify_module_import(
                project_root,
                module_name,
            )

            results.append(result)

            if not result.is_importable:
                raise CodeGenerationError(
                    message=(
                        f"Module import verification failed for "
                        f"'{module_name}': {result.error_output}"
                    ),
                    location=module_name,
                    error_code="ERR_IMPORT_VERIFICATION_FAILED",
                    suggested_resolution=(
                        "Fix generated imports or declare missing "
                        "third-party dependencies in pyproject.toml."
                    ),
                    details={
                        "exit_code": result.exit_code,
                        "timed_out": result.timed_out,
                    },
                )

        logger.info(
            "All generated module imports verified.",
            extra={
                "package_name": package_name,
                "module_count": len(results),
            },
        )

        return tuple(results)

    @staticmethod
    def _module_name_from_path(
        project_root: Path,
        file_path: Path,
    ) -> str:
        src_root = project_root / "src"

        try:
            relative = file_path.relative_to(src_root)
        except ValueError as err:
            raise CodeGenerationError(
                message=(
                    f"Generated Python file '{file_path}' is outside "
                    f"source root '{src_root}'."
                ),
                location=str(file_path),
                error_code="ERR_IMPORT_PATH_OUTSIDE_SOURCE",
                suggested_resolution=(
                    "Keep generated Python modules under the project's src directory."
                ),
            ) from err

        if relative.name == "__init__.py":
            relative = relative.parent
        else:
            relative = relative.with_suffix("")

        module_name = ".".join(relative.parts)

        if not module_name:
            raise CodeGenerationError(
                message=f"Unable to derive Python module name from '{file_path}'.",
                location=str(file_path),
                error_code="ERR_IMPORT_MODULE_NAME_FAILED",
                suggested_resolution=(
                    "Ensure the generated source tree contains a valid package."
                ),
            )

        return module_name

    @staticmethod
    def _validate_project_root(project_root: Path) -> None:
        if not project_root.is_absolute():
            raise CodeGenerationError(
                message=f"Project root must be absolute: '{project_root}'.",
                location=str(project_root),
                error_code="ERR_IMPORT_PROJECT_ROOT_INVALID",
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
                error_code="ERR_IMPORT_PROJECT_ROOT_MISSING",
                suggested_resolution=(
                    "Generate the project before running import verification."
                ),
            )

    @staticmethod
    def _validate_module_name(module_name: str) -> None:
        if not module_name.strip():
            raise CodeGenerationError(
                message="Module name must not be empty.",
                location="module_name",
                error_code="ERR_IMPORT_MODULE_NAME_EMPTY",
                suggested_resolution=(
                    "Provide a valid Python module name."
                ),
            )

        if any(
            not part.isidentifier()
            for part in module_name.split(".")
        ):
            raise CodeGenerationError(
                message=f"Invalid Python module name '{module_name}'.",
                location="module_name",
                error_code="ERR_IMPORT_MODULE_NAME_INVALID",
                suggested_resolution=(
                    "Use a valid dotted Python module identifier."
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