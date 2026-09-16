"""Token validation mechanics, configuration, and JWT parsing."""

import logging
from typing import Any, ClassVar

import jwt
from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import SettingsConfigDict


from meta_config import MetaBaseSettings
from meta_security.claims import TokenClaims
from meta_security.exceptions import ClaimExtractionError, TokenValidationError
from meta_telemetry import trace_span

logger = logging.getLogger("meta_security")


class SecuritySettings(MetaBaseSettings):
    """Configuration constraints for cryptographic validation. Inherits boot-halting properties."""

    jwt_public_key: SecretStr = Field(
        ...,
        description="PEM encoded public key for signature verification",
    )
    jwt_algorithms: tuple[str, ...] = Field(
        default=("RS256",),
        description="Permitted cryptographic algorithms",
    )
    jwt_issuer: str | None = Field(
        default=None,
        description="Required issuer validation (if set)",
    )
    jwt_audience: str | None = Field(
        default=None,
        description="Required audience validation (if set)",
    )

    openbao_path: ClassVar[str] = "secret/data/backend/security"


def _extract_validation_telemetry(
    params: dict[str, Any],
) -> dict[str, Any]:
    """Sanitize span attributes to prevent leaking raw tokens."""
    return {"action": "validate_jwt"}


def _safe_validation_fields(error: ValidationError) -> list[str]:
    """Return only validation field locations without exposing invalid values."""
    fields: list[str] = []

    for item in error.errors():
        location = item.get("loc", ())
        field = ".".join(str(part) for part in location)

        if field and field not in fields:
            fields.append(field)

    return fields


@trace_span(
    name="validate_jwt",
    extract_attributes=_extract_validation_telemetry,
)
def validate_token(
    token: str,
    settings: SecuritySettings,
) -> TokenClaims:
    """Validate a raw JWT and extract it into a strongly-typed TokenClaims object.

    :param token: Raw encoded JWT string.
    :param settings: Validated SecuritySettings instance.
    :return: Immutable TokenClaims object.
    :raises TokenValidationError: If cryptography fails (e.g., expired, invalid signature).
    :raises ClaimExtractionError: If schema validation on the claims payload fails.
    """
    if not token:
        raise TokenValidationError(
            "Token validation failed.",
            context={"error": "empty_token"},
        )

    try:
        payload = jwt.decode(
            jwt=token,
            key=settings.jwt_public_key.get_secret_value(),
            algorithms=settings.jwt_algorithms,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={
                "require": ["exp", "sub"],
            },
        )

        claims = TokenClaims.model_validate(payload)

        logger.info(
            "Token successfully validated",
            extra={
                "event_type": "token_validation_success",
            },
        )

        return claims

    except jwt.ExpiredSignatureError as err:
        logger.warning(
            "Token has expired",
            extra={
                "event_type": "token_validation_failed",
                "error": "expired",
            },
        )

        raise TokenValidationError(
            "Token has expired.",
            context={"error": "expired"},
        ) from err

    except jwt.PyJWTError as err:
        logger.warning(
            "Token cryptographic validation failed",
            extra={
                "event_type": "token_validation_failed",
                "error": "invalid_token",
                "exception_type": type(err).__name__,
            },
        )

        raise TokenValidationError(
            "Token cryptographic validation failed.",
            context={
                "error": "invalid_token",
                "exception_type": type(err).__name__,
            },
        ) from err

    except ValidationError as err:
        fields = _safe_validation_fields(err)

        logger.error(
            "Token claims failed structural validation",
            extra={
                "event_type": "claim_extraction_failed",
                "error": "invalid_claims",
                "invalid_fields": fields,
            },
        )

        raise ClaimExtractionError(
            "Failed to parse identity claims from token payload.",
            context={
                "error": "invalid_claims",
                "invalid_fields": fields,
            },
        ) from err
