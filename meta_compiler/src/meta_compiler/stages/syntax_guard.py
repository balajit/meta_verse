"""Syntax guard and structural validation stage for meta_compiler.

Parses raw YAML/JSON manifest definitions and executes strict JSON Schema
Draft 2020-12 validation using pre-compiled, cached schema validators with
full structured logging and agentic telemetry support.
"""

import hashlib
import json
import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from meta_compiler.config import CompilerSettings
from meta_compiler.core.action_registry import ActionRegistry
from meta_compiler.core.context import CompilationContext
from meta_compiler.exceptions import (
    ConfigurationError,
    ManifestSyntaxError,
    SchemaValidationError,
)
from meta_compiler.stages.base import BaseCompilerStage

logger = logging.getLogger("meta_compiler.stages.syntax")
# [Existing functions parse_and_validate_yaml, validate_manifest_syntax remain as defined]


class SyntaxGuardStage(BaseCompilerStage):
    """Stage 1 Adapter: Structural syntax and JSON Schema Draft 2020-12 validation."""

    def run(self, context: CompilationContext, registry: ActionRegistry) -> None:
        logger.debug(
            "Executing SyntaxGuardStage for context %s",
            context.context_id,
            extra={"event": "stage.syntax_guard.start", "context_id": str(context.context_id)},
        )
        if isinstance(context.raw_input, str):
            validated_dict = parse_and_validate_yaml(context.raw_input)
            context.raw_input = validated_dict
        elif isinstance(context.raw_input, dict):
            validate_manifest_syntax(context.raw_input)
        else:
            raise SchemaValidationError(
                f"Unsupported raw input format: {type(context.raw_input).__name__}"
            )


@lru_cache(maxsize=8)
def _get_compiled_validator(schema_path_str: str) -> tuple[jsonschema.Draft202012Validator, str]:
    """Loads JSON schema from disk, calculates SHA-256 digest, and caches the compiled validator."""
    path = Path(schema_path_str)
    logger.debug("Loading and compiling meta-schema validator from disk path: %s", path)

    if not path.is_file():
        logger.error("Meta-schema file not found at path: %s", path)
        raise ConfigurationError(
            f"Meta-schema file not found at location: '{path}'",
            details={"schema_path": str(path)},
        )

    try:
        raw_bytes = path.read_bytes()
        schema_digest = hashlib.sha256(raw_bytes).hexdigest()[:16]
        schema_data = json.loads(raw_bytes.decode("utf-8"))
    except json.JSONDecodeError as err:
        logger.error("Failed to parse JSON meta-schema at '%s': %s", path, err)
        raise ConfigurationError(
            f"Invalid JSON format in meta-schema file at '{path}': {err}",
            details={"schema_path": str(path), "line": err.lineno, "column": err.colno},
        ) from err
    except Exception as err:
        logger.error("Unexpected I/O error loading meta-schema at '%s': %s", path, err)
        raise ConfigurationError(
            f"Failed to read meta-schema file at '{path}': {err}",
            details={"schema_path": str(path)},
        ) from err

    try:
        jsonschema.Draft202012Validator.check_schema(schema_data)
        validator = jsonschema.Draft202012Validator(schema_data)
        logger.info(
            "Successfully compiled Draft202012Validator [digest=%s] for schema: %s",
            schema_digest,
            path,
        )
        return validator, schema_digest
    except jsonschema.exceptions.SchemaError as err:
        logger.error("Meta-schema at '%s' is not valid JSON Schema Draft 2020-12: %s", path, err)
        raise ConfigurationError(
            f"Configured meta-schema at '{path}' is not valid Draft 2020-12 JSON Schema: {err.message}",
            details={"schema_path": str(path), "schema_error": err.message},
        ) from err


def validate_manifest_syntax(
    raw_manifest: dict[str, Any],
    schema_path: Path | None = None,
    settings: CompilerSettings | None = None,
) -> dict[str, Any]:
    """Executes jsonschema structural validation against the static Draft 2020-12 schema."""
    start_time = time.perf_counter()

    if not isinstance(raw_manifest, dict):
        raise SchemaValidationError(
            f"Manifest payload must be a dict object, got {type(raw_manifest).__name__}",
            details={"received_type": type(raw_manifest).__name__},
        )

    active_settings = settings or CompilerSettings()
    target_schema_path = schema_path or active_settings.get_resolved_schema_path()
    resolved_path_str = str(target_schema_path.resolve())

    validator, schema_digest = _get_compiled_validator(resolved_path_str)
    errors = list(validator.iter_errors(raw_manifest))

    namespace = raw_manifest.get("namespace", "unknown")
    name = raw_manifest.get("name", "unknown")

    if errors:
        error_details: list[dict[str, Any]] = []
        for err in errors:
            formatted_path = ".".join(str(elem) for elem in err.absolute_path) or "root"
            error_details.append(
                {
                    "path": formatted_path,
                    "message": err.message,
                    "validator": err.validator,
                    "validator_value": str(err.validator_value),
                }
            )
            logger.error(
                "Syntax validation error for manifest '%s/%s' at path '%s': %s [schema_digest=%s]",
                namespace,
                name,
                formatted_path,
                err.message,
                schema_digest,
            )

        first_error_msg = error_details[0]["message"]
        first_error_path = error_details[0]["path"]
        raise SchemaValidationError(
            message=f"Manifest syntax validation failed at '{first_error_path}': {first_error_msg}",
            schema_path=resolved_path_str,
            details={
                "manifest_identifier": f"{namespace}/{name}",
                "schema_digest": schema_digest,
                "error_count": len(error_details),
                "errors": error_details,
            },
        )

    duration_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "Successfully validated syntax for manifest '%s/%s' in %.2fms [schema_digest=%s]",
        namespace,
        name,
        duration_ms,
        schema_digest,
    )
    return raw_manifest


def parse_and_validate_yaml(
    raw_yaml_str: str,
    schema_path: Path | None = None,
    settings: CompilerSettings | None = None,
) -> dict[str, Any]:
    """Parses raw YAML text and immediately validates its syntax structure."""
    if not isinstance(raw_yaml_str, str) or not raw_yaml_str.strip():
        raise ManifestSyntaxError(
            "Raw YAML manifest input must be a non-empty string.",
            details={"input_type": type(raw_yaml_str).__name__},
        )

    try:
        parsed_dict = yaml.safe_load(raw_yaml_str)
    except yaml.YAMLError as err:
        logger.error("Failed to parse raw YAML manifest string: %s", err)
        line_num = getattr(err, "problem_mark", None)
        line_index = line_num.line + 1 if line_num else None
        raise ManifestSyntaxError(
            message=f"YAML syntax parsing failure: {err}",
            line_number=line_index,
            details={"yaml_error": str(err)},
        ) from err

    if not isinstance(parsed_dict, dict):
        raise ManifestSyntaxError(
            message=f"Expected top-level YAML mapping/dict, received {type(parsed_dict).__name__}",
            details={"received_type": type(parsed_dict).__name__},
        )

    return validate_manifest_syntax(parsed_dict, schema_path=schema_path, settings=settings)
