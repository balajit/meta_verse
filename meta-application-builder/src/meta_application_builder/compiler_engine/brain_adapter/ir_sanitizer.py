from __future__ import annotations

from typing import Any

import structlog
from pydantic import BaseModel, Field, ValidationError, model_validator

logger = structlog.get_logger(__name__)


class IRSanitizationError(Exception):
    """Raised when untrusted IR violates structural or safety constraints."""
    pass


class UntrustedIRField(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    type_hint: str = Field(..., min_length=1, max_length=64)
    nullable: bool = False
    default: Any | None = None

    @model_validator(mode="after")
    def validate_safety(self) -> UntrustedIRField:
        forbidden = {"__globals__", "__code__", "__closure__", "__dict__"}
        if self.name in forbidden or self.type_hint in forbidden:
            raise IRSanitizationError(f"Forbidden symbol detected in field spec: {self.name}")
        return self


class UntrustedIRModel(BaseModel):
    model_name: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    fields: list[UntrustedIRField] = Field(..., max_length=512)
    metadata: dict[str, str] = Field(default_factory=dict, max_length=32)


class IRSanitizer:
    MAX_RECURSION_DEPTH: int = 16

    @classmethod
    def sanitize(cls, raw_payload: dict[str, Any], depth: int = 0) -> UntrustedIRModel:
        if depth > cls.MAX_RECURSION_DEPTH:
            logger.error("ir_sanitization_max_depth_exceeded", depth=depth)
            raise IRSanitizationError("Maximum recursion depth exceeded during IR sanitization.")

        try:
            sanitized = UntrustedIRModel.model_validate(raw_payload)
            logger.info("ir_sanitization_success", model_name=sanitized.model_name, field_count=len(sanitized.fields))
            return sanitized
        except ValidationError as e:
            logger.warning("ir_sanitization_validation_failed", error=str(e))
            raise IRSanitizationError(f"Invalid untrusted IR structure: {e}") from e