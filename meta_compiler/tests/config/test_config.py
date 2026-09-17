"""Configuration guardrail tests.

These encode the review-mandated fail-fast contract: ``CompilerSettings``
performs runtime asset/env validation at construction (Pydantic validation ->
asset/config validation -> construction succeeds or halts).
"""

import os
from pathlib import Path

import pytest

from meta_compiler.config import CompilerSettings, ConfigurationError
from meta_compiler.exceptions import ConfigurationError as CanonicalConfigurationError


def test_configuration_error_identity_is_canonical() -> None:
    assert ConfigurationError is CanonicalConfigurationError


def test_instantiation_resolves_packaged_schema_asset() -> None:
    settings = CompilerSettings()
    resolved = settings.get_resolved_schema_path()
    assert resolved.exists()
    assert resolved.is_file()
    assert resolved.name == "meta_schema_v1.json"


def test_instantiation_halts_when_schema_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing_schema.json"
    with pytest.raises(ConfigurationError):
        CompilerSettings(schema_path=missing)


def test_instantiation_halts_when_schema_path_is_directory(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        CompilerSettings(schema_path=tmp_path)


def test_instantiation_succeeds_with_valid_explicit_schema(tmp_path: Path) -> None:
    schema_file = tmp_path / "meta_schema_v1.json"
    schema_file.write_text("{}", encoding="utf-8")
    settings = CompilerSettings(schema_path=schema_file)
    assert settings.get_resolved_schema_path() == schema_file.resolve()


def test_production_without_db_url_halts_at_construction(tmp_path: Path) -> None:
    schema_file = tmp_path / "meta_schema_v1.json"
    schema_file.write_text("{}", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        CompilerSettings(
            environment="production",
            schema_path=schema_file,
            db_connection_url=None,
        )


def test_production_with_explicit_db_url_constructs(tmp_path: Path) -> None:
    schema_file = tmp_path / "meta_schema_v1.json"
    schema_file.write_text("{}", encoding="utf-8")
    settings = CompilerSettings(
        environment="production",
        schema_path=schema_file,
        db_connection_url="postgresql+asyncpg://u:p@db:5432/meta",
    )
    assert settings.environment == "production"


def test_test_environment_is_exempt_from_runtime_validation() -> None:
    settings = CompilerSettings(
        environment="test",
        schema_path=Path("/definitely/not/present.json"),
    )
    assert settings.environment == "test"


def test_environment_from_env_variable() -> None:
    os.environ["ENVIRONMENT"] = "test"
    try:
        settings = CompilerSettings()
        assert settings.environment == "test"
    finally:
        os.environ.pop("ENVIRONMENT", None)


def test_whitespace_db_url_is_treated_as_unset(tmp_path: Path) -> None:
    schema_file = tmp_path / "meta_schema_v1.json"
    schema_file.write_text("{}", encoding="utf-8")
    settings = CompilerSettings(
        db_connection_url="   ",
        schema_path=schema_file,
    )
    assert settings.get_db_url_string() is None
