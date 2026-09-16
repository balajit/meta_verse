from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from meta_service_generator.exceptions import CodeGenerationError
from meta_service_generator.local_telemetry import get_logger
from meta_telemetry import get_tracer, trace_span
from pydantic import BaseModel, ConfigDict, Field


logger = get_logger("meta_service_generator.generation.artifacts")
tracer = get_tracer("meta_service_generator.generation.artifacts")

DEFAULT_MAX_TEMPLATE_OUTPUT_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_TOTAL_GENERATED_BYTES = 100 * 1024 * 1024
DEFAULT_MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_ARTIFACT_COUNT = 2_000


class Artifact(BaseModel):
    """
    Immutable representation of a synthesized file artifact.
    """

    relative_path: str
    absolute_path: str
    content_hash: str
    size_bytes: int
    is_executable: bool = False
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )


class ArtifactWriter:
    """
    Safely writes file artifacts with path traversal protection and atomic file operations.
    """

    def __init__(
        self,
        target_dir: Path | str,
        *,
        max_artifact_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES,
        max_total_generated_bytes: int = DEFAULT_MAX_TOTAL_GENERATED_BYTES,
        max_artifact_count: int = DEFAULT_MAX_ARTIFACT_COUNT,
    ) -> None:
        if max_artifact_bytes <= 0:
            raise ValueError("max_artifact_bytes must be greater than zero.")

        if max_total_generated_bytes <= 0:
            raise ValueError(
                "max_total_generated_bytes must be greater than zero."
            )

        if max_artifact_count <= 0:
            raise ValueError("max_artifact_count must be greater than zero.")

        if max_artifact_bytes > max_total_generated_bytes:
            raise ValueError(
                "max_artifact_bytes cannot exceed max_total_generated_bytes."
            )

        try:
            resolved_target = Path(target_dir).expanduser().resolve()

            if resolved_target.exists() and not resolved_target.is_dir():
                raise CodeGenerationError(
                    message=(
                        f"Artifact target path exists but is not a directory: "
                        f"'{resolved_target}'."
                    ),
                    location=str(resolved_target),
                    error_code="ERR_ARTIFACT_TARGET_NOT_DIRECTORY",
                    suggested_resolution=(
                        "Choose a directory that can contain generated artifacts."
                    ),
                )

            resolved_target.mkdir(parents=True, exist_ok=True)

            self.target_dir = resolved_target
            self.max_artifact_bytes = max_artifact_bytes
            self.max_total_generated_bytes = max_total_generated_bytes
            self.max_artifact_count = max_artifact_count

            self._written_sizes: dict[str, int] = {}
            self._total_generated_bytes = 0
            self._lock = Lock()

            logger.info(
                "Artifact writer initialized.",
                extra={
                    "event_type": "artifact_writer_initialized",
                    "target_dir": str(resolved_target),
                    "max_artifact_bytes": max_artifact_bytes,
                    "max_total_generated_bytes": max_total_generated_bytes,
                    "max_artifact_count": max_artifact_count,
                },
            )

        except CodeGenerationError:
            raise

        except OSError as err:
            raise CodeGenerationError(
                message=(
                    f"Failed to initialize artifact target directory "
                    f"'{target_dir}': {err}"
                ),
                location=str(target_dir),
                error_code="ERR_ARTIFACT_TARGET_INITIALIZATION_FAILED",
                suggested_resolution=(
                    "Verify filesystem permissions and target-directory availability."
                ),
            ) from err

    @trace_span("generation.artifacts.write_artifact")
    def write_artifact(
        self,
        relative_path: Path | str,
        content: str,
        is_executable: bool = False,
    ) -> Artifact:
        """
        Atomically writes file content to target destination after validating path bounds.
        """
        if not isinstance(content, str):
            raise CodeGenerationError(
                message=(
                    f"Artifact content must be str, got "
                    f"{type(content).__name__}."
                ),
                location=str(relative_path),
                error_code="ERR_ARTIFACT_CONTENT_TYPE",
                suggested_resolution=(
                    "Pass generated source content as a UTF-8 Python string."
                ),
            )

        try:
            rel_path = Path(relative_path)

            if rel_path.is_absolute():
                raise CodeGenerationError(
                    message=(
                        f"Absolute artifact path is forbidden: "
                        f"'{relative_path}'."
                    ),
                    location=str(relative_path),
                    error_code="ERR_ARTIFACT_ABSOLUTE_PATH",
                    suggested_resolution=(
                        "Provide an artifact path relative to the generation target."
                    ),
                )

            if not str(rel_path) or str(rel_path) == ".":
                raise CodeGenerationError(
                    message="Artifact relative path cannot be empty.",
                    location=str(relative_path),
                    error_code="ERR_ARTIFACT_EMPTY_PATH",
                    suggested_resolution=(
                        "Provide a concrete relative artifact filename."
                    ),
                )

            destination = (self.target_dir / rel_path).resolve()

            try:
                destination.relative_to(self.target_dir)
            except ValueError as err:
                raise CodeGenerationError(
                    message=(
                        f"Path traversal attempt detected: '{relative_path}' "
                        "resolves outside target directory."
                    ),
                    location=str(relative_path),
                    error_code="ERR_ARTIFACT_PATH_TRAVERSAL",
                    suggested_resolution=(
                        "Ensure target paths are relative and contained "
                        "within target_dir."
                    ),
                ) from err

            with self._lock:
                if destination.exists() and destination.is_symlink():
                    raise CodeGenerationError(
                        message=(
                            "Refusing to overwrite symlink artifact destination: "
                            f"'{destination}'."
                        ),
                        location=str(relative_path),
                        error_code="ERR_ARTIFACT_SYMLINK_DESTINATION",
                        suggested_resolution=(
                            "Remove the symlink or generate into a clean target directory."
                        ),
                    )

                destination.parent.mkdir(parents=True, exist_ok=True)

                current = destination.parent
                while current != self.target_dir:
                    if current.is_symlink():
                        raise CodeGenerationError(
                            message=(
                                f"Artifact parent directory is a symlink: "
                                f"'{current}'."
                            ),
                            location=str(relative_path),
                            error_code="ERR_ARTIFACT_SYMLINK_PARENT",
                            suggested_resolution=(
                                "Generate artifacts into a directory tree without "
                                "symbolic-link components."
                            ),
                        )

                    current = current.parent

                content_bytes = content.encode("utf-8")
                content_size = len(content_bytes)

                if content_size > self.max_artifact_bytes:
                    raise CodeGenerationError(
                        message=(
                            f"Artifact '{destination.name}' exceeded the maximum "
                            f"artifact size of {self.max_artifact_bytes} bytes."
                        ),
                        location=str(destination),
                        error_code="ERR_ARTIFACT_OUTPUT_TOO_LARGE",
                        suggested_resolution=(
                            "Reduce generated template expansion or increase the "
                            "explicit generator resource limit."
                        ),
                    )

                relative_key = rel_path.as_posix()
                previous_size = self._written_sizes.get(relative_key, 0)

                projected_total = (
                    self._total_generated_bytes
                    - previous_size
                    + content_size
                )

                projected_count = len(self._written_sizes) + (
                    0 if relative_key in self._written_sizes else 1
                )

                if projected_count > self.max_artifact_count:
                    raise CodeGenerationError(
                        message=(
                            "Generation would exceed the maximum artifact count "
                            f"of {self.max_artifact_count}."
                        ),
                        location=str(self.target_dir),
                        error_code="ERR_ARTIFACT_COUNT_LIMIT_EXCEEDED",
                        suggested_resolution=(
                            "Reduce the generated artifact set or increase the "
                            "explicit generator resource limit."
                        ),
                    )

                if projected_total > self.max_total_generated_bytes:
                    raise CodeGenerationError(
                        message=(
                            "Generation would exceed the maximum total generated "
                            f"size of {self.max_total_generated_bytes} bytes."
                        ),
                        location=str(self.target_dir),
                        error_code="ERR_TOTAL_GENERATED_OUTPUT_TOO_LARGE",
                        suggested_resolution=(
                            "Reduce generated output or increase the explicit "
                            "generator resource limit."
                        ),
                    )

                digest = hashlib.sha256(content_bytes).hexdigest()
                temp_path: Path | None = None

                try:
                    with tempfile.NamedTemporaryFile(
                        mode="wb",
                        dir=destination.parent,
                        prefix=f".{destination.name}.",
                        suffix=".tmp",
                        delete=False,
                    ) as temp_file:
                        temp_path = Path(temp_file.name)
                        temp_file.write(content_bytes)
                        temp_file.flush()
                        os.fsync(temp_file.fileno())

                    if is_executable:
                        current_permissions = stat.S_IMODE(
                            os.stat(
                                temp_path,
                                follow_symlinks=False,
                            ).st_mode
                        )

                        os.chmod(
                            temp_path,
                            current_permissions
                            | stat.S_IXUSR
                            | stat.S_IXGRP
                            | stat.S_IXOTH,
                        )

                    temp_path.replace(destination)

                    try:
                        directory_fd = os.open(
                            destination.parent,
                            os.O_RDONLY
                            | getattr(os, "O_DIRECTORY", 0),
                        )

                        try:
                            os.fsync(directory_fd)
                        finally:
                            os.close(directory_fd)

                    except OSError as err:
                        logger.warning(
                            "Artifact directory fsync was unavailable.",
                            extra={
                                "event_type": (
                                    "artifact_directory_fsync_unavailable"
                                ),
                                "artifact": relative_key,
                                "error_type": type(err).__name__,
                            },
                        )

                    self._written_sizes[relative_key] = content_size
                    self._total_generated_bytes = projected_total

                    artifact = Artifact(
                        relative_path=relative_key,
                        absolute_path=str(destination),
                        content_hash=digest,
                        size_bytes=content_size,
                        is_executable=is_executable,
                    )

                    logger.info(
                        "Artifact written successfully.",
                        extra={
                            "event_type": "artifact_written",
                            "artifact": relative_key,
                            "size_bytes": content_size,
                            "content_hash": digest,
                            "artifact_count": len(self._written_sizes),
                            "total_generated_bytes": (
                                self._total_generated_bytes
                            ),
                        },
                    )

                    return artifact

                finally:
                    if temp_path is not None and temp_path.exists():
                        try:
                            temp_path.unlink()
                        except OSError as err:
                            logger.warning(
                                "Failed to remove temporary artifact file.",
                                extra={
                                    "event_type": "artifact_temp_cleanup_failed",
                                    "artifact": relative_key,
                                    "temp_path": str(temp_path),
                                    "error_type": type(err).__name__,
                                },
                            )

        except CodeGenerationError:
            raise

        except UnicodeEncodeError as err:
            raise CodeGenerationError(
                message=(
                    f"Artifact content cannot be encoded as UTF-8: {err}"
                ),
                location=str(relative_path),
                error_code="ERR_ARTIFACT_ENCODING_FAILED",
                suggested_resolution=(
                    "Ensure generated source contains valid Unicode text."
                ),
            ) from err

        except OSError as err:
            raise CodeGenerationError(
                message=f"Failed to write artifact '{relative_path}': {err}",
                location=str(relative_path),
                error_code="ERR_ARTIFACT_WRITE_FAILED",
                suggested_resolution=(
                    "Verify filesystem write permissions and available disk space."
                ),
            ) from err