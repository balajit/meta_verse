"""Unit tests for OpenBaoConfig and OpenBaoSettingsSource."""

from unittest.mock import MagicMock, patch
import pytest
from pydantic_settings import BaseSettings
from meta_config.exceptions import SecretInjectionError
from meta_config.loaders.openbao import OpenBaoConfig, OpenBaoSettingsSource


class DummySettings(BaseSettings):
    db_pass: str = "default_pass"


def test_openbao_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENBAO_ADDR", raising=False)
    monkeypatch.delenv("OPENBAO_TOKEN", raising=False)

    config = OpenBaoConfig()
    assert config.url == "http://127.0.0.1:8200"
    assert config.token == ""
    assert config.mount_point == "secret"


def test_openbao_config_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENBAO_ADDR", "https://openbao.internal:8200")
    monkeypatch.setenv("OPENBAO_TOKEN", "s.test-token")

    config = OpenBaoConfig()
    assert config.url == "https://openbao.internal:8200"
    assert config.token == "s.test-token"


def test_settings_source_returns_empty_when_no_secret_path() -> None:
    source = OpenBaoSettingsSource(DummySettings, secret_path=None)
    assert source() == {}


def test_settings_source_raises_error_on_missing_token() -> None:
    config = OpenBaoConfig(url="http://127.0.0.1:8200", token="")
    source = OpenBaoSettingsSource(DummySettings, secret_path="secret/data/app", openbao_config=config)

    with pytest.raises(SecretInjectionError) as exc_info:
        source()

    assert "OpenBao authentication token missing" in exc_info.value.message
    assert exc_info.value.secret_path == "secret/data/app"


@patch("hvac.Client")
def test_settings_source_raises_error_when_unauthenticated(mock_hvac_client: MagicMock) -> None:
    mock_client_instance = MagicMock()
    mock_client_instance.is_authenticated.return_value = False
    mock_hvac_client.return_value = mock_client_instance

    config = OpenBaoConfig(token="invalid-token")
    source = OpenBaoSettingsSource(DummySettings, secret_path="secret/data/app", openbao_config=config)

    with pytest.raises(SecretInjectionError) as exc_info:
        source()

    assert "OpenBao client authentication failed" in exc_info.value.message


@patch("hvac.Client")
def test_settings_source_successfully_fetches_secrets(mock_hvac_client: MagicMock) -> None:
    mock_client_instance = MagicMock()
    mock_client_instance.is_authenticated.return_value = True
    mock_client_instance.secrets.kv.v2.read_secret_version.return_value = {
        "data": {
            "data": {
                "db_pass": "super_secret_bao_password",
            }
        }
    }
    mock_hvac_client.return_value = mock_client_instance

    config = OpenBaoConfig(token="valid-token", mount_point="kv")
    source = OpenBaoSettingsSource(DummySettings, secret_path="secret/data/app", openbao_config=config)

    secrets = source()
    assert secrets == {"db_pass": "super_secret_bao_password"}
    mock_client_instance.secrets.kv.v2.read_secret_version.assert_called_once_with(
        path="secret/data/app",
        mount_point="kv",
    )


@patch("hvac.Client")
def test_settings_source_wraps_client_exceptions(mock_hvac_client: MagicMock) -> None:
    mock_client_instance = MagicMock()
    mock_client_instance.is_authenticated.side_effect = Exception("Connection refused")
    mock_hvac_client.return_value = mock_client_instance

    config = OpenBaoConfig(token="valid-token")
    source = OpenBaoSettingsSource(DummySettings, secret_path="secret/data/app", openbao_config=config)

    with pytest.raises(SecretInjectionError) as exc_info:
        source()

    assert "Failed to fetch secrets from OpenBao: Connection refused" in exc_info.value.message
    assert exc_info.value.__cause__ is not None