from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class DirectModeExecutionError(Exception):
    """Raised when local direct-mode compilation fails."""
    pass


class DirectModeRunner:
    @staticmethod
    def execute_local_build(spec_path: Path, output_dir: Path) -> bool:
        logger.info("direct_mode_execution_started", spec_file=str(spec_path), output=str(output_dir))
        if not spec_path.exists():
            logger.error("spec_file_not_found", path=str(spec_path))
            raise DirectModeExecutionError(f"Specification file not found: {spec_path}")

        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("direct_mode_execution_completed", output_dir=str(output_dir))
        return True