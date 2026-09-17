"""Application settings and runtime environment configuration for meta_compiler.

CompilerSettings subclasses ``meta_config.MetaBaseSettings`` to inherit fail-fast
boot validation and optional OpenBao secret injection. Security-sensitive defaults
(development database credentials) are intentionally NOT embedded; the database
connection URL must be provided explicitly via environment / dotenv / OpenBao.
"""

import importlib.resources
import logging
from pathlib import Path
from typing import Any, Literal

from meta_config import MetaBaseSettings
from pydantic import Field, SecretStr, field_validator

logger = logging.getLogger("meta_compiler.config")


class CompilerSettings(MetaBaseSettings):
    """Compiler environment configurations with fail-fast boot validation.

    Instantiation performs Pydantic validation (fail-fast) followed by runtime
    asset validation (schema path existence, environment-specific rules) via
    :meth:`model_post_init`. A host application therefore cannot construct a
    :class:`MetaCompiler` with an invalid runtime configuration.
    """

    environment: Literal["development", "test", "production"] = Field(
        default="development",
        description="Execution environment stage.",
    )

    db_connection_url: SecretStr | None = Field(
        default=None,
        description=(
            "Database connection string with credential masking. No default is "
            "embedded; must be provided explicitly in all environments."
        ),
    )

    schema_path: Path | None = Field(
        default=None,
        description="Path override for JSON schema asset. Resolves to package resource if None.",
    )

    debug: bool = Field(default=False, description="Enable verbosity for compiler execution.")

    def model_post_init(self, __context: Any) -> None:
        """Runs runtime asset/config validation immediately after Pydantic validation.

        The ``test`` environment is exempt so suites can remain hermetic; every
        other environment halts the boot sequence on missing or malformed config.
        """
        if self.environment != "test":
            self.validate_runtime()

    @field_validator("db_connection_url", mode="before")
    @classmethod
    def _validate_db_url_not_empty(cls, value: Any) -> Any:
        """Coerces whitespace-only or empty connection strings to None for fast failure."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def get_db_url_string(self) -> str | None:
        """Safely extracts the raw database connection URL string."""
        return self.db_connection_url.get_secret_value() if self.db_connection_url else None

    def get_resolved_schema_path(self) -> Path:
        """Resolves schema path using explicit configuration or package resources safely."""
        if self.schema_path is not None:
            resolved = self.schema_path.resolve()
            logger.debug("Using explicit user-provided schema path: %s", resolved)
            return resolved

        try:
            ref = importlib.resources.files("meta_compiler").joinpath("schemas/meta_schema_v1.json")
            with importlib.resources.as_file(ref) as resource_path:
                resolved = resource_path.resolve()
                logger.debug("Resolved packaged schema resource path: %s", resolved)
                return resolved
        except Exception as err:
            logger.error("Failed to locate packaged schema resource: %s", err, exc_info=True)
            raise ConfigurationError(f"Failed to locate packaged schema resource: {err}") from err

    def validate_runtime(self) -> "CompilerSettings":
        """Validates environment-specific rules and mandatory runtime assets."""
        logger.info("Executing runtime environment validation for stage '%s'...", self.environment)

        raw_url = self.get_db_url_string()

        if self.environment == "production":
            if not raw_url:
                logger.error("Production runtime validation failed: empty DB URL supplied.")
                raise ConfigurationError(
                    "Production environment requires an explicitly configured "
                    "'META_COMPILER_DB_CONNECTION_URL'."
                )

        resolved_path = self.get_resolved_schema_path()

        if not resolved_path.exists():
            logger.error("Mandatory schema asset is missing at path: %s", resolved_path)
            raise ConfigurationError(
                f"Mandatory schema asset is missing: '{resolved_path}'",
                path=resolved_path,
            )

        if not resolved_path.is_file():
            logger.error("Configured schema path is not a file: %s", resolved_path)
            raise ConfigurationError(
                f"Configured schema path is not a file: '{resolved_path}'",
                path=resolved_path,
            )

        logger.info("Runtime validation successful. Schema asset verified at %s.", resolved_path)
        return self


# Re-export the canonical configuration exception so that both
# ``meta_compiler.config.ConfigurationError`` and
# ``meta_compiler.exceptions.ConfigurationError`` refer to the same class.
from meta_compiler.exceptions import ConfigurationError  # noqa: E402
