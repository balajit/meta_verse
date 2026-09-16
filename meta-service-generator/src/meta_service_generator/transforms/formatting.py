### file name: src/meta_service_generator/transforms/formatting.py

from __future__ import annotations

import ast

import black
from black.mode import TargetVersion
from black.parsing import InvalidInput

from meta_service_generator.exceptions import CodeGenerationError
from meta_telemetry import get_tracer, trace_span


tracer = get_tracer("meta_service_generator.transforms.formatting")


class CodeFormattingGate:
    """
    In-process formatting gate enforcing Black/Ruff code styling and AST validity.
    """

    def __init__(
        self,
        line_length: int = 88,
    ) -> None:
        if not 40 <= line_length <= 200:
            raise ValueError(
                "line_length must be between 40 and 200."
            )

        self.mode = black.Mode(
            target_versions={
                TargetVersion.PY313,
            },
            line_length=line_length,
            is_pyi=False,
        )

    @trace_span("transforms.formatting.format_code")
    def format_code(
        self,
        source_code: str,
        filename: str = "<generated>",
    ) -> str:
        """
        Formats Python source code using Black in-process and validates syntax.
        """
        if not isinstance(source_code, str):
            raise CodeGenerationError(
                message=(
                    f"Source code must be str, got "
                    f"{type(source_code).__name__}."
                ),
                location=filename,
                error_code="ERR_FORMATTING_SOURCE_TYPE",
                suggested_resolution=(
                    "Pass generated Python source as a string."
                ),
            )

        try:
            ast.parse(
                source_code,
                filename=filename,
            )
        except SyntaxError as err:
            raise CodeGenerationError(
                message=(
                    f"Formatting gate rejected invalid Python syntax "
                    f"in '{filename}': {err.msg}"
                ),
                location=(
                    f"{filename}:{err.lineno or 0}:{err.offset or 0}"
                ),
                error_code="ERR_FORMATTING_GATE_INVALID_SYNTAX",
                suggested_resolution=(
                    "Inspect generated Python code for syntax errors."
                ),
            ) from err

        try:
            formatted_code = black.format_str(
                source_code,
                mode=self.mode,
            )

            ast.parse(
                formatted_code,
                filename=filename,
            )

            return formatted_code

        except InvalidInput as err:
            raise CodeGenerationError(
                message=(
                    f"Black rejected generated Python in '{filename}': {err}"
                ),
                location=filename,
                error_code="ERR_FORMATTING_BLACK_REJECTED",
                suggested_resolution=(
                    "Inspect generated Python syntax before formatting."
                ),
            ) from err

        except SyntaxError as err:
            raise CodeGenerationError(
                message=(
                    f"Black produced syntactically invalid output for "
                    f"'{filename}': {err.msg}"
                ),
                location=(
                    f"{filename}:{err.lineno or 0}:{err.offset or 0}"
                ),
                error_code="ERR_FORMATTING_OUTPUT_INVALID",
                suggested_resolution=(
                    "Inspect formatter compatibility and generated source."
                ),
            ) from err

        except Exception as err:
            raise CodeGenerationError(
                message=(
                    f"Failed to format generated file '{filename}': {err}"
                ),
                location=filename,
                error_code="ERR_FORMATTING_GATE_FAILED",
                suggested_resolution=(
                    "Ensure input code is valid Python source."
                ),
            ) from err