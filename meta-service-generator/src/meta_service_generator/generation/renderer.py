from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import jinja2
from jinja2 import StrictUndefined

from meta_service_generator.exceptions import CodeGenerationError
from meta_service_generator.ir.names import (
    to_pascal_case,
    to_screaming_snake_case,
    to_snake_case,
)
from meta_service_generator.local_telemetry import get_logger
from meta_telemetry import get_tracer, trace_span


logger = get_logger("meta_service_generator.generation.renderer")
tracer = get_tracer("meta_service_generator.generation.renderer")


TEMPLATE_MAP: dict[str, str] = {
    "database.py.jinja2": "database.py.jinja2",
    "workflows.py.jinja2": "execution/workflows.py.jinja2",
    "fsm.py.jinja2": "execution/fsm.py.jinja2",
    "rules.py.jinja2": "execution/rules.py.jinja2",
    "config.py.jinja2": "extensions/config.py.jinja2",
    "policy.py.jinja2": "extensions/policy.py.jinja2",
    "telemetry.py.jinja2": "extensions/telemetry.py.jinja2",
    "dtos.py.jinja2": "models/dtos.py.jinja2",
    "orm.py.jinja2": "models/orm.py.jinja2",
    "main.py.jinja2": "project/main.py.jinja2",
    "pyproject.toml.jinja2": "project/pyproject.toml.jinja2",
    "repository.py.jinja2": "repositories/repository.py.jinja2",
    "router.py.jinja2": "routers/router.py.jinja2",
    "domain_service.py.jinja2": "service/domain_service.py.jinja2",
    "conftest.py.jinja2": "tests/conftest.py.jinja2",
    "test_fsm.py.jinja2": "tests/test_fsm.py.jinja2",
    "test_routers.py.jinja2": "tests/test_routers.py.jinja2",
    "test_workflow.py.jinja2": "tests/test_workflow.py.jinja2",
    "test_workflows.py.jinja2": "tests/test_workflows.py.jinja2",
}

DEFAULT_MAX_TEMPLATE_OUTPUT_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_TOTAL_GENERATED_BYTES = 100 * 1024 * 1024
DEFAULT_MAX_ARTIFACT_COUNT = 2_000


class TemplateRenderer:
    """Strict Jinja2 renderer for generated project artifacts."""

    def __init__(
        self,
        template_dir: Path | str | None = None,
        *,
        max_template_output_bytes: int = DEFAULT_MAX_TEMPLATE_OUTPUT_BYTES,
    ) -> None:
        if max_template_output_bytes <= 0:
            raise ValueError(
                "max_template_output_bytes must be greater than zero."
            )

        loaders: list[jinja2.BaseLoader] = []

        if template_dir is not None:
            try:
                resolved = Path(template_dir).expanduser().resolve()
            except OSError as err:
                raise CodeGenerationError(
                    message=(
                        f"Failed to resolve template directory "
                        f"'{template_dir}': {err}"
                    ),
                    location=str(template_dir),
                    error_code="ERR_TEMPLATE_DIR_RESOLUTION_FAILED",
                    suggested_resolution=(
                        "Provide a readable template directory path."
                    ),
                ) from err

            if not resolved.is_dir():
                raise CodeGenerationError(
                    message=f"Template directory '{resolved}' is invalid.",
                    location=str(resolved),
                    error_code="ERR_TEMPLATE_DIR_NOT_FOUND",
                    suggested_resolution=(
                        "Provide an existing template directory."
                    ),
                )

            loaders.append(
                jinja2.FileSystemLoader(str(resolved))
            )

        try:
            loaders.append(
                jinja2.PackageLoader(
                    "meta_service_generator",
                    "templates",
                )
            )
        except Exception as err:
            raise CodeGenerationError(
                message=(
                    "Failed to initialize package template loader: "
                    f"{err}"
                ),
                location="meta_service_generator.templates",
                error_code="ERR_PACKAGE_TEMPLATE_LOADER_FAILED",
                suggested_resolution=(
                    "Verify package installation and template resources."
                ),
            ) from err

        self.env = jinja2.Environment(
            loader=(
                jinja2.ChoiceLoader(loaders)
                if len(loaders) > 1
                else loaders[0]
            ),
            undefined=StrictUndefined,
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

        self.max_template_output_bytes = max_template_output_bytes

        self.env.filters["pascal_case"] = to_pascal_case
        self.env.filters["snake_case"] = to_snake_case
        self.env.filters["to_snake_case"] = to_snake_case
        self.env.filters["screaming_snake_case"] = (
            to_screaming_snake_case
        )
        self.env.filters["python_literal"] = self._python_literal

        logger.info(
            "Template renderer initialized.",
            extra={
                "event_type": "template_renderer_initialized",
                "template_dir": (
                    str(template_dir)
                    if template_dir is not None
                    else None
                ),
                "max_template_output_bytes": (
                    max_template_output_bytes
                ),
            },
        )

    @staticmethod
    def _python_literal(value: Any) -> str:
        if isinstance(value, StrictUndefined):
            return "None"

        if isinstance(value, str):
            return json.dumps(
                value,
                ensure_ascii=False,
            )

        if value is True:
            return "True"

        if value is False:
            return "False"

        if value is None:
            return "None"

        if isinstance(value, int):
            return repr(value)

        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError(
                    "Non-finite floating-point values are not valid "
                    "Python literals."
                )

            return repr(value)

        raise TypeError(
            "Unsupported Python literal type: "
            f"{type(value).__name__}"
        )

    def resolve_template_name(self, template_name: str) -> str:
        if not isinstance(template_name, str) or not template_name.strip():
            raise CodeGenerationError(
                message="Template name cannot be empty.",
                location="templates",
                error_code="ERR_TEMPLATE_NAME_INVALID",
                suggested_resolution="Provide a valid template name.",
            )

        return TEMPLATE_MAP.get(
            template_name,
            template_name,
        )

    @trace_span("generation.renderer.render")
    def render(
        self,
        template_name: str,
        context: Mapping[str, Any],
    ) -> str:
        if not isinstance(context, Mapping):
            raise CodeGenerationError(
                message=(
                    "Template context must implement Mapping; "
                    f"received {type(context).__name__}."
                ),
                location=f"templates/{template_name}",
                error_code="ERR_TEMPLATE_CONTEXT_INVALID",
                suggested_resolution=(
                    "Pass an immutable or read-only mapping."
                ),
            )

        canonical_name = self.resolve_template_name(
            template_name
        )

        try:
            template = self.env.get_template(
                canonical_name
            )

        except jinja2.TemplateNotFound as err:
            raise CodeGenerationError(
                message=(
                    f"Template '{canonical_name}' was not found."
                ),
                location=f"templates/{canonical_name}",
                error_code="ERR_TEMPLATE_NOT_FOUND",
                suggested_resolution=(
                    "Ensure the template is packaged and registered."
                ),
            ) from err

        except jinja2.TemplateSyntaxError as err:
            raise CodeGenerationError(
                message=(
                    f"Template syntax error at line {err.lineno}: "
                    f"{err.message}"
                ),
                location=(
                    f"templates/{canonical_name}:{err.lineno}"
                ),
                error_code="ERR_TEMPLATE_SYNTAX_ERROR",
                suggested_resolution=(
                    "Fix the Jinja2 template syntax."
                ),
            ) from err

        try:
            rendered = template.render(
                **dict(context)
            )

        except jinja2.UndefinedError as err:
            raise CodeGenerationError(
                message=(
                    f"Undefined template variable: {err}"
                ),
                location=f"templates/{canonical_name}",
                error_code="ERR_TEMPLATE_UNDEFINED_VARIABLE",
                suggested_resolution=(
                    "Provide all variables required by the template."
                ),
            ) from err

        except (UnicodeError, TypeError, ValueError) as err:
            raise CodeGenerationError(
                message=f"Template rendering failed: {err}",
                location=f"templates/{canonical_name}",
                error_code="ERR_TEMPLATE_RENDER_FAILED",
                suggested_resolution=(
                    "Inspect template logic and rendering context."
                ),
            ) from err

        except Exception as err:
            raise CodeGenerationError(
                message=f"Template rendering failed: {err}",
                location=f"templates/{canonical_name}",
                error_code="ERR_TEMPLATE_RENDER_FAILED",
                suggested_resolution=(
                    "Inspect template logic and rendering context."
                ),
            ) from err

        try:
            rendered_size = len(
                rendered.encode("utf-8")
            )
        except UnicodeEncodeError as err:
            raise CodeGenerationError(
                message=(
                    f"Template '{canonical_name}' produced content "
                    f"that cannot be encoded as UTF-8: {err}"
                ),
                location=f"templates/{canonical_name}",
                error_code="ERR_TEMPLATE_ENCODING_FAILED",
                suggested_resolution=(
                    "Ensure template output contains valid Unicode text."
                ),
            ) from err

        if rendered_size > self.max_template_output_bytes:
            raise CodeGenerationError(
                message=(
                    f"Template '{canonical_name}' exceeded the maximum "
                    f"rendered output size of "
                    f"{self.max_template_output_bytes} bytes."
                ),
                location=f"templates/{canonical_name}",
                error_code="ERR_TEMPLATE_OUTPUT_TOO_LARGE",
                suggested_resolution=(
                    "Reduce generated template expansion or increase the "
                    "explicit generator resource limit."
                ),
            )

        if not rendered.strip():
            raise CodeGenerationError(
                message=(
                    f"Template '{canonical_name}' produced no output."
                ),
                location=f"templates/{canonical_name}",
                error_code="ERR_TEMPLATE_EMPTY_OUTPUT",
                suggested_resolution=(
                    "Ensure the template emits a valid artifact."
                ),
            )

        logger.info(
            "Template rendered successfully.",
            extra={
                "event_type": "template_rendered",
                "template": canonical_name,
                "output_bytes": rendered_size,
            },
        )

        return rendered