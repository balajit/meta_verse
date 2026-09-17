"""Configuration loader with OpenBao integration and robust error handling."""

from typing import Optional
from pydantic import Field, AliasChoices, ValidationError
from pydantic_settings import SettingsConfigDict
from meta_config import MetaBaseSettings
from meta_builder_brain.exceptions import ConfigurationError

__all__ = ["BrainSettings", "bootstrap_configuration", "ConfigurationError"]


class BrainSettings(MetaBaseSettings):
    """Centralized configuration for meta_builder_brain loaded via meta-config."""

    model_config = SettingsConfigDict(
        env_prefix="BRAIN_",
        extra="ignore",
        populate_by_name=True,
    )

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/meta_brain",
        description="Async PostgreSQL database URL",
        validation_alias=AliasChoices("BRAIN_DATABASE_URL", "DATABASE_URL"),
    )
    OPA_SIDECAR_URL: str = Field(
        default="http://localhost:8181/v1/data",
        description="Open Policy Agent sidecar endpoint URL",
        validation_alias=AliasChoices("BRAIN_OPA_SIDECAR_URL", "OPA_SIDECAR_URL"),
    )
    BCR_URN_PREFIX: str = Field(
        default="urn:meta:bcr:",
        description="URN prefix for Blueprint Component Registry entities",
        validation_alias=AliasChoices("BRAIN_BCR_URN_PREFIX", "BCR_URN_PREFIX"),
    )
    ENVIRONMENT: str = Field(
        default="production",
        description="Deployment environment name",
        validation_alias=AliasChoices("BRAIN_ENVIRONMENT", "ENVIRONMENT"),
    )
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Application logging verbosity level",
        validation_alias=AliasChoices("BRAIN_LOG_LEVEL", "LOG_LEVEL"),
    )
    OPENBAO_URL: Optional[str] = Field(
        default=None,
        description="OpenBao secrets server endpoint URL",
        validation_alias=AliasChoices("BRAIN_OPENBAO_URL", "OPENBAO_URL"),
    )
    OPENBAO_TOKEN: Optional[str] = Field(
        default=None,
        description="Authentication token for OpenBao secrets server",
        validation_alias=AliasChoices("BRAIN_OPENBAO_TOKEN", "OPENBAO_TOKEN"),
    )

    @property
    def database_url(self) -> str:
        return self.DATABASE_URL

    @property
    def opa_sidecar_url(self) -> str:
        return self.OPA_SIDECAR_URL

    @property
    def bcr_urn_prefix(self) -> str:
        return self.BCR_URN_PREFIX

    @property
    def environment(self) -> str:
        return self.ENVIRONMENT

    @property
    def log_level(self) -> str:
        return self.LOG_LEVEL


def bootstrap_configuration() -> BrainSettings:
    """Bootstraps application settings with error handling for misconfigurations."""
    try:
        return BrainSettings()
    except ValidationError as exc:
        raise ConfigurationError(
            f"Failed to bootstrap settings due to validation errors: {exc}"
        ) from exc
    except Exception as exc:
        raise ConfigurationError(
            f"Unexpected error bootstrapping BrainSettings: {exc}"
        ) from exc