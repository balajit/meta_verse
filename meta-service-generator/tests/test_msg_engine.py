import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from meta_service_generator.msg_engine import MetaServiceGeneratorEngine
from meta_service_generator.exceptions import GeneratorError
from meta_service_generator.ir.model import ServiceIR

@pytest.fixture
def engine(tmp_path):
    return MetaServiceGeneratorEngine(default_output_dir=tmp_path / "output")

@pytest.fixture
def sample_manifest():
    return {
        "version": "1.0.0",
        "service_name": "test_service",
        "models": []
    }

def test_engine_initialization(tmp_path):
    eng = MetaServiceGeneratorEngine(default_output_dir=tmp_path)
    assert eng.default_output_dir == tmp_path
    assert eng.loader is not None

@patch("meta_service_generator.msg_engine.CodeGenerationPipeline")
@patch("meta_service_generator.msg_engine.VerificationRunner")
def test_generate_service_success(mock_verification_runner_cls, mock_pipeline_cls, engine, sample_manifest):
    mock_pipeline = MagicMock()
    mock_pipeline_cls.return_value = mock_pipeline
    mock_pipeline.execute.return_value = [Path("test_out/main.py")]

    mock_runner = MagicMock()
    mock_runner.verify_all.return_value = {"status": "passed", "errors": 0}
    mock_verification_runner_cls.return_value = mock_runner

    result = engine.generate_service(manifest_source=sample_manifest, verify=True)

    mock_pipeline_cls.assert_called_once()
    mock_pipeline.execute.assert_called_once()
    mock_runner.verify_all.assert_called_once()

    assert result["status"] == "success"
    assert "output_directory" in result
    assert result["verification"] == {"status": "passed", "errors": 0}

@patch("meta_service_generator.msg_engine.CodeGenerationPipeline")
def test_generate_service_pipeline_failure(mock_pipeline_cls, engine, sample_manifest):
    mock_pipeline = MagicMock()
    mock_pipeline.execute.side_effect = Exception("Manifest parsing error")
    mock_pipeline_cls.return_value = mock_pipeline

    with pytest.raises(GeneratorError, match="Generation pipeline failed"):
        engine.generate_service(manifest_source=sample_manifest, verify=False)

def test_generate_service_with_file_path(engine, sample_manifest, tmp_path):
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(sample_manifest))

    with patch("meta_service_generator.msg_engine.ManifestLoader") as mock_loader_cls, \
         patch("meta_service_generator.msg_engine.CodeGenerationPipeline") as mock_pipeline_cls, \
         patch("meta_service_generator.msg_engine.VerificationRunner") as mock_runner_cls:

        mock_loader = mock_loader_cls.return_value
        del mock_loader.load
        del mock_loader.load_manifest
        del mock_loader.parse_file

        mock_pipeline = mock_pipeline_cls.return_value
        mock_pipeline.execute.return_value = [Path("test_out/main.py")]

        mock_runner = mock_runner_cls.return_value
        mock_runner.verify_all.return_value = {}

        result = engine.generate_service(manifest_source=manifest_file, verify=True)

        assert result["status"] == "success"