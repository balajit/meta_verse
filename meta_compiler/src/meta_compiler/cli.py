"""Command-Line Interface (CLI) driver for the meta_compiler pipeline."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from meta_compiler.config import CompilerSettings, ConfigurationError
from meta_compiler.core.telemetry import JSONFormatter
from meta_compiler.orchestrator import (
    PipelineCompilationError,
    compile_and_register_manifest,
    compile_manifest,
)

logger = logging.getLogger("meta_compiler.cli")


def build_cli_parser(default_db_url: str | None = None) -> argparse.ArgumentParser:
    """Constructs the command-line argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="meta-compiler",
        description="Meta-Builder Workflow Compiler & Graph Validation CLI Engine",
    )
    subparsers = parser.add_subparsers(
        dest="command",
        title="Subcommands",
        description="Supported operation modes",
        required=True,
    )

    validate_parser = subparsers.add_parser(
        "validate",
        help="Run local syntax, topology, and contract validation without database persistence.",
    )
    validate_parser.add_argument(
        "-f",
        "--file",
        type=Path,
        required=True,
        help="Path to raw workflow manifest YAML file",
    )

    register_parser = subparsers.add_parser(
        "register",
        help="Execute full compilation pipeline and register workflow in target database.",
    )
    register_parser.add_argument(
        "-f",
        "--file",
        type=Path,
        required=True,
        help="Path to raw workflow manifest YAML file",
    )
    register_parser.add_argument(
        "--db-url",
        type=str,
        default=default_db_url,
        help="Target PostgreSQL async connection URL",
    )

    return parser


def run_dry_run_validation(
    manifest_path: Path, settings_override: CompilerSettings | None = None
) -> bool:
    """Executes stages 1 through 4 of the pipeline locally without requiring database access."""
    logger.info("Executing dry-run validation for file: %s", manifest_path)
    if not manifest_path.is_file():
        logger.error("Specified manifest file does not exist: %s", manifest_path)
        return False

    try:
        raw_yaml_str = manifest_path.read_text(encoding="utf-8")
        compiled_def = compile_manifest(raw_yaml_str, settings=settings_override)
        logger.info(
            "VALIDATION SUCCESSFUL: Manifest '%s/%s' is valid.",
            compiled_def.manifest_spec.namespace if compiled_def.manifest_spec else "unknown",
            compiled_def.manifest_spec.name if compiled_def.manifest_spec else "unknown",
        )
        return True
    except PipelineCompilationError as err:
        logger.error("VALIDATION FAILED at [%s]: %s", err.stage, err)
        return False
    except Exception as err:
        logger.error("VALIDATION FAILED: %s", err)
        return False


async def run_registration(
    manifest_path: Path,
    db_url: str,
    settings_override: CompilerSettings | None = None,
) -> str | None:
    """Executes the complete 5-stage orchestration pipeline using an async SQLAlchemy session."""
    logger.info("Executing registration pipeline for file: %s", manifest_path)
    if not manifest_path.is_file():
        logger.error("Specified manifest file does not exist: %s", manifest_path)
        return None

    raw_yaml_str = manifest_path.read_text(encoding="utf-8")
    engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    try:
        async with async_session() as session:
            graph = await compile_and_register_manifest(
                raw_yaml_str, session, settings=settings_override
            )
            logger.info("REGISTRATION SUCCESSFUL: Persisted Definition UUID: %s", graph.manifest_id)
            return str(graph.manifest_id)
    except PipelineCompilationError as err:
        logger.error("PIPELINE COMPILATION FAILURE at [%s]: %s", err.stage, err)
        return None
    except Exception as err:
        logger.error("UNEXPECTED REGISTRATION ERROR: %s", err)
        return None
    finally:
        await engine.dispose()


def bootstrap() -> CompilerSettings:
    """Application bootstrap routine verifying runtime integrity before starting engine."""
    try:
        active_settings = CompilerSettings()
        return active_settings.validate_runtime()
    except ConfigurationError as err:
        print(f"Bootstrap Failure: {err}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """CLI application main entry point."""
    active_settings = bootstrap()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(
        JSONFormatter(
            service_name="meta-compiler",
            environment=active_settings.environment,
        )
    )
    logging.basicConfig(
        level=logging.INFO,
        handlers=[stream_handler],
        force=True,
    )
    default_db_url = active_settings.get_db_url_string()
    parser = build_cli_parser(default_db_url=default_db_url)
    args = parser.parse_args()

    if args.command == "validate":
        success = run_dry_run_validation(args.file, settings_override=active_settings)
        sys.exit(0 if success else 1)
    elif args.command == "register":
        if not args.db_url:
            logger.error("Database URL is required for registration.")
            sys.exit(1)

        # A --db-url override must still satisfy production policy.
        if args.db_url != default_db_url and active_settings.environment == "production":
            logger.error(
                "Database URL override is not permitted in the '%s' environment; "
                "configure 'META_COMPILER_DB_CONNECTION_URL' instead.",
                active_settings.environment,
            )
            sys.exit(1)

        definition_id = asyncio.run(
            run_registration(args.file, args.db_url, settings_override=active_settings)
        )
        sys.exit(0 if definition_id else 1)


if __name__ == "__main__":
    main()
