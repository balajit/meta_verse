"""Core Pydantic V2 domain specifications and models for meta_compiler.

Contract Division Notice:
- JSON Schema (meta_schema_v1.json): Performs broad structural validation at input boundary.
- Pydantic Models (this module): Enforces strict identifier patterns, provenance references,
  and immutable IR (Intermediate Representation) structures for runtime compilation.
"""

import logging
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from meta_compiler.core.immutable import ImmutableDict, freeze_value

logger = logging.getLogger("meta_compiler.compilers.models")


class ArtifactSourceSpec(BaseModel):
    """Identifies upstream node and output artifact origin for data provenance.

    Attributes:
        task_id: Upstream producer task identifier.
        artifact_name: Upstream output artifact handle name.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    task_id: str = Field(..., min_length=1, description="Upstream task identifier")
    artifact_name: str = Field(..., min_length=1, description="Upstream output artifact name")

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(f"Task ID '{v}' in artifact source contains invalid characters.")
        return v

    @field_validator("artifact_name")
    @classmethod
    def validate_artifact_name(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", v):
            raise ValueError(
                f"Source artifact name '{v}' must be a valid Python identifier (letters, numbers, underscores)."
            )
        return v


class ArtifactRefSpec(BaseModel):
    """Specifies an input or output data artifact binding for a task node.

    Attributes:
        name: Unique logical identifier for the artifact within task context.
        type: Primary data type string representation.
        schema_def: Optional JSON Schema dictionary defining internal payload contracts.
        source: Optional provenance link to upstream output.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    name: str = Field(..., min_length=1, description="Artifact identifier name")
    type: str = Field(..., min_length=1, description="Data type specification")
    schema_def: Mapping[str, Any] | None = Field(
        default=None,
        alias="schema",
        description="Optional schema payload validation rules",
    )
    source: ArtifactSourceSpec | None = Field(
        default=None,
        description="Provenance reference linking input artifact to upstream task output",
    )

    @field_validator("name")
    @classmethod
    def validate_name_identifier(cls, v: str) -> str:
        """Enforces strict Python variable naming rules for artifact handles."""
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", v):
            raise ValueError(
                f"Artifact name '{v}' must be a valid Python identifier (letters, numbers, underscores)."
            )
        return v


class TaskNodeSpec(BaseModel):
    """Represents an immutable, discrete execution unit node within a workflow graph.

    Attributes:
        id: Unique identifier for the task within manifest scope.
        action: Executable routine or runner target specifier.
        depends_on: Prerequisite parent node IDs.
        inputs: Declared input artifact specifications.
        outputs: Declared output artifact specifications.
        params: Arbitrary static execution configuration.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    id: str = Field(..., min_length=1, description="Unique node ID")
    action: str = Field(..., min_length=1, description="Target action identifier")
    depends_on: tuple[str, ...] = Field(
        default_factory=tuple,
        description="IDs of prerequisite parent nodes",
    )
    inputs: tuple[ArtifactRefSpec, ...] = Field(
        default_factory=tuple,
        description="Input artifact specifications",
    )
    outputs: tuple[ArtifactRefSpec, ...] = Field(
        default_factory=tuple,
        description="Output artifact specifications",
    )
    params: Mapping[str, Any] = Field(
        default_factory=dict,
        description="Static task execution configuration key-values",
    )

    @field_validator("id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                f"Task ID '{v}' contains invalid characters. Must match pattern ^[a-zA-Z0-9_-]+$"
            )
        return v

    @field_validator("depends_on")
    @classmethod
    def validate_no_self_dependency(cls, v: tuple[str, ...], info: Any) -> tuple[str, ...]:
        task_id = info.data.get("id")
        if task_id and task_id in v:
            raise ValueError(f"Task '{task_id}' cannot declare a direct dependency on itself.")

        seen: set[str] = set()
        deduped: list[str] = []
        for item in v:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        return tuple(deduped)

    @model_validator(mode="after")
    def _deep_freeze_params(self) -> "TaskNodeSpec":
        """Freezes the mutable ``params`` mapping into a read-only structure."""
        if not isinstance(self.params, ImmutableDict):
            object.__setattr__(self, "params", freeze_value(self.params))
        return self


class WorkflowManifestSpec(BaseModel):
    """Root metadata container representing a complete, immutable declarative workflow IR.

    Attributes:
        version: Manifest version identifier.
        namespace: Logical grouping boundary.
        name: Canonical workflow identifier name.
        description: Optional human-readable documentation summary.
        tasks: Sequence of declared DAG task nodes.
        entities: Optional dynamic domain model dictionary.
        fsms: Optional finite state machine specifications.
        custom_types_module: Optional filesystem path string for dynamically loaded type modules.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        str_strip_whitespace=True,
    )

    version: str = Field(..., description="Manifest protocol version")
    namespace: str = Field(..., min_length=1, description="Target deployment namespace")
    name: str = Field(..., min_length=1, description="Workflow definition identifier")
    description: str | None = Field(
        default=None,
        description="Detailed workflow summary",
    )
    tasks: tuple[TaskNodeSpec, ...] = Field(
        default_factory=tuple,
        description="Sequence of declared DAG task nodes",
    )
    entities: Mapping[str, Any] = Field(
        default_factory=dict,
        description="Dynamic domain entity AST specifications",
    )
    fsms: Mapping[str, Any] = Field(
        default_factory=dict,
        description="Finite state machine state specifications",
    )
    custom_types_module: str | None = Field(
        default=None,
        description="Path to dynamic custom python types module",
    )

    @field_validator("version")
    @classmethod
    def validate_version_format(cls, v: str) -> str:
        if not re.match(r"^v?[0-9]+(\.[0-9]+)*$", v):
            raise ValueError(
                f"Version string '{v}' must follow semantic versioning format (e.g. 'v1.0.0' or '1.0.0')"
            )
        return v

    @field_validator("tasks")
    @classmethod
    def validate_task_graph_semantics(
        cls, tasks: tuple[TaskNodeSpec, ...]
    ) -> tuple[TaskNodeSpec, ...]:
        """Validates task collection invariants: unique IDs and existence of dependency targets."""
        if not tasks:
            return tasks

        seen_ids: set[str] = set()
        duplicates: set[str] = set()

        for task in tasks:
            if task.id in seen_ids:
                duplicates.add(task.id)
            seen_ids.add(task.id)

        if duplicates:
            raise ValueError(f"Duplicate task node IDs detected in manifest: {sorted(duplicates)}")

        for task in tasks:
            unknown = set(task.depends_on) - seen_ids
            if unknown:
                raise ValueError(f"Task '{task.id}' depends on unknown task(s): {sorted(unknown)}")

        return tasks

    @model_validator(mode="after")
    def _deep_freeze_mappings(self) -> "WorkflowManifestSpec":
        """Freezes mutable mapping fields (entities/fsms) into read-only structures."""
        for field_name in ("entities", "fsms"):
            value = getattr(self, field_name)
            if not isinstance(value, ImmutableDict):
                object.__setattr__(self, field_name, freeze_value(value))
        return self

    def get_node_by_id(self, task_id: str) -> TaskNodeSpec | None:
        """Helper to lookup a task node by its string ID."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None


class NodeExecutionMetadata(BaseModel):
    """Metadata tracking discrete node execution parameters in the target graph."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str
    inputs: list[str]
    output_type: str
    is_terminal: bool = False


class CompiledExecutionGraph(BaseModel):
    """Execution IR returned after manifest syntax, model build, DAG graph compilation, and DB registration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_id: str = Field(..., description="Unique ID or UUID of the registered workflow")
    namespace: str
    name: str
    version: str
    nodes: dict[str, NodeExecutionMetadata] = Field(
        ..., description="Topological nodes in the execution graph"
    )
    db_record_id: int | str = Field(..., description="Primary key of the persisted DB record")
    compiled_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionPlan(BaseModel):
    """Immutable compiler output artifact summarizing workflow graph execution topology."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    graph_version: str = Field(default="v1", description="Plan schema version")
    stages: tuple[tuple[str, ...], ...] = Field(
        ..., description="Sequential parallel execution generations"
    )
    critical_path: tuple[str, ...] = Field(
        ..., description="Longest execution chain sequence from root to leaf"
    )
    roots: tuple[str, ...] = Field(..., description="Entry nodes with zero upstream dependencies")
    leaves: tuple[str, ...] = Field(..., description="Terminal nodes with no downstream dependents")
