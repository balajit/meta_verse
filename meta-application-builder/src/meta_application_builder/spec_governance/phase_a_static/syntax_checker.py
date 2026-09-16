from __future__ import annotations

import asyncio
import json
import logging

import ruamel.yaml
from pydantic import ValidationError

from meta_application_builder.spec_governance.schemas.det_schema import (
    DomainEntityTemplate,
)
from meta_application_builder.spec_governance.schemas.rfc7807_error import (
    ProblemDetails,
    ValidationErrorDetail,
)

logger = logging.getLogger("meta_application_builder.spec_governance.syntax_checker")


class GovernanceSyntaxError(Exception):
    """Raised when Phase A payload syntax or schema deserialization fails."""

    def __init__(self, problem: ProblemDetails) -> None:
        super().__init__(problem.detail)
        self.problem = problem


class StaticSyntaxChecker:
    """Phase A Validator: Performs payload size verification, format parsing, and Pydantic schema validation."""

    MAX_PAYLOAD_BYTES: int = 2 * 1024 * 1024  # 2MB Hard Limit[cite: 6]

    @classmethod
    def _parse_and_validate_sync(cls, raw_content: str, format_type: str, instance_uri: str) -> DomainEntityTemplate:
        """Synchronous parsing and validation worker executed inside a thread worker pool."""
        # Payload size validation
        if len(raw_content.encode("utf-8")) > cls.MAX_PAYLOAD_BYTES:
            logger.error("Payload size exceeds limit of %d bytes for instance: %s", cls.MAX_PAYLOAD_BYTES, instance_uri)
            problem = ProblemDetails.create(
                status=413,
                title="Payload Too Large",
                detail=f"Specification size exceeds maximum limit of {cls.MAX_PAYLOAD_BYTES} bytes.",
                instance=instance_uri,
                invalid_params=[ValidationErrorDetail(field_path="$", code="MBR-001", message="Payload size too large.")],
            )
            raise GovernanceSyntaxError(problem)

        # Parsing
        try:
            if format_type.lower() == "json":
                parsed_dict = json.loads(raw_content)
            elif format_type.lower() in ("yaml", "yml"):
                yaml = ruamel.yaml.YAML(typ="safe")
                parsed_dict = yaml.load(raw_content)
            else:
                problem = ProblemDetails.create(
                    status=400,
                    title="Unsupported Media Type",
                    detail=f"Format '{format_type}' is unsupported. Must be 'json' or 'yaml'.",
                    instance=instance_uri,
                    invalid_params=[ValidationErrorDetail(field_path="format", code="MBR-002", message="Unsupported format.")],
                )
                raise GovernanceSyntaxError(problem)
        except Exception as parse_exc:
            if isinstance(parse_exc, GovernanceSyntaxError):
                raise
            logger.error("Failed to parse raw content as %s: %s", format_type, str(parse_exc))
            problem = ProblemDetails.create(
                status=400,
                title="Malformed Syntax",
                detail=f"Invalid {format_type.upper()} document syntax: {str(parse_exc)}",
                instance=instance_uri,
                invalid_params=[ValidationErrorDetail(field_path="$", code="MBR-003", message="Syntax parsing failure.")],
            )
            raise GovernanceSyntaxError(problem) from parse_exc

        # Schema Validation
        try:
            model = DomainEntityTemplate.model_validate(parsed_dict)
            logger.info("Phase A syntax parsing succeeded for URN: '%s'", model.urn)
            return model
        except ValidationError as val_exc:
            logger.error("Pydantic validation failed for instance %s: %s", instance_uri, str(val_exc))
            invalid_params = []
            for err in val_exc.errors():
                loc = ".".join([str(p) for p in err["loc"]])
                invalid_params.append(
                    ValidationErrorDetail(field_path=loc, code="MBR-004", message=err["msg"])
                )

            problem = ProblemDetails.create(
                status=422,
                title="Schema Validation Error",
                detail="Domain Entity Template payload failed structural schema validation rules.",
                instance=instance_uri,
                invalid_params=invalid_params,
            )
            raise GovernanceSyntaxError(problem) from val_exc

    @classmethod
    async def parse_and_validate_async(cls, raw_content: str, format_type: str, instance_uri: str) -> DomainEntityTemplate:
        """Asynchronously offloads CPU-bound parsing and validation to a background thread to keep the event loop unblocked."""
        logger.info("Executing non-blocking Phase A syntax validation for instance: '%s'", instance_uri)
        return await asyncio.to_thread(cls._parse_and_validate_sync, raw_content, format_type, instance_uri)