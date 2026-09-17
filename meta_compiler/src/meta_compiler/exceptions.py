"""Domain exception hierarchy for the meta_compiler package.

Provides structured, domain-specific exception types containing rich diagnostic
metadata and JSON-serializable payloads for APM tracing and API boundary propagation.
"""

from __future__ import annotations

import os
from typing import Any


class MetaCompilerError(Exception):
    """Base exception for all meta_compiler runtime and compilation errors."""

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | list[Any] | None = None,
        component: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if isinstance(details, dict):
            self.details = dict(details)
        elif isinstance(details, list):
            self.details = {"entries": list(details)}
        else:
            self.details = {}
        self.component = component

    def to_dict(self) -> dict[str, Any]:
        """Return structured, JSON-serializable diagnostic metadata."""
        payload: dict[str, Any] = {
            "error_type": type(self).__name__,
            "message": self.message,
        }

        if self.component:
            payload["component"] = self.component

        if self.details:
            payload["details"] = self.details

        return payload


class ConfigurationError(MetaCompilerError):
    """Raised when runtime configuration or packaged assets are invalid."""

    def __init__(
        self,
        message: str,
        *,
        path: str | os.PathLike[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = dict(details or {})
        if path is not None:
            merged["path"] = os.fspath(path)

        super().__init__(
            message,
            details=merged,
            component="config",
        )


class ManifestSyntaxError(MetaCompilerError):
    """Raised when raw YAML/JSON input cannot be parsed."""

    def __init__(
        self,
        message: str,
        *,
        line_number: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = dict(details or {})

        if line_number is not None:
            merged["line_number"] = line_number

        super().__init__(
            message,
            details=merged,
            component="syntax_guard",
        )


class SchemaValidationError(MetaCompilerError):
    """Raised when manifest input violates the meta-schema."""

    def __init__(
        self,
        message: str,
        *,
        schema_path: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = dict(details or {})

        if schema_path is not None:
            merged["schema_path"] = schema_path

        super().__init__(
            message,
            details=merged,
            component="schema_validator",
        )


class SemanticValidationError(MetaCompilerError):
    """Raised when manifest semantic invariants are violated."""

    def __init__(
        self,
        message: str,
        *,
        node_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = dict(details or {})

        if node_id is not None:
            merged["node_id"] = node_id

        super().__init__(
            message,
            details=merged,
            component="semantic_validator",
        )


class DAGCompilationError(MetaCompilerError):
    """Raised when DAG construction or validation fails."""

    def __init__(
        self,
        message: str,
        *,
        cycle_nodes: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = dict(details or {})

        if cycle_nodes is not None:
            merged["cycle_nodes"] = list(cycle_nodes)

        super().__init__(
            message,
            details=merged,
            component="dag_compiler",
        )


class ContractValidationError(MetaCompilerError):
    """Raised when action or data contracts are incompatible."""

    def __init__(
        self,
        message: str,
        *,
        action_name: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = dict(details or {})

        if action_name is not None:
            merged["action_name"] = action_name

        super().__init__(
            message,
            details=merged,
            component="contract_checker",
        )


class ModelCompilationError(MetaCompilerError):
    """Raised when runtime Pydantic model compilation fails."""

    def __init__(
        self,
        message: str,
        *,
        model_name: str | None = None,
        details: dict[str, Any] | list[Any] | None = None,
    ) -> None:
        if isinstance(details, dict):
            merged = dict(details)
        elif isinstance(details, list):
            merged = {"entries": list(details)}
        else:
            merged = {}

        if model_name is not None:
            merged["model_name"] = model_name

        super().__init__(
            message,
            details=merged,
            component="model_compiler",
        )


class PersistenceError(MetaCompilerError):
    """Raised when persistence or serialization fails."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            details=details,
            component="persistence",
        )


class SyntaxValidationError(ManifestSyntaxError):
    """Alias for :class:`ManifestSyntaxError` for Step-1 syntax-guard compliance.

    Exists to satisfy the exported naming contract (``SyntaxValidationError``)
    while remaining identity-equal to the canonical manifest-syntax exception.
    """


class TopologyValidationError(MetaCompilerError):
    """Raised when graph topology verification fails (pre-graph dependency checks)."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            details=details,
            component="dag_compiler",
        )


class CyclicGraphError(TopologyValidationError):
    """Topological cycle-detection exception (Step-3 cycle check).

    Exists to satisfy the exported naming contract (``CyclicGraphError``).
    Carries the detected ``cycle_nodes`` for diagnostics.
    """

    def __init__(
        self,
        message: str,
        *,
        cycle_nodes: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = dict(details or {})
        if cycle_nodes is not None:
            merged["cycle_nodes"] = list(cycle_nodes)
        super().__init__(
            message,
            details=merged,
        )
        self.cycle_nodes = list(cycle_nodes or [])
