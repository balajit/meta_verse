"""Common helper utilities and compiled artifact containers for the MetaCompiler engine."""

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger("meta_compiler.stages.common")


def generate_model_source_code(models: dict[str, type[BaseModel]]) -> str:
    """Generates clean, executable Python source code for dynamic Pydantic models.

    Delegates to the datamodel-code-generator backed implementation in
    :mod:`meta_compiler.stages.model_compiler` so that schema composition,
    constraints, and annotations are handled by a single, canonical generator.
    """
    from meta_compiler.stages.model_compiler import (
        generate_model_source_code as generate_from_models,
    )

    return generate_from_models(models)


class CompiledArtifacts:
    """Container holding compiled manifest specifications, topology graphs, and DB payloads."""

    def __init__(
        self,
        manifest_spec: Any,
        execution_order: Any,
        db_payload: dict[str, Any],
        compiled_models: dict[str, type[BaseModel]] | None = None,
    ) -> None:
        self.manifest_spec = manifest_spec
        self.execution_order = execution_order
        self.db_payload = db_payload
        self.compiled_models = compiled_models or {}

    def write_to_disk(self, target_dir: Path) -> list[Path]:
        """Safely writes compiled artifacts and dynamic source code to disk."""
        resolved_dir = target_dir.resolve()
        resolved_dir.mkdir(parents=True, exist_ok=True)
        written_files: list[Path] = []

        if self.manifest_spec:
            blueprint_file = resolved_dir / "dag_blueprint.json"
            blueprint_data = (
                self.manifest_spec.model_dump_json(indent=2)
                if hasattr(self.manifest_spec, "model_dump_json")
                else json.dumps(self.manifest_spec, indent=2)
            )
            blueprint_file.write_text(blueprint_data, encoding="utf-8")
            written_files.append(blueprint_file)

        if self.compiled_models:
            models_file = resolved_dir / "domain_models.py"
            source_code = generate_model_source_code(self.compiled_models)
            models_file.write_text(source_code, encoding="utf-8")
            written_files.append(models_file)

        logger.info(
            "Wrote %d compiled artifacts to disk at '%s'",
            len(written_files),
            resolved_dir,
            extra={
                "event": "artifacts.disk_write",
                "target_dir": str(resolved_dir),
                "count": len(written_files),
            },
        )
        return written_files
