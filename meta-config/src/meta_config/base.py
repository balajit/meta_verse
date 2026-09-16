"""Base Settings implementation enforcing runtime immutability and boot validation."""

import sys
from typing import Any, Tuple, Type, ClassVar
from pydantic import ValidationError
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from meta_config.exceptions import BootConfigurationError, ConfigValidationError
from meta_config.loaders.openbao import OpenBaoSettingsSource
from meta_config.telemetry import log_config_error, log_config_event, trace_config_span


class MetaBaseSettings(BaseSettings):
    """Base class for all system setting configurations with strict immutability and boot validation."""

    model_config = SettingsConfigDict(
        frozen=True,
        extra="forbid",
        validate_default=True,
        arbitrary_types_allowed=True,
        case_sensitive=False,
    )
    openbao_path: ClassVar[str | None] = None

    def __init__(self, **values: Any) -> None:
        class_name = self.__class__.__name__
        with trace_config_span(f"config_validation:{class_name}"):
            try:
                super().__init__(**values)
                log_config_event(
                    event_type="boot_validation",
                    status="success",
                    metadata={"config_class": class_name},
                )
            except ValidationError as val_err:
                errors = val_err.errors()
                config_err = ConfigValidationError(
                    message=f"Configuration validation failed for {class_name}",
                    errors=errors,
                    context={"config_class": class_name},
                )
                log_config_error("boot_validation", config_err, {"config_class": class_name, "errors": errors})
                sys.stderr.write(f"FATAL: Application boot halted due to malformed configuration in {class_name}.\n")
                raise BootConfigurationError(
                    message=f"Boot sequence halted: {class_name} configuration invalid.",
                    context={"root_cause": config_err.errors},
                ) from val_err

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        secret_path = cls.openbao_path

        openbao_source = OpenBaoSettingsSource(settings_cls, secret_path=secret_path)
        return (
            init_settings,
            env_settings,
            openbao_source,
            dotenv_settings,
            file_secret_settings,
        )