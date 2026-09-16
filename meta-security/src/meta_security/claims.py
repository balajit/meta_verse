"""Claim extraction and immutable schema validation using Pydantic."""

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


class TokenClaims(BaseModel):
    """Immutable representation of validated identity token claims."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=True,
    )

    sub: StrictStr = Field(
        ...,
        description="Subject identifier (e.g., user UUID)",
    )
    exp: StrictInt = Field(
        ...,
        description="Expiration timestamp in epoch seconds",
    )
    iss: StrictStr | None = Field(
        default=None,
        description="Token Issuer",
    )
    aud: StrictStr | tuple[StrictStr, ...] | None = Field(
        default=None,
        description="Intended audience",
    )
    roles: tuple[StrictStr, ...] = Field(
        default_factory=tuple,
        description="List of RBAC roles assigned to subject",
    )
    tenant_id: StrictStr | None = Field(
        default=None,
        description="Associated tenant scope, if applicable",
    )

    @property
    def is_service_account(self) -> bool:
        """Helper to determine if the claims belong to a machine-to-machine context."""
        return "service_account" in self.roles