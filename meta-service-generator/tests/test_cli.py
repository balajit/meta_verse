from __future__ import annotations

from pathlib import Path
import unittest.mock as mock

import pytest
from typer.testing import CliRunner

from meta_service_generator.cli import app
from meta_service_generator.exceptions import CodeGenerationError


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestCLIGenerateCommand:
    def test_generate_success(self, runner: CliRunner, tmp_path: Path) -> None:
        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text('{"service_name": "test"}')
        out_dir = tmp_path / "output"

        result = runner.invoke(
            app,
            [
                "generate",
                "--manifest",
                str(manifest_file),
                "--output-dir",
                str(out_dir),
            ],
        )

        assert result.exit_code == 0
        assert f"Ingesting manifest from: {manifest_file.resolve()}" in result.stdout
        assert "Emitting microservice to:" in result.stdout

    def test_generate_missing_manifest_argument(self, runner: CliRunner, tmp_path: Path) -> None:
        out_dir = tmp_path / "output"
        result = runner.invoke(app, ["generate", "--output-dir", str(out_dir)])

        assert result.exit_code != 0
        assert "Missing option '--manifest'" in result.output or "Error" in result.output

    def test_generate_non_existent_manifest_file(self, runner: CliRunner, tmp_path: Path) -> None:
        missing_manifest = tmp_path / "does_not_exist.json"
        out_dir = tmp_path / "output"

        result = runner.invoke(
            app,
            [
                "generate",
                "-m",
                str(missing_manifest),
                "-o",
                str(out_dir),
            ],
        )

        assert result.exit_code != 0

    def test_generate_pipeline_failure_with_json_diagnostics(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text('{"service_name": "test"}')
        out_dir = tmp_path / "output"

        gen_error = CodeGenerationError(
            message="Generation engine crashed.",
            location="stage2",
            error_code="ERR_STAGE2_FAILED",
            suggested_resolution="Check manifest configuration.",
        )

        with mock.patch("meta_service_generator.cli.load_settings", side_effect=gen_error):
            result = runner.invoke(
                app,
                [
                    "generate",
                    "-m",
                    str(manifest_file),
                    "-o",
                    str(out_dir),
                    "--json-diagnostics",
                ],
            )

        assert result.exit_code == 1
        assert "ERR_STAGE2_FAILED" in result.output
        assert '"generation_status": "failed"' in result.output


class TestCLIVerifyCommand:
    def test_verify_success(self, runner: CliRunner, tmp_path: Path) -> None:
        project_dir = tmp_path / "my_project"
        project_dir.mkdir()

        result = runner.invoke(
            app,
            [
                "verify",
                "--project-dir",
                str(project_dir),
            ],
        )

        assert result.exit_code == 0
        assert f"Verifying target microservice project at: {project_dir.resolve()}" in result.stdout

    def test_verify_failure_execution_error(self, runner: CliRunner, tmp_path: Path) -> None:
        project_dir = tmp_path / "my_project"
        project_dir.mkdir()

        with mock.patch("typer.echo", side_effect=RuntimeError("Verification runner crashed")):
            result = runner.invoke(
                app,
                [
                    "verify",
                    "-p",
                    str(project_dir),
                ],
            )

        assert result.exit_code == 1
        assert "Verification runner crashed" in result.output or "ERR_UNHANDLED_SYSTEM_EXCEPTION" in result.output


class TestCLISchemaCommand:
    def test_schema_export_success(self, runner: CliRunner, tmp_path: Path) -> None:
        export_path = tmp_path / "schema.json"

        result = runner.invoke(
            app,
            [
                "schema",
                "--export",
                str(export_path),
            ],
        )

        assert result.exit_code == 0
        assert f"Exporting manifest schema to: {export_path.resolve()}" in result.stdout

    def test_schema_export_failure_diagnostics(self, runner: CliRunner, tmp_path: Path) -> None:
        export_path = tmp_path / "schema.json"

        with mock.patch("typer.echo", side_effect=PermissionError("Permission denied writing schema")):
            result = runner.invoke(
                app,
                [
                    "schema",
                    "-e",
                    str(export_path),
                    "--json-diagnostics",
                ],
            )

        assert result.exit_code == 1
        assert "Permission denied writing schema" in result.output