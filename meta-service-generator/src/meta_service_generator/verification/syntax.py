from __future__ import annotations

import ast
from pathlib import Path

from meta_service_generator.exceptions import CodeGenerationError
from meta_telemetry import get_tracer, trace_span
from pydantic import BaseModel, ConfigDict, Field
from meta_service_generator.local_telemetry import get_logger

logger = get_logger("meta_service_generator.verification.syntax")
tracer = get_tracer("meta_service_generator.verification.syntax")


class SyntaxVerificationResult(BaseModel):
    """Immutable result status for AST syntax verification [source: 3]."""

    file_path: str = Field(
        ...,
        min_length=1,
        description="Path to the Python source file.",
    )
    is_valid: bool = Field(
        ...,
        description="True when Python AST parsing succeeds.",
    )
    error_message: str | None = Field(
        default=None,
        description="Syntax parser error message.",
    )
    line_number: int | None = Field(
        default=None,
        ge=1,
        description="One-based source line containing syntax failure.",
    )
    column_offset: int | None = Field(
        default=None,
        ge=0,
        description="Zero-based parser column offset.",
    )

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )


class SyntaxVerifier:
    """Verifies syntactical validity of generated Python modules using AST parsing [source: 3]."""

    @trace_span("verification.syntax.verify_file")
    def verify_file(
        self,
        file_path: Path,
    ) -> SyntaxVerificationResult:
        """Parses a single Python file into an AST to verify syntax [source: 3]."""
        if not file_path.exists():
            raise CodeGenerationError(
                message=f"Generated Python file does not exist: '{file_path}'.",
                location=str(file_path),
                error_code="ERR_SYNTAX_FILE_MISSING",
                suggested_resolution=(
                    "Ensure the generation pipeline emitted the expected Python file."
                ),
            )

        if not file_path.is_file():
            raise CodeGenerationError(
                message=f"Generated Python path is not a file: '{file_path}'.",
                location=str(file_path),
                error_code="ERR_SYNTAX_FILE_INVALID",
                suggested_resolution=(
                    "Ensure the generated Python source path points to a regular file."
                ),
            )

        try:
            source = file_path.read_text(encoding="utf-8")
            ast.parse(
                source,
                filename=str(file_path),
                mode="exec",
            )

            return SyntaxVerificationResult(
                file_path=str(file_path),
                is_valid=True,
            )

        except UnicodeDecodeError as err:
            logger.error(
                "Generated Python source is not valid UTF-8.",
                extra={
                    "file_path": str(file_path),
                },
            )

            return SyntaxVerificationResult(
                file_path=str(file_path),
                is_valid=False,
                error_message=(
                    f"Generated source is not valid UTF-8: {err}"
                ),
            )

        except OSError as err:
            raise CodeGenerationError(
                message=(
                    f"Unable to read generated Python file "
                    f"'{file_path}': {err}"
                ),
                location=str(file_path),
                error_code="ERR_SYNTAX_FILE_READ_FAILED",
                suggested_resolution=(
                    "Verify generated-file permissions and filesystem integrity."
                ),
            ) from err

        except SyntaxError as err:
            logger.error(
                "Generated Python syntax verification failed.",
                extra={
                    "file_path": str(file_path),
                    "line_number": err.lineno,
                    "column_offset": err.offset,
                    "error_message": err.msg,
                },
            )

            return SyntaxVerificationResult(
                file_path=str(file_path),
                is_valid=False,
                error_message=err.msg,
                line_number=err.lineno,
                column_offset=err.offset,
            )

    @trace_span("verification.syntax.verify_directory")
    def verify_directory(
        self,
        directory: Path,
    ) -> tuple[SyntaxVerificationResult, ...]:
        """Recursively parses all Python files within target directory [source: 3]."""
        if not directory.exists():
            raise CodeGenerationError(
                message=f"Generated source directory does not exist: '{directory}'.",
                location=str(directory),
                error_code="ERR_SYNTAX_DIRECTORY_MISSING",
                suggested_resolution=(
                    "Ensure source generation completed before syntax verification."
                ),
            )

        if not directory.is_dir():
            raise CodeGenerationError(
                message=f"Generated source path is not a directory: '{directory}'.",
                location=str(directory),
                error_code="ERR_SYNTAX_DIRECTORY_INVALID",
                suggested_resolution=(
                    "Pass the generated project's source directory."
                ),
            )

        python_files = sorted(
            path
            for path in directory.rglob("*.py")
            if not path.is_symlink()
        )

        if not python_files:
            raise CodeGenerationError(
                message=f"No Python files found under '{directory}'.",
                location=str(directory),
                error_code="ERR_SYNTAX_NO_PYTHON_FILES",
                suggested_resolution=(
                    "Ensure the generation pipeline emitted Python source files."
                ),
            )

        results: list[SyntaxVerificationResult] = []

        for file_path in python_files:
            result = self.verify_file(file_path)
            results.append(result)

            if not result.is_valid:
                raise CodeGenerationError(
                    message=(
                        f"Syntax error in generated file "
                        f"'{result.file_path}': "
                        f"{result.error_message}"
                    ),
                    location=(
                        f"{result.file_path}:"
                        f"{result.line_number or 0}:"
                        f"{result.column_offset or 0}"
                    ),
                    error_code="ERR_SYNTAX_VERIFICATION_FAILED",
                    suggested_resolution=(
                        "Inspect template output and LibCST transformations "
                        "for invalid Python syntax."
                    ),
                )

        logger.info(
            "Generated source syntax verification passed.",
            extra={
                "directory": str(directory),
                "python_file_count": len(results),
            },
        )

        return tuple(results)