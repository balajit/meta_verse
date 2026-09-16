"""Unit tests for MetaBaseSettings, boot validation, immutability, and telemetry context."""

import os
from unittest.mock import MagicMock, patch
import pytest
from pydantic import Field, SecretStr, ValidationError
from meta_config.base import MetaBaseSettings
from meta_config.exceptions import BootConfigurationError, ConfigValidationError


class SimpleAppSettings(MetaBaseSettings):
    app_name: str = Field(default="meta-service")
    port: int = Field(default=8080, ge=1, le=65535)
    secret_key: SecretStr = Field(...)


class CustomPathSettings(MetaBaseSettings):
    database_url: str = Field(default="postgresql://localhost:5432/db")

    model_config = {
        "openbao_path": "secret/data/backend/database",
    }


def test_settings_boot_success_with_explicit_args() -> None:
    settings = SimpleAppSettings(secret_key=SecretStr("super-secret"))
    assert settings.app_name == "meta-service"
    assert settings.port == 8080
    assert settings.secret_key.get_secret_value() == "super-secret"


def test_settings_boot_success_from_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "override-app")
    monkeypatch.setenv("PORT", "9090")
    monkeypatch.setenv("SECRET_KEY", "env-secret")

    settings = SimpleAppSettings()
    assert settings.app_name == "override-app"
    assert settings.port == 9090
    assert settings.secret_key.get_secret_value() == "env-secret"


def test_settings_fail_fast_on_missing_required_field() -> None:
    with pytest.raises(BootConfigurationError) as exc_info:
        SimpleAppSettings()

    err = exc_info.value
    assert "Boot sequence halted: SimpleAppSettings configuration invalid." in err.message
    assert "root_cause" in err.context
    assert isinstance(err.__cause__, ValidationError)


def test_settings_fail_fast_on_invalid_value_type() -> None:
    with pytest.raises(BootConfigurationError) as exc_info:
        SimpleAppSettings(port=70000, secret_key=SecretStr("key"))

    err = exc_info.value
    assert "SimpleAppSettings" in err.message


def test_runtime_immutability_enforced() -> None:
    settings = SimpleAppSettings(secret_key=SecretStr("super-secret"))
    with pytest.raises(ValidationError):
        settings.app_name = "new-name"


def test_extra_fields_forbidden() -> None:
    with pytest.raises(BootConfigurationError):
        SimpleAppSettings(secret_key=SecretStr("key"), unknown_field="invalid")


def test_dict_based_model_config_openbao_path_extracted() -> None:
    with patch("meta_config.base.OpenBaoSettingsSource") as mock_source_cls:
        mock_instance = MagicMock()
        mock_instance.return_value = {}
        mock_source_cls.return_value = mock_instance

        _ = CustomPathSettings()
        mock_source_cls.assert_called_once_with(
            CustomPathSettings,
            secret_path="secret/data/backend/database",
        )