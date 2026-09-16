from pathlib import Path
import pytest
from pydantic import ValidationError

from meta_service_generator.config import GeneratorSettings, load_settings


def test_generator_settings_defaults():
    settings = GeneratorSettings()
    assert settings.target_emission_path.is_absolute()
    assert settings.json_diagnostics is False
    assert settings.debug is False
    assert settings.get_strictness("enforce_strict_types") is True
    assert settings.get_strictness("non_existent_key", default=False) is False


def test_generator_settings_env_overrides(monkeypatch, tmp_path):
    target_dir = tmp_path / "custom_out"
    monkeypatch.setenv("META_GEN_TARGET_EMISSION_PATH", str(target_dir))
    monkeypatch.setenv("META_GEN_DEBUG", "true")
    monkeypatch.setenv("META_GEN_JSON_DIAGNOSTICS", "true")

    settings = GeneratorSettings()
    assert settings.target_emission_path == target_dir.resolve()
    assert settings.debug is True
    assert settings.json_diagnostics is True


@pytest.mark.parametrize(
    "invalid_kwargs",
    [
        {"strictness_flags": "invalid_type"},
        {"debug": "not_a_boolean"},
        {"extra_field": "forbid_extra"},
    ],
)
def test_load_settings_invalid_parsing_raises_runtime_error(invalid_kwargs):
    with pytest.raises(RuntimeError, match="Fatal configuration boot error"):
        load_settings(**invalid_kwargs)


def test_load_settings_successful_overrides(tmp_path):
    out_path = tmp_path / "output_test"
    settings = load_settings(target_emission_path=out_path, debug=True)
    assert settings.target_emission_path == out_path.resolve()
    assert settings.debug is True