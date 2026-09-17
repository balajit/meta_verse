from __future__ import annotations

import json
from itertools import islice
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from meta_service_generator.exceptions import ManifestValidationError
from meta_service_generator.local_telemetry import get_logger
from meta_service_generator.manifest.schema import ManifestSpec
from meta_telemetry import get_tracer, trace_span

logger = get_logger("meta_service_generator.manifest.validator")
tracer = get_tracer("meta_service_generator.manifest.validator")

_MAX_SCHEMA_ERRORS = 100


class ManifestValidator:
    """Validates manifests against JSON Schema and Pydantic."""

    def __init__(
        self,
        schema_path: Path | None = None,
    ) -> None:
        resolved_path = (
            schema_path
            if schema_path is not None
            else self._resolve_packaged_schema_path()
        )

        if not resolved_path.is_file():
            raise ManifestValidationError(
                message=(
                    "Manifest JSON Schema is missing: "
                    f"{resolved_path}"
                ),
                location=str(resolved_path),
                error_code="ERR_MANIFEST_SCHEMA_MISSING",
                suggested_resolution=(
                    "Ensure manifest.schema.json is packaged with "
                    "meta-service-generator."
                ),
            )

        try:
            schema_content = json.loads(
                resolved_path.read_text(
                    encoding="utf-8",
                )
            )
        except json.JSONDecodeError as err:
            raise ManifestValidationError(
                message=(
                    "Manifest JSON Schema is not valid JSON: "
                    f"{resolved_path}: {err}"
                ),
                location=str(resolved_path),
                error_code="ERR_MANIFEST_SCHEMA_INVALID_JSON",
                suggested_resolution=(
                    "Correct the packaged manifest.schema.json file."
                ),
                details={
                    "line": err.lineno,
                    "column": err.colno,
                },
            ) from err
        except (OSError, UnicodeError) as err:
            raise ManifestValidationError(
                message=(
                    "Failed to read Manifest JSON Schema from "
                    f"{resolved_path}: {err}"
                ),
                location=str(resolved_path),
                error_code="ERR_MANIFEST_SCHEMA_READ_FAILED",
                suggested_resolution=(
                    "Verify schema packaging, encoding, permissions, "
                    "and filesystem accessibility."
                ),
                details={
                    "exception_type": type(err).__name__,
                },
            ) from err

        try:
            Draft202012Validator.check_schema(
                schema_content
            )

            self._validator = Draft202012Validator(
                schema_content
            )
        except Exception as err:
            raise ManifestValidationError(
                message=(
                    "Failed to initialize JSON Schema "
                    f"Draft-2020-12 validator from {resolved_path}: {err}"
                ),
                location=str(resolved_path),
                error_code="ERR_MANIFEST_SCHEMA_INITIALIZATION",
                suggested_resolution=(
                    "Correct the packaged Draft-2020-12 manifest schema."
                ),
                details={
                    "exception_type": type(err).__name__,
                },
            ) from err

        self._schema_path = resolved_path

        logger.info(
            "Manifest validator initialized.",
            extra={
                "event_type": "manifest.validator.initialized",
                "schema_path": str(resolved_path),
            },
        )

    @staticmethod
    def _resolve_packaged_schema_path() -> Path:
        path = (
            Path(__file__).resolve().parents[1]
            / "schemas"
            / "manifest.schema.json"
        )

        if not path.is_file():
            raise ManifestValidationError(
                message=(
                    "Unable to resolve packaged "
                    f"manifest.schema.json: {path}"
                ),
                location=str(path),
                error_code="ERR_MANIFEST_SCHEMA_MISSING",
                suggested_resolution=(
                    "Ensure manifest.schema.json is included in "
                    "the installed package."
                ),
            )

        return path

    @trace_span("manifest.validator.validate")
    def validate(
        self,
        raw_manifest: dict[str, Any],
        source_label: str = "manifest",
    ) -> ManifestSpec:
        if not isinstance(raw_manifest, dict):
            raise ManifestValidationError(
                message=(
                    "Manifest root must be an object/dictionary, "
                    f"got {type(raw_manifest).__name__}."
                ),
                location=f"{source_label}#/",
                error_code="ERR_MANIFEST_ROOT_INVALID",
                suggested_resolution=(
                    "Ensure the manifest root is a JSON/YAML object."
                ),
            )

        errors = list(
            islice(
                self._validator.iter_errors(raw_manifest),
                _MAX_SCHEMA_ERRORS + 1,
            )
        )

        if errors:
            truncated = (
                len(errors) > _MAX_SCHEMA_ERRORS
            )

            visible_errors = errors[
                :_MAX_SCHEMA_ERRORS
            ]

            first_error = visible_errors[0]

            json_pointer = self._json_pointer(
                tuple(first_error.path)
            )

            details: dict[str, Any] = {
                "validation_error_count": len(
                    visible_errors
                ),
                "validation_errors": [
                    {
                        "path": self._json_pointer(
                            tuple(error.path)
                        ),
                        "message": error.message,
                        "validator": error.validator,
                    }
                    for error in visible_errors
                ],
            }

            if truncated:
                details["validation_errors_truncated"] = True

            logger.error(
                "JSON Schema validation failed at '%s': %s",
                json_pointer,
                first_error.message,
                extra={
                    "event_type": "manifest.validation.schema_error",
                    "location": f"{source_label}#{json_pointer}",
                    "error_count": len(visible_errors),
                },
            )

            raise ManifestValidationError(
                message=(
                    f"Schema violation at '{json_pointer}': "
                    f"{first_error.message}"
                ),
                location=(
                    f"{source_label}#{json_pointer}"
                ),
                error_code="ERR_MANIFEST_SCHEMA_VIOLATION",
                suggested_resolution=(
                    "Update manifest fields to match the "
                    "Draft-2020-12 schema."
                ),
                details=details,
            )

        try:
            manifest = ManifestSpec.model_validate(
                raw_manifest
            )
        except ValidationError as err:
            pydantic_errors = err.errors()

            if not pydantic_errors:
                raise ManifestValidationError(
                    message=(
                        "Manifest Pydantic validation failed without "
                        "a structured validation error."
                    ),
                    location=source_label,
                    error_code="ERR_MANIFEST_TYPE_MISMATCH",
                    suggested_resolution=(
                        "Verify manifest fields satisfy the runtime "
                        "Pydantic contract."
                    ),
                ) from err

            first_error = pydantic_errors[0]

            location = self._json_pointer(
                tuple(first_error["loc"])
            )

            logger.error(
                "Pydantic type compilation error at '%s': %s",
                location,
                first_error["msg"],
                extra={
                    "event_type": "manifest.validation.type_error",
                    "location": f"{source_label}#{location}",
                    "pydantic_error_count": len(pydantic_errors),
                },
            )

            raise ManifestValidationError(
                message=(
                    f"Type compilation error at '{location}': "
                    f"{first_error['msg']}"
                ),
                location=f"{source_label}#{location}",
                error_code="ERR_MANIFEST_TYPE_MISMATCH",
                suggested_resolution=(
                    "Verify manifest fields satisfy the runtime "
                    "Pydantic contract."
                ),
                details={
                    "validation_error_count": len(
                        pydantic_errors
                    ),
                    "validation_errors": [
                        {
                            "path": self._json_pointer(
                                tuple(error["loc"])
                            ),
                            "message": error["msg"],
                        }
                        for error in pydantic_errors
                    ],
                },
            ) from err

        logger.info(
            "Manifest validation succeeded.",
            extra={
                "event_type": "manifest.validation_succeeded",
                "source_label": source_label,
                "entity_count": len(manifest.entities),
                "workflow_count": len(manifest.workflows),
                "policy_count": len(manifest.policies),
            },
        )

        return manifest

    @staticmethod
    def _json_pointer(
        path: tuple[object, ...],
    ) -> str:
        if not path:
            return "/"

        return "/" + "/".join(
            str(element)
            .replace("~", "~0")
            .replace("/", "~1")
            for element in path
        )