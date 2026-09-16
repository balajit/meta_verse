from __future__ import annotations

from pathlib import Path
from typing import Annotated

from meta_service_generator.config import GeneratorSettings, load_settings
from meta_service_generator.diagnostics import DiagnosticEngine
from meta_service_generator.exceptions import GeneratorError
from meta_telemetry import get_tracer, trace_span
import typer

tracer = get_tracer("meta_service_generator.cli")

app = typer.Typer(
    name="meta-service-generator",
    help="Synthesizes production-grade zero-modification FastAPI microservices.",
    add_completion=False,
)


def _handle_execution_failure(exc: Exception, json_diagnostics: bool) -> None:
    engine = DiagnosticEngine(json_mode=json_diagnostics)
    report = engine.create_report_from_exception(exc)
    engine.emit(report)
    raise typer.Exit(code=1)


@app.command("generate")
@trace_span("cli.generate")
def generate_command(
    manifest: Annotated[
        Path,
        typer.Option(
            "--manifest",
            "-m",
            help="Path to input JSON or YAML service manifest.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            "-o",
            help="Directory path where synthesized service files will be emitted.",
            resolve_path=True,
        ),
    ],
    json_diagnostics: Annotated[
        bool,
        typer.Option(
            "--json-diagnostics",
            help="Emit errors strictly using REQ-030 JSON structure.",
        ),
    ] = False,
) -> None:
    """Generates a zero-modification FastAPI service from a valid manifest."""
    try:
        settings: GeneratorSettings = load_settings(
            target_emission_path=output_dir,
            json_diagnostics=json_diagnostics,
        )
        typer.echo(f"Ingesting manifest from: {manifest}")
        typer.echo(f"Emitting microservice to: {settings.target_emission_path}")

        # Pipeline invocation will occur in Stage 2/3 bindings
    except Exception as exc:
        _handle_execution_failure(exc, json_diagnostics)


@app.command("verify")
@trace_span("cli.verify")
def verify_command(
    project_dir: Annotated[
        Path,
        typer.Option(
            "--project-dir",
            "-p",
            help="Path to generated microservice project directory.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            resolve_path=True,
        ),
    ],
    json_diagnostics: Annotated[
        bool,
        typer.Option(
            "--json-diagnostics",
            help="Emit errors strictly using REQ-030 JSON structure.",
        ),
    ] = False,
) -> None:
    """Executes Stage 6 readiness verification suite against a target service."""
    try:
        typer.echo(f"Verifying target microservice project at: {project_dir}")
        # Stage 6 runner invocation will occur here
    except Exception as exc:
        _handle_execution_failure(exc, json_diagnostics)


@app.command("schema")
@trace_span("cli.schema")
def schema_command(
    export: Annotated[
        Path,
        typer.Option(
            "--export",
            "-e",
            help="File path to export JSON Schema definition.",
            resolve_path=True,
        ),
    ],
    json_diagnostics: Annotated[
        bool,
        typer.Option(
            "--json-diagnostics",
            help="Emit errors strictly using REQ-030 JSON structure.",
        ),
    ] = False,
) -> None:
    """Exports the Draft 2020-12 manifest schema specification[cite: 2]."""
    try:
        typer.echo(f"Exporting manifest schema to: {export}")
        # Schema export invocation will occur here
    except Exception as exc:
        _handle_execution_failure(exc, json_diagnostics)


if __name__ == "__main__":
    app()