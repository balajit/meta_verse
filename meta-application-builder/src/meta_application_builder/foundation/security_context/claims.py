from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional

import jwt
from jwt import PyJWKClient
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SecurityClaimsException(Exception):
    """Base exception for claim validation failures."""
    pass


class InvalidTenantIdentifierError(SecurityClaimsException):
    """Raised when tenant_id fails strict structural or namespace constraints."""
    pass


class SecurityClaims(BaseModel):
    """
    Pydantic v2 strict domain schema for OIDC RS256/ES256 JWT claims.
    Enforces mandatory security boundaries before any downstream handling.
    """
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    iss: str = Field(..., description="Issuer authority URI (e.g., https://identity.meta.internal)")
    sub: str = Field(..., description="Subject unique workload or user identifier")
    aud: str = Field(..., description="Target service audience identifier")
    exp: int = Field(..., gt=0, description="Expiration epoch timestamp in seconds")
    nbf: int = Field(..., gt=0, description="Not-before epoch timestamp in seconds")
    iat: int = Field(..., gt=0, description="Issued-at epoch timestamp in seconds")
    jti: str = Field(..., min_length=8, description="Unique JWT Token Identifier for replay protection")
    tenant_id: str = Field(..., description="Tenant namespace identifier matching pattern ^tenant_[a-z0-9_]{3,32}$")
    roles: List[str] = Field(default_factory=list, description="Assigned RBAC role identifiers")
    permissions: List[str] = Field(default_factory=list, description="Fine-grained ABAC permission strings")

    @property
    def principal(self) -> str:
        """Convenience accessor returning the subject identifier."""
        return self.sub

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_id_format(cls, value: str) -> str:
        pattern = r"^tenant_[a-z0-9_]{3,32}$"
        if not re.match(pattern, value):
            raise InvalidTenantIdentifierError(
                f"Invalid tenant_id '{value}'. Must match format '{pattern}'."
            )
        return value

    @field_validator("exp")
    @classmethod
    def validate_temporal_window(cls, value: int, info) -> int:
        if "nbf" in info.data and value <= info.data["nbf"]:
            raise SecurityClaimsException("Token expiration (exp) must be strictly greater than not-before (nbf)")

        # Runtime Temporal Validation with clock skew
        now = datetime.now(timezone.utc).timestamp()
        if value <= now:
            raise SecurityClaimsException(f"Token has expired. Expiration: {value}, Current time: {now}")
        if "nbf" in info.data and info.data["nbf"] > now:
            raise SecurityClaimsException(
                f"Token is not yet valid. Not before: {info.data['nbf']}, Current time: {now}")

        return value

    @classmethod
    def verify_and_parse(
        cls,
        token: str,
        jwks_uri: str,
        expected_issuer: str,
        expected_audience: str,
        leeway_seconds: int = 60,
        algorithms: Optional[List[str]] = None
    ) -> SecurityClaims:
        """
        Fetches, caches, and rotates public keys from a JWKS endpoint; strictly enforces
        signature verification, algorithm allowlisting, iss/aud assertions, and clock skew validation.
        """
        allowed_algorithms = algorithms or ["RS256", "ES256"]
        try:
            jwk_client = PyJWKClient(jwks_uri)
            signing_key = jwk_client.get_signing_key_from_jwt(token)

            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=allowed_algorithms,
                audience=expected_audience,
                issuer=expected_issuer,
                leeway=leeway_seconds,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                    "verify_iss": True,
                    "verify_aud": True,
                }
            )
            return cls(**payload)
        except jwt.PyJWTError as err:
            raise SecurityClaimsException(f"JWT verification failed: {err}") from err
        except Exception as err:
            raise SecurityClaimsException(f"Unexpected error validating claims: {err}") from err