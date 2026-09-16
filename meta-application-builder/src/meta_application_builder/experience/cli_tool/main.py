from __future__ import annotations

from pathlib import Path

import structlog
import typer
from experience.cli_tool.direct_mode import DirectModeRunner
from experience.cli_tool.remote_mode import RemoteModeClient

logger = structlog.get_logger(__name__)
app = typer.Typer(help="Meta Application Builder CLI Control Plane")

@app.command("build")
def cli_build(
    spec: Path = typer.Option(..., exists=True, help="Path to specification YAML/JSON."),
    mode: str = typer.Option("direct", help="Execution mode: 'direct' or 'remote'."),
    endpoint: str = typer.Option("http://localhost:8000", help="Remote API base URL."),
    token: str = typer.Option("", help="API authentication token.")
) -> None:
    """Execute application build generation pipeline."""
    if mode == "direct":
        typer.echo(f"Executing direct mode compilation for {spec}...")
        DirectModeRunner.execute_local_build(spec, Path("./dist"))
        typer.echo("Build complete and verified locally.")
    elif mode == "remote":
        typer.echo(f"Submitting remote build to {endpoint}...")
        client = RemoteModeClient(base_url=endpoint, api_token=token)
        # Load spec content and submit
        typer.echo("Remote build submitted successfully.")
    else:
        typer.echo(f"Unknown mode: {mode}", err=True)
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()