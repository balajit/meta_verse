from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from meta_config import MetaBaseSettings
from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from meta_service_generator.exceptions import ConfigurationError


class FrozenDict(dict[str, Any]):
    """Dict-compatible container that rejects every in-place mutation."""

    def _immutable(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("GeneratorSettings mappings are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    __iadd__ = _immutable
    __imul__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable


def _freeze_mapping(
    value: Mapping[str, Any],
) -> FrozenDict:
    """Create an immutable copy of a configuration mapping."""
    return FrozenDict(dict(value))


class GeneratorSettings(MetaBaseSettings):
    """Validated, immutable generator configuration."""

    target_emission_path: Path = Field(
        default=Path("./output"),
        description=(
            "Target directory for synthesized FastAPI service source files."
        ),
    )

    strictness_flags: dict[str, bool] = Field(
        default_factory=lambda: FrozenDict(
            {
                "enforce_strict_types": True,
                "fail_on_warning": False,
                "validate_referential_integrity": True,
            }
        ),
        description=(
            "Behavioral strictness settings for code generation stages."
        ),
    )

    formatting_preferences: dict[str, str] = Field(
        default_factory=lambda: FrozenDict(
            {
                "line_length": "100",
                "formatter": "ruff",
            }
        ),
        description=(
            "Code formatting configuration applied during AST post-processing."
        ),
    )

    json_diagnostics: bool = Field(default=False)
    debug: bool = Field(default=False)

    model_config = SettingsConfigDict(
        env_prefix="META_GEN_",
        env_file_encoding="utf-8",
        case_sensitive=False,
        frozen=True,
        extra="forbid",
        validate_default=True,
    )

    @field_validator(
        "target_emission_path",
        mode="after",
    )
    @classmethod
    def validate_emission_path(
        cls,
        value: Path,
    ) -> Path:
        """Normalize the configured output path before execution."""
        return value.expanduser().resolve()

    @field_validator(
        "strictness_flags",
        "formatting_preferences",
        mode="after",
    )
    @classmethod
    def freeze_mappings(
        cls,
        value: dict[str, Any],
    ) -> FrozenDict:
        """Convert configuration mappings into immutable snapshots."""
        return _freeze_mapping(value)

    def get_strictness(
        self,
        key: str,
        default: bool = True,
    ) -> bool:
        """Return a strictness flag with an explicit default."""
        return self.strictness_flags.get(key, default)


def load_settings(
    **overrides: Any,
) -> GeneratorSettings:
    """Construct settings and fail immediately on malformed configuration."""
    try:
        return GeneratorSettings(**overrides)
    except Exception as err:
        raise ConfigurationError(
            message="Malformed or missing generator configuration.",
            location="GeneratorSettings",
            error_code="ERR_CONFIGURATION_INVALID",
            suggested_resolution=(
                "Correct generator configuration before starting "
                "the generation pipeline."
            ),
            details={
                "exception_type": type(err).__name__,
            },
        ) from err