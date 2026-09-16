"""
Multi-Tier Payload Limits Engine (Payload Guard).
Enforces strict raw byte caps, maximum nesting depth checks, AST node allocation thresholds, and collection cardinality bounds.
"""

from __future__ import annotations

import ast
import json
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field

logger = structlog.getLogger("meta_application_builder.compiler_engine.validation.payload_guard")


class PayloadGuardConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    max_raw_bytes: int = Field(default=1_048_576, description="Maximum allowed payload size in bytes (1MB)")
    max_nesting_depth: int = Field(default=20, description="Maximum allowed nesting depth for dictionaries/lists")
    max_collection_cardinality: int = Field(default=1000, description="Maximum items allowed in a single dict or list")
    max_ast_nodes: int = Field(default=5000, description="Maximum allowed AST nodes during parsing")


class PayloadViolationError(Exception):
    """Raised when payload dimensions exceed security bounds."""
    pass


class PayloadGuard:
    """Validates raw payloads and syntax trees against denial-of-service (DoS) thresholds."""

    def __init__(self, config: PayloadGuardConfig | None = None) -> None:
        self.config = config or PayloadGuardConfig()

    def inspect_bytes(self, raw_bytes: bytes) -> None:
        if len(raw_bytes) > self.config.max_raw_bytes:
            raise PayloadViolationError(
                f"Payload size {len(raw_bytes)} bytes exceeds maximum allowed limit of {self.config.max_raw_bytes} bytes."
            )

    def _check_structure(self, obj: Any, current_depth: int = 0) -> None:
        if current_depth > self.config.max_nesting_depth:
            raise PayloadViolationError(
                f"Payload nesting depth {current_depth} exceeds maximum allowed limit of {self.config.max_nesting_depth}."
            )

        if isinstance(obj, dict):
            if len(obj) > self.config.max_collection_cardinality:
                raise PayloadViolationError(
                    f"Dictionary key count {len(obj)} exceeds maximum collection cardinality of {self.config.max_collection_cardinality}."
                )
            for k, v in obj.items():
                self._check_structure(k, current_depth + 1)
                self._check_structure(v, current_depth + 1)
        elif isinstance(obj, list | tuple | set):
            if len(obj) > self.config.max_collection_cardinality:
                raise PayloadViolationError(
                    f"Collection element count {len(obj)} exceeds maximum collection cardinality of {self.config.max_collection_cardinality}."
                )
            for item in obj:
                self._check_structure(item, current_depth + 1)

    def inspect_json_payload(self, raw_bytes: bytes) -> Any:
        self.inspect_bytes(raw_bytes)
        try:
            parsed = json.loads(raw_bytes.decode("utf-8"))
        except Exception as err:
            raise PayloadViolationError(f"Failed to parse JSON payload: {err}") from err

        self._check_structure(parsed)
        return parsed

    def inspect_ast_node_limit(self, tree: ast.AST) -> None:
        node_count = sum(1 for _ in ast.walk(tree))
        if node_count > self.config.max_ast_nodes:
            raise PayloadViolationError(
                f"AST node count {node_count} exceeds maximum allowed allocation threshold of {self.config.max_ast_nodes}."
            )
        logger.debug("ast_node_limit_verified", node_count=node_count, threshold=self.config.max_ast_nodes)