"""Unit tests for ResilienceConfig bounds and validation."""

import pytest
from meta_resiliency.config import ResilienceConfig


def test_config_defaults() -> None:
    cfg = ResilienceConfig()
    assert cfg.enable_telemetry is True
    assert cfg.default_timeout_seconds == 30.0
    assert cfg.max_retry_attempts == 3


def test_config_invalid_backoff_bounds() -> None:
    with pytest.raises(BaseException):
        ResilienceConfig(
            retry_backoff_min_seconds=10.0,
            retry_backoff_max_seconds=2.0,
        )