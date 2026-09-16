"""Pytest fixtures for meta-resiliency test suite."""

import pytest
from meta_resiliency.config import ResilienceConfig


@pytest.fixture
def default_config() -> ResilienceConfig:
    return ResilienceConfig()