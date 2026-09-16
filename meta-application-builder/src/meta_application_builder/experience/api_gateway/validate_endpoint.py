from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, status
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1/build", tags=["Validation"])


class ValidateRequest(BaseModel):
    spec_payload: dict[str, Any] = Field(..., description="Raw specification dictionary.")


class ValidateResponse(BaseModel):
    is_valid: bool
    violations: list[str] = Field(default_factory=list)


@router.post("/validate", response_model=ValidateResponse, status_code=status.HTTP_200_OK)
async def validate_spec(payload: ValidateRequest) -> ValidateResponse:
    logger.info("dry_run_validation_started", keys=list(payload.spec_payload.keys()))
    # Dry-run validation check simulation
    violations: list[str] = []

    if not payload.spec_payload:
        violations.append("Specification payload cannot be empty.")

    is_valid = len(violations) == 0
    logger.info("dry_run_validation_completed", is_valid=is_valid, violation_count=len(violations))

    return ValidateResponse(is_valid=is_valid, violations=violations)