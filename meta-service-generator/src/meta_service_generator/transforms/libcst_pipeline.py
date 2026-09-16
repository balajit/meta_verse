from __future__ import annotations

import ast
from collections.abc import Sequence

import libcst as cst

from meta_service_generator.exceptions import CodeGenerationError
from meta_service_generator.local_telemetry import get_logger
from meta_service_generator.transforms.annotations import (
    FutureAnnotationsTransformer,
)
from meta_service_generator.transforms.cleanup import (
    DeadCodeCleanupTransformer,
)
from meta_service_generator.transforms.imports import (
    ImportOrganizerTransformer,
)
from meta_telemetry import get_tracer, trace_span


logger = get_logger(
    "meta_service_generator.transforms.libcst_pipeline"
)

tracer = get_tracer(
    "meta_service_generator.transforms.libcst_pipeline"
)


class LibCSTPipeline:
    """
    Executes AST/CST transformation passes sequentially on raw Python code strings.
    """

    def __init__(
        self,
        transformers: Sequence[type[cst.CSTTransformer]] | None = None,
    ) -> None:
        configured_transformers = (
            transformers
            if transformers is not None
            else (
                FutureAnnotationsTransformer,
                ImportOrganizerTransformer,
                DeadCodeCleanupTransformer,
            )
        )

        normalized = tuple(configured_transformers)

        for transformer_cls in normalized:
            if not isinstance(transformer_cls, type):
                raise ValueError(
                    "Every CST transformer must be a transformer class."
                )

            if not issubclass(
                transformer_cls,
                cst.CSTTransformer,
            ):
                raise ValueError(
                    f"Invalid CST transformer: "
                    f"{transformer_cls!r}."
                )

        self.transformers: tuple[
            type[cst.CSTTransformer], ...
        ] = normalized

    @trace_span("transforms.libcst_pipeline.transform")
    def transform(
        self,
        source_code: str,
        filename: str = "<generated>",
    ) -> str:
        """
        Parses source string into LibCST module, applies all transformation passes, and returns code.
        """
        if not isinstance(source_code, str):
            raise CodeGenerationError(
                message=(
                    f"Source code must be str, got "
                    f"{type(source_code).__name__}."
                ),
                location=filename,
                error_code="ERR_CST_SOURCE_TYPE",
                suggested_resolution=(
                    "Pass generated Python source as a string."
                ),
            )

        if not isinstance(filename, str) or not filename.strip():
            raise CodeGenerationError(
                message="CST filename cannot be empty.",
                location="filename",
                error_code="ERR_CST_FILENAME_INVALID",
                suggested_resolution=(
                    "Provide the generated artifact's relative filename."
                ),
            )

        if not source_code.strip():
            raise CodeGenerationError(
                message="CST transformation received empty source.",
                location=filename,
                error_code="ERR_CST_EMPTY_SOURCE",
                suggested_resolution=(
                    "Ensure the Jinja2 template emits Python source."
                ),
            )

        try:
            cst_tree = cst.parse_module(source_code)

        except cst.ParserSyntaxError as err:
            raise CodeGenerationError(
                message=(
                    f"LibCST syntax parsing failed for '{filename}': "
                    f"{err}"
                ),
                location=(
                    f"{filename}:{err.raw_line}:{err.raw_column}"
                ),
                error_code="ERR_CST_PARSING_FAILED",
                suggested_resolution=(
                    "Verify Jinja2 template output for invalid Python syntax."
                ),
            ) from err

        for transformer_cls in self.transformers:
            transformer_name = transformer_cls.__name__

            try:
                transformer = transformer_cls()
                cst_tree = cst_tree.visit(transformer)

                logger.debug(
                    "CST transformation completed.",
                    extra={
                        "event_type": "cst_transform_completed",
                        "filename": filename,
                        "transformer": transformer_name,
                    },
                )

            except Exception as err:
                if isinstance(err, CodeGenerationError):
                    raise

                raise CodeGenerationError(
                    message=(
                        f"CST transformer '{transformer_name}' failed "
                        f"for '{filename}': {err}"
                    ),
                    location=filename,
                    error_code="ERR_CST_TRANSFORM_FAILED",
                    suggested_resolution=(
                        "Inspect the named CST transformer and generated "
                        "Python source."
                    ),
                    details={
                        "transformer": transformer_name,
                    },
                ) from err

        try:
            transformed_code = cst_tree.code

            ast.parse(
                transformed_code,
                filename=filename,
            )

        except SyntaxError as err:
            raise CodeGenerationError(
                message=(
                    f"LibCST transformation produced invalid Python "
                    f"for '{filename}': {err.msg}"
                ),
                location=(
                    f"{filename}:{err.lineno or 0}:{err.offset or 0}"
                ),
                error_code="ERR_CST_OUTPUT_INVALID",
                suggested_resolution=(
                    "Inspect the registered LibCST transformations."
                ),
            ) from err

        except Exception as err:
            raise CodeGenerationError(
                message=(
                    f"Failed to validate transformed source "
                    f"for '{filename}': {err}"
                ),
                location=filename,
                error_code="ERR_CST_OUTPUT_VALIDATION_FAILED",
                suggested_resolution=(
                    "Inspect transformed Python output."
                ),
            ) from err

        logger.info(
            "CST transformation pipeline completed.",
            extra={
                "event_type": "cst_pipeline_completed",
                "file_path": filename,
                "transformer_count": len(self.transformers),
            },
        )

        return transformed_code