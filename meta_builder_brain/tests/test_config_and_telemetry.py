import os
import logging
import pytest
from unittest.mock import patch
from meta_config import BootConfigurationError
from meta_builder_brain.config import (
    BrainSettings,
    bootstrap_configuration,
    ConfigurationError,
)
from meta_builder_brain.telemetry import setup_telemetry, with_trace


def test_brain_settings_defaults():
    settings = BrainSettings(
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db",
        OPA_SIDECAR_URL="http://localhost:8181/v1/data",
        BCR_URN_PREFIX="urn:meta:bcr:",
    )
    assert settings.environment == "production"
    assert settings.log_level == "INFO"
    assert settings.bcr_urn_prefix == "urn:meta:bcr:"


def test_bootstrap_configuration_success():
    settings = bootstrap_configuration()
    assert isinstance(settings, BrainSettings)


def test_bootstrap_configuration_failure():
    with patch(
        "meta_builder_brain.config.BrainSettings",
        side_effect=Exception("Config load error"),
    ):
        with pytest.raises(ConfigurationError) as exc_info:
            bootstrap_configuration()
        assert "Unexpected error bootstrapping BrainSettings" in str(exc_info.value)
        assert "Config load error" in str(exc_info.value)


def test_setup_telemetry(tmp_path):
    log_file = tmp_path / "test_app.log"
    setup_telemetry(log_level="DEBUG", log_file_path=str(log_file))

    logger = logging.getLogger("test_logger")
    logger.debug("Telemetry verification log entry")

    assert log_file.exists()


def test_with_trace_decorator():
    @with_trace(span_name="test_span_execution")
    def dummy_function(x: int, y: int) -> int:
        return x + y

    result = dummy_function(5, 10)
    assert result == 15