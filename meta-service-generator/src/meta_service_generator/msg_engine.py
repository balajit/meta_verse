from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from meta_service_generator.config import load_settings
from meta_service_generator.exceptions import (
    CodeGenerationError,
    GeneratorError,
    ManifestValidationError,
)
from meta_service_generator.generation.pipeline import CodeGenerationPipeline
from meta_service_generator.ir.builder import IRBuilder
from meta_service_generator.ir.model import ServiceIR
from meta_service_generator.local_telemetry import get_logger
from meta_service_generator.manifest.loader import ManifestLoader
from meta_service_generator.manifest.schema import ManifestSpec
from meta_service_generator.manifest.validator import ManifestValidator
from meta_service_generator.verification.runner import VerificationRunner

logger = get_logger("meta_service_generator.msg_engine")


def _to_service_ir(manifest_source: Any) -> ServiceIR:
    """Converts manifest dictionary, ManifestSpec, or ServiceIR into ServiceIR."""
    if isinstance(manifest_source, ServiceIR):
        return manifest_source

    if isinstance(manifest_source, ManifestSpec):
        return IRBuilder().build(manifest_source)

    if isinstance(manifest_source, Mapping):
        raw_manifest: dict[str, Any] = dict(manifest_source)
    else:
        model_dump = getattr(manifest_source, "model_dump", None)

        if not callable(model_dump):
            raise ManifestValidationError(
                message=(
                    "Manifest source must be a ServiceIR, ManifestSpec, "
                    "mapping, or Pydantic model exposing model_dump()."
                ),
                location="manifest_source",
                error_code="ERR_MANIFEST_SOURCE_INVALID",
                suggested_resolution="Provide a validated manifest object or mapping.",
            )

        dumped = model_dump()

        if not isinstance(dumped, Mapping):
            raise ManifestValidationError(
                message="Manifest model_dump() did not return a mapping.",
                location="manifest_source",
                error_code="ERR_MANIFEST_SOURCE_INVALID",
                suggested_resolution="Provide a Pydantic model whose model_dump() returns manifest data.",
            )

        raw_manifest = dict(dumped)

    validator = ManifestValidator()

    service_name = raw_manifest.get("service_name") or raw_manifest.get("name")
    version = raw_manifest.get("version", "1.0.0")

    raw_entities = (
        raw_manifest.get("entities")
        if raw_manifest.get("entities") is not None
        else raw_manifest.get("models")
    )

    sanitized_manifest: dict[str, Any] = {
        "version": version,
        "service_name": service_name,
        "entities": raw_entities,
        "business_rules": raw_manifest.get("business_rules", []),
        "workflows": raw_manifest.get("workflows", []),
        "policies": raw_manifest.get("policies", []),
    }

    if not isinstance(service_name, str):
        raise ManifestValidationError(
            message="Manifest is missing required service_name.",
            location="manifest#/service_name",
            error_code="ERR_MANIFEST_SERVICE_NAME_MISSING",
            suggested_resolution="Provide a valid service_name field.",
        )

    if not isinstance(raw_entities, list):
        raise ManifestValidationError(
            message="Manifest is missing a valid entities collection.",
            location="manifest#/entities",
            error_code="ERR_MANIFEST_ENTITIES_MISSING",
            suggested_resolution="Provide an entities array in the manifest.",
        )

    spec = validator.validate(sanitized_manifest, source_label="manifest")
    return IRBuilder().build(spec)


def _find_workspace_package(target_dir: Path, package_name: str) -> Path | None:
    """Traverses parent directories to locate local sibling workspace packages."""
    normalized_target = package_name.replace("_", "-")
    current = target_dir.resolve()

    for _ in range(5):
        parent = current.parent
        if parent == current:
            break

        try:
            candidates = tuple(parent.iterdir())
        except OSError as err:
            logger.warning(
                "Unable to inspect workspace parent directory.",
                extra={
                    "event_type": "workspace.package_lookup_failed",
                    "directory": str(parent),
                    "package_name": package_name,
                    "exception_type": type(err).__name__,
                },
            )
            current = parent
            continue

        for candidate in candidates:
            if not candidate.is_dir():
                continue

            if candidate.name.replace("_", "-") != normalized_target:
                continue

            if (candidate / "pyproject.toml").exists():
                return candidate.resolve()

        current = parent

    return None


def _patch_pyproject_sources(target_dir: Path) -> None:
    """Injects local workspace dependencies directly under [tool.uv.sources] in pyproject.toml."""
    pyproject_path = target_dir / "pyproject.toml"

    if not pyproject_path.exists():
        return

    try:
        content = pyproject_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as err:
        raise CodeGenerationError(
            message=f"Failed to read generated pyproject.toml: {err}",
            location=str(pyproject_path),
            error_code="ERR_GENERATED_PYPROJECT_READ_FAILED",
            suggested_resolution="Verify the generated project filesystem and encoding.",
            details={"exception_type": type(err).__name__},
        ) from err

    dependencies_to_check = (
        "meta-compiler",
        "meta-telemetry",
        "meta-polymorph",
        "meta-builder-brain",
    )

    sources_to_add: dict[str, str] = {}

    for dependency in dependencies_to_check:
        dependency_path = _find_workspace_package(target_dir, dependency)
        if dependency_path is not None:
            sources_to_add[dependency] = str(dependency_path)

    if not sources_to_add:
        return

    lines = content.splitlines()
    uv_sources_index = -1

    for index, line in enumerate(lines):
        if line.strip() == "[tool.uv.sources]":
            uv_sources_index = index
            break

    if uv_sources_index != -1:
        inserted: list[str] = []
        for package_name, package_path in sources_to_add.items():
            assignment_exists = any(
                line.strip().startswith(f"{package_name} =")
                or line.strip().startswith(f'"{package_name}" =')
                for line in lines
            )
            if not assignment_exists:
                inserted.append(
                    f'{package_name} = {{ path = "{package_path}", editable = true }}'
                )

        if inserted:
            lines = (
                lines[: uv_sources_index + 1]
                + inserted
                + lines[uv_sources_index + 1 :]
            )
            try:
                pyproject_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            except (OSError, UnicodeError) as err:
                raise CodeGenerationError(
                    message=f"Failed to update generated pyproject.toml: {err}",
                    location=str(pyproject_path),
                    error_code="ERR_GENERATED_PYPROJECT_WRITE_FAILED",
                    suggested_resolution="Verify write permissions for the generated project directory.",
                    details={"exception_type": type(err).__name__},
                ) from err
        return

    inserted = ["", "[tool.uv.sources]"]
    for package_name, package_path in sources_to_add.items():
        inserted.append(
            f'{package_name} = {{ path = "{package_path}", editable = true }}'
        )

    try:
        pyproject_path.write_text(
            "\n".join(lines) + "\n" + "\n".join(inserted) + "\n",
            encoding="utf-8",
        )
    except (OSError, UnicodeError) as err:
        raise CodeGenerationError(
            message=f"Failed to append [tool.uv.sources] to generated pyproject.toml: {err}",
            location=str(pyproject_path),
            error_code="ERR_GENERATED_PYPROJECT_WRITE_FAILED",
            suggested_resolution="Verify write permissions for the generated project directory.",
            details={"exception_type": type(err).__name__},
        ) from err


def _resolve_verification_result(
    runner: VerificationRunner,
    project_root: Path,
    package_name: str,
) -> Any:
    """
    Execute the verification runner synchronously, resolving coroutines if the
    runner implementation utilizes async contracts.
    """
    result = runner.run_pipeline(
        project_root=project_root,
        package_name=package_name,
    )

    if asyncio.iscoroutine(result):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            return loop.run_until_complete(result)
        return asyncio.run(result)

    return result


class MetaServiceGeneratorEngine:
    """
    High-level engine wrapper for meta-service-generator designed for seamless
    integration into application builder platforms with minimal configuration effort.
    """

    def __init__(
        self,
        default_output_dir: str | Path = "generated_service",
    ) -> None:
        self.default_output_dir = Path(default_output_dir).expanduser().resolve()
        self.loader = ManifestLoader()
        self.validator = ManifestValidator()

    def generate_service(
        self,
        manifest_source: str | Path | dict[str, Any] | ManifestSpec | ServiceIR,
        output_dir: str | Path | None = None,
        verify: bool = True,
    ) -> dict[str, Any]:
        """Validates manifest, executes code generation pipeline, and runs verification."""
        target_dir = (
            Path(output_dir) if output_dir is not None else self.default_output_dir
        ).expanduser().resolve()

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            raise CodeGenerationError(
                message=f"Unable to create generation target directory: {err}",
                location=str(target_dir),
                error_code="ERR_GENERATION_TARGET_CREATE_FAILED",
                suggested_resolution="Verify the target directory path and filesystem permissions.",
                details={"exception_type": type(err).__name__},
            ) from err

        logger.info(
            "Starting service generation pipeline.",
            extra={
                "event_type": "generation.started",
                "output_directory": str(target_dir),
                "verify": verify,
            },
        )

        load_settings(target_emission_path=target_dir, debug=verify)

        if isinstance(manifest_source, (str, Path)):
            manifest_path = Path(manifest_source).expanduser().resolve()
            manifest_data = self.loader.load_from_path(manifest_path)
            service_ir = _to_service_ir(manifest_data)
        else:
            service_ir = _to_service_ir(manifest_source)

        logger.info(
            "Manifest resolved into ServiceIR.",
            extra={
                "event_type": "generation.manifest_resolved",
                "service_name": str(service_ir.service_name),
            },
        )

        try:
            pipeline = CodeGenerationPipeline()
            emitted_paths = pipeline.execute(
                service_ir=service_ir,
                target_dir=target_dir,
            )

            logger.info(
                "Generation pipeline emitted artifacts.",
                extra={
                    "event_type": "generation.artifacts_emitted",
                    "output_directory": str(target_dir),
                    "emitted_file_count": len(emitted_paths),
                },
            )
        except GeneratorError:
            raise
        except Exception as err:
            logger.error(
                "Generation pipeline execution failed.",
                extra={
                    "event_type": "generation.pipeline_failed",
                    "exception_type": type(err).__name__,
                },
            )
            raise CodeGenerationError(
                message=f"Generation pipeline failed: {err}",
                location=str(target_dir),
                error_code="ERR_GENERATION_PIPELINE_FAILED",
                suggested_resolution="Inspect generation-stage diagnostics and generated artifact state.",
                details={"exception_type": type(err).__name__},
            ) from err

        _patch_pyproject_sources(target_dir)

        verification_results: dict[str, Any] = {}

        if verify:
            runner = VerificationRunner()
            result = _resolve_verification_result(
                runner=runner,
                project_root=target_dir,
                package_name=str(service_ir.service_name),
            )

            if hasattr(result, "model_dump"):
                verification_results = result.model_dump()
            elif isinstance(result, dict):
                verification_results = result
            else:
                verification_results = {"result": result}

        logger.info(
            "Service generation completed successfully.",
            extra={
                "event_type": "generation.completed",
                "output_directory": str(target_dir),
                "emitted_file_count": len(emitted_paths),
                "verification_enabled": verify,
            },
        )

        return {
            "status": "success",
            "output_directory": str(target_dir),
            "emitted_files": [str(path) for path in emitted_paths],
            "verification": verification_results,
        }