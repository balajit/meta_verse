from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

import yaml

from meta_service_generator.exceptions import ManifestValidationError
from meta_service_generator.local_telemetry import get_logger
from meta_telemetry import get_tracer, trace_span

logger = get_logger("meta_service_generator.manifest.loader")
tracer = get_tracer("meta_service_generator.manifest.loader")


class ManifestLoader:
    """Safely loads JSON/YAML manifests with bounded input size."""

    DEFAULT_MAX_MANIFEST_BYTES: Final[int] = 5 * 1024 * 1024
    DEFAULT_MAX_MANIFEST_DEPTH: Final[int] = 64
    DEFAULT_MAX_MANIFEST_NODES: Final[int] = 100_000

    _JSON_SUFFIXES: Final[frozenset[str]] = frozenset({".json"})
    _YAML_SUFFIXES: Final[frozenset[str]] = frozenset(
        {".yaml", ".yml"}
    )

    def __init__(
        self,
        max_manifest_bytes: int = DEFAULT_MAX_MANIFEST_BYTES,
        max_manifest_depth: int = DEFAULT_MAX_MANIFEST_DEPTH,
        max_manifest_nodes: int = DEFAULT_MAX_MANIFEST_NODES,
    ) -> None:
        if max_manifest_bytes <= 0:
            raise ValueError(
                "max_manifest_bytes must be greater than zero."
            )

        if max_manifest_depth <= 0:
            raise ValueError(
                "max_manifest_depth must be greater than zero."
            )

        if max_manifest_nodes <= 0:
            raise ValueError(
                "max_manifest_nodes must be greater than zero."
            )

        self._max_manifest_bytes = max_manifest_bytes
        self._max_manifest_depth = max_manifest_depth
        self._max_manifest_nodes = max_manifest_nodes

    @trace_span("manifest.loader.load_from_path")
    def load_from_path(
        self,
        path: Path,
    ) -> dict[str, Any]:
        if not isinstance(path, Path):
            raise TypeError(
                f"path must be pathlib.Path, got {type(path).__name__}."
            )

        try:
            if not path.exists():
                raise ManifestValidationError(
                    message=f"Manifest file not found at path: {path}",
                    location=str(path),
                    error_code="ERR_MANIFEST_FILE_NOT_FOUND",
                    suggested_resolution=(
                        "Verify the --manifest option path points "
                        "to a valid file."
                    ),
                )

            if not path.is_file():
                raise ManifestValidationError(
                    message=(
                        f"Manifest path is not a regular file: {path}"
                    ),
                    location=str(path),
                    error_code="ERR_MANIFEST_PATH_NOT_FILE",
                    suggested_resolution=(
                        "Provide a path to a regular manifest file."
                    ),
                )

            file_size = path.stat().st_size

            if file_size > self._max_manifest_bytes:
                raise ManifestValidationError(
                    message=(
                        f"Manifest file '{path}' is {file_size} bytes, "
                        f"exceeding the maximum allowed size of "
                        f"{self._max_manifest_bytes} bytes."
                    ),
                    location=str(path),
                    error_code="ERR_MANIFEST_TOO_LARGE",
                    suggested_resolution=(
                        "Reduce the manifest size or increase the "
                        "configured limit explicitly."
                    ),
                )

            content = path.read_text(
                encoding="utf-8",
            )

        except ManifestValidationError:
            raise

        except (OSError, UnicodeError) as err:
            raise ManifestValidationError(
                message=(
                    f"Failed to read manifest file at {path}: {err}"
                ),
                location=str(path),
                error_code="ERR_MANIFEST_READ_FAILED",
                suggested_resolution=(
                    "Check file encoding, permissions, and filesystem "
                    "accessibility."
                ),
                details={
                    "exception_type": type(err).__name__,
                },
            ) from err

        return self.load_from_str(
            content=content,
            source_label=str(path),
            suffix=path.suffix.lower(),
        )

    @trace_span("manifest.loader.load_from_str")
    def load_from_str(
        self,
        content: str,
        source_label: str = "inline_string",
        suffix: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(content, str):
            raise TypeError(
                f"content must be str, got {type(content).__name__}."
            )

        if not content.strip():
            raise ManifestValidationError(
                message="Manifest content is empty.",
                location=source_label,
                error_code="ERR_MANIFEST_EMPTY",
                suggested_resolution=(
                    "Provide a non-empty YAML or JSON service specification."
                ),
            )

        content_size = len(
            content.encode("utf-8")
        )

        if content_size > self._max_manifest_bytes:
            raise ManifestValidationError(
                message=(
                    "Manifest content exceeds the maximum allowed size."
                ),
                location=source_label,
                error_code="ERR_MANIFEST_TOO_LARGE",
                suggested_resolution=(
                    "Reduce the manifest size or increase the "
                    "configured limit explicitly."
                ),
                details={
                    "content_bytes": content_size,
                    "max_manifest_bytes": self._max_manifest_bytes,
                },
            )

        normalized_suffix = (
            suffix.lower()
            if suffix
            else None
        )

        if normalized_suffix in self._JSON_SUFFIXES:
            parsed = self._parse_json(
                content,
                source_label,
            )
        elif normalized_suffix in self._YAML_SUFFIXES:
            parsed = self._parse_yaml(
                content,
                source_label,
            )
        else:
            try:
                parsed = self._parse_json(
                    content,
                    source_label,
                )
            except ManifestValidationError:
                parsed = self._parse_yaml(
                    content,
                    source_label,
                )

        self._validate_structure_limits(
            parsed,
            source_label,
        )

        logger.info(
            "Manifest loaded successfully.",
            extra={
                "event_type": "manifest.loaded",
                "source_label": source_label,
                "content_bytes": content_size,
            },
        )

        return parsed

    @staticmethod
    def _parse_json(
        content: str,
        source_label: str,
    ) -> dict[str, Any]:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as err:
            raise ManifestValidationError(
                message=(
                    f"Failed to parse JSON manifest: {err.msg} "
                    f"at line {err.lineno}, column {err.colno}."
                ),
                location=source_label,
                error_code="ERR_MANIFEST_SYNTAX_INVALID",
                suggested_resolution=(
                    "Correct JSON syntax or use a YAML manifest extension."
                ),
                details={
                    "line": err.lineno,
                    "column": err.colno,
                },
            ) from err

        return ManifestLoader._require_mapping(
            parsed,
            source_label,
        )

    @staticmethod
    def _parse_yaml(
        content: str,
        source_label: str,
    ) -> dict[str, Any]:
        try:
            parsed = yaml.safe_load(content)
        except yaml.YAMLError as err:
            raise ManifestValidationError(
                message=f"Failed to parse manifest syntax: {err}",
                location=source_label,
                error_code="ERR_MANIFEST_SYNTAX_INVALID",
                suggested_resolution=(
                    "Correct syntax errors in YAML/JSON document structure."
                ),
                details={
                    "exception_type": type(err).__name__,
                },
            ) from err

        return ManifestLoader._require_mapping(
            parsed,
            source_label,
        )

    @staticmethod
    def _require_mapping(
        parsed: Any,
        source_label: str,
    ) -> dict[str, Any]:
        if not isinstance(parsed, dict):
            raise ManifestValidationError(
                message=(
                    "Manifest structure must resolve to a key-value "
                    f"dictionary, got {type(parsed).__name__}."
                ),
                location=source_label,
                error_code="ERR_MANIFEST_TOP_LEVEL_INVALID",
                suggested_resolution=(
                    "Ensure top-level document structure is an "
                    "object/dictionary."
                ),
            )

        return parsed

    def _validate_structure_limits(
        self,
        value: Any,
        source_label: str,
    ) -> None:
        """
        Validate manifest structural complexity without recursive Python calls.

        An explicit stack prevents deeply nested user-controlled manifests
        from consuming the Python interpreter's call stack.
        """
        active: set[int] = set()
        visited_nodes = 0

        stack: list[
            tuple[str, Any, int, bool]
        ] = [
            ("root", value, 0, False)
        ]

        while stack:
            location, node, depth, exiting = stack.pop()

            if exiting:
                if isinstance(node, (dict, list)):
                    active.discard(id(node))
                continue

            if depth > self._max_manifest_depth:
                raise ManifestValidationError(
                    message=(
                        "Manifest nesting exceeds maximum depth of "
                        f"{self._max_manifest_depth}."
                    ),
                    location=source_label,
                    error_code="ERR_MANIFEST_MAX_DEPTH",
                    suggested_resolution=(
                        "Reduce manifest nesting depth."
                    ),
                    details={
                        "depth": depth,
                        "max_manifest_depth": (
                            self._max_manifest_depth
                        ),
                    },
                )

            visited_nodes += 1

            if visited_nodes > self._max_manifest_nodes:
                raise ManifestValidationError(
                    message=(
                        "Manifest structure exceeds maximum node count "
                        f"of {self._max_manifest_nodes}."
                    ),
                    location=source_label,
                    error_code="ERR_MANIFEST_MAX_NODES",
                    suggested_resolution=(
                        "Reduce manifest structural complexity."
                    ),
                    details={
                        "visited_nodes": visited_nodes,
                        "max_manifest_nodes": (
                            self._max_manifest_nodes
                        ),
                    },
                )

            if not isinstance(node, (dict, list)):
                continue

            node_id = id(node)

            if node_id in active:
                raise ManifestValidationError(
                    message=(
                        "Manifest contains a recursive YAML "
                        "alias/reference cycle."
                    ),
                    location=source_label,
                    error_code="ERR_MANIFEST_RECURSIVE_STRUCTURE",
                    suggested_resolution=(
                        "Remove recursive YAML aliases from the manifest."
                    ),
                )

            active.add(node_id)

            stack.append(
                (
                    location,
                    node,
                    depth,
                    True,
                )
            )

            if isinstance(node, dict):
                children = list(
                    node.items()
                )

                for key, child in reversed(children):
                    stack.append(
                        (
                            f"{location}.{key}",
                            child,
                            depth + 1,
                            False,
                        )
                    )
                    stack.append(
                        (
                            f"{location}.<key>",
                            key,
                            depth + 1,
                            False,
                        )
                    )
            else:
                for index in range(
                    len(node) - 1,
                    -1,
                    -1,
                ):
                    stack.append(
                        (
                            f"{location}[{index}]",
                            node[index],
                            depth + 1,
                            False,
                        )
                    )