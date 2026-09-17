from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenList(list[Any]):
    """List-compatible container that rejects in-place mutation."""

    def _immutable(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("Manifest collections are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    __iadd__ = _immutable
    __imul__ = _immutable
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable


def _freeze_value(
    value: Any,
) -> Any:
    """Recursively freeze manifest collection values."""
    if isinstance(value, FrozenList):
        return value

    if isinstance(value, list):
        return FrozenList(
            _freeze_value(item)
            for item in value
        )

    if isinstance(value, dict):
        return {
            key: _freeze_value(item)
            for key, item in value.items()
        }

    if isinstance(value, set):
        return frozenset(
            _freeze_value(item)
            for item in value
        )

    if isinstance(value, tuple):
        return tuple(
            _freeze_value(item)
            for item in value
        )

    return value


class _FrozenCollectionsModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
    )

    @model_validator(mode="after")
    def freeze_collections(self) -> Any:
        for field_name, value in self.__dict__.items():
            object.__setattr__(
                self,
                field_name,
                _freeze_value(value),
            )

        return self


class AttributeSpec(_FrozenCollectionsModel):
    name: str = Field(
        min_length=1,
        pattern=r"^[a-z][a-z0-9_]*$",
    )

    type: Literal[
        "str",
        "int",
        "float",
        "bool",
        "datetime",
        "uuid",
        "dict",
        "list",
    ]

    primary_key: bool = False
    nullable: bool = False
    unique: bool = False
    indexed: bool = False


class RelationshipSpec(_FrozenCollectionsModel):
    name: str = Field(
        min_length=1,
        pattern=r"^[a-z][a-z0-9_]*$",
    )

    target_entity: str = Field(min_length=1)

    cardinality: Literal[
        "1:1",
        "1:N",
        "N:M",
    ]

    foreign_key: str | None = Field(
        default=None,
        min_length=1,
    )


class TransitionSpec(_FrozenCollectionsModel):
    trigger: str = Field(
        min_length=1,
        pattern=r"^[a-z][a-z0-9_]*$",
    )

    source_state: str = Field(min_length=1)
    target_state: str = Field(min_length=1)

    guards: list[str] = Field(
        default_factory=list,
    )


class FSMSpec(_FrozenCollectionsModel):
    state_attribute: str = Field(min_length=1)
    initial_state: str = Field(min_length=1)

    states: list[str] = Field(
        min_length=1,
    )

    transitions: list[TransitionSpec] = Field(
        default_factory=list,
    )


class EntitySpec(_FrozenCollectionsModel):
    name: str = Field(
        min_length=1,
        pattern=r"^[A-Z][a-zA-Z0-9]*$",
    )

    class_name: str | None = Field(
        default=None,
        alias="class_name",
        min_length=1,
        pattern=r"^[A-Z][a-zA-Z0-9]*$",
    )

    table_name: str | None = Field(
        default=None,
        alias="tableName",
        min_length=1,
        pattern=r"^[a-z][a-z0-9_]*$",
    )

    attributes: list[AttributeSpec] = Field(
        min_length=1,
    )

    relationships: list[RelationshipSpec] = Field(
        default_factory=list,
    )

    fsm: FSMSpec | None = None

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
    )


class BusinessRuleSpec(_FrozenCollectionsModel):
    name: str = Field(
        min_length=1,
        pattern=r"^[a-z][a-z0-9_]*$",
    )

    priority:int = Field(
        default=1,
        ge=0
    )

    target_entity: str = Field(min_length=1)
    expression: str = Field(min_length=1)
    error_code: str = Field(
        min_length=1,
        pattern=r"^[A-Z0-9_]*$",
    )
    error_message: str = Field(min_length=1)


class RetryPolicySpec(_FrozenCollectionsModel):
    """
    Declarative retry/backoff configuration for workflows and workflow steps.

    This mirrors the canonical IRRetryPolicy contract while remaining
    independent from the IR package.
    """

    max_retries: int = Field(
        default=0,
        ge=0,
        le=100,
    )

    multiplier: float = Field(
        default=1.0,
        gt=0,
    )

    min_seconds: float = Field(
        default=0.1,
        ge=0,
    )

    max_seconds: float = Field(
        default=10.0,
        gt=0,
    )

    @model_validator(mode="after")
    def validate_backoff_range(self) -> RetryPolicySpec:
        if self.max_seconds < self.min_seconds:
            raise ValueError(
                "Retry max_seconds cannot be less than min_seconds."
            )

        return self


class CompensationSpec(_FrozenCollectionsModel):
    """Compensating operation for a workflow step."""

    action: str = Field(min_length=1)

    timeout_seconds: float | None = Field(
        default=None,
        gt=0,
    )


class WorkflowStepSpec(_FrozenCollectionsModel):
    name: str = Field(
        min_length=1,
        pattern=r"^[a-z][a-z0-9_]*$",
    )

    action: str = Field(min_length=1)

    depends_on: list[str] = Field(
        default_factory=list,
    )

    # Backward-compatible representation aligned with manifest schema range (0..100)
    max_retries: int = Field(
        default=3,
        ge=0,
        le=100,
    )

    retry_policy: RetryPolicySpec | None = None

    timeout_seconds: float | None = Field(
        default=None,
        gt=0,
    )

    compensation: CompensationSpec | None = None

    @model_validator(mode="after")
    def validate_retry_configuration(self) -> WorkflowStepSpec:
        if (
            self.retry_policy is not None
            and self.max_retries != 3
            and self.retry_policy.max_retries != self.max_retries
        ):
            raise ValueError(
                f"Workflow step '{self.name}' specifies conflicting "
                "max_retries and retry_policy.max_retries values."
            )

        return self


class WorkflowSpec(_FrozenCollectionsModel):
    name: str = Field(
        min_length=1,
        pattern=r"^[a-z][a-z0-9_]*$",
    )

    steps: list[WorkflowStepSpec] = Field(
        min_length=1,
    )

    execution_mode: Literal[
        "sequential",
        "parallel",
    ] = "parallel"

    transaction_boundary: Literal[
        "workflow",
        "step",
        "none",
    ] = "workflow"

    retry_policy: RetryPolicySpec = Field(
        default_factory=RetryPolicySpec,
    )

    timeout_seconds: float | None = Field(
        default=None,
        gt=0,
    )

    compensation_enabled: bool = False


class PolicySpec(_FrozenCollectionsModel):
    name: str = Field(
        min_length=1,
        pattern=r"^[a-z][a-z0-9_]*$",
    )

    roles: list[str] = Field(
        min_length=1,
    )

    actions: list[str] = Field(
        min_length=1,
    )

    claims_required: list[str] = Field(
        default_factory=list,
    )


class ManifestSpec(_FrozenCollectionsModel):
    version: str = Field(
        min_length=1,
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$",
    )

    service_name: str = Field(
        min_length=1,
        pattern=r"^[a-z][a-z0-9_]*$",
    )

    entities: list[EntitySpec] = Field(
        min_length=1,
    )

    business_rules: list[BusinessRuleSpec] = Field(
        default_factory=list,
    )

    workflows: list[WorkflowSpec] = Field(
        default_factory=list,
    )

    policies: list[PolicySpec] = Field(
        default_factory=list,
    )
