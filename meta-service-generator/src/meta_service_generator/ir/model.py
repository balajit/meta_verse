from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any, Literal

from meta_telemetry import get_tracer, trace_span
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

logger = logging.getLogger(__name__)
tracer = get_tracer("meta_service_generator.ir.model")


# -----------------------------------------------------------------------------
# Shared immutable model configuration
# -----------------------------------------------------------------------------

IR_MODEL_CONFIG = ConfigDict(
    frozen=True,
    extra="forbid",
    validate_assignment=True,
)


# -----------------------------------------------------------------------------
# Common types
# -----------------------------------------------------------------------------

ScalarValue = str | int | float | bool | None


class IRHttpMethod(StrEnum):
    """HTTP methods supported by generated endpoint definitions."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class IRCardinality(StrEnum):
    """Relationship cardinality supported by the generated service."""

    ONE_TO_ONE = "1:1"
    ONE_TO_MANY = "1:N"
    MANY_TO_MANY = "N:M"


class IROwnership(StrEnum):
    """Relationship ownership semantics."""

    SOURCE = "source"
    TARGET = "target"
    ASSOCIATION = "association"


class IRLoadingStrategy(StrEnum):
    """SQLAlchemy relationship loading strategies."""

    SELECT = "select"
    SELECTIN = "selectin"
    JOINED = "joined"
    SUBQUERY = "subquery"
    RAISE = "raise"


class IRSerializationDirection(StrEnum):
    """Controls whether a relationship is exposed in generated DTOs."""

    NONE = "none"
    FORWARD = "forward"
    REVERSE = "reverse"
    BOTH = "both"


class IRTransactionBoundary(StrEnum):
    """Defines who owns the transaction boundary."""

    WORKFLOW = "workflow"
    STEP = "step"
    NONE = "none"


class IRWorkflowExecutionMode(StrEnum):
    """Defines workflow step scheduling semantics."""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


class IRExpressionLanguage(StrEnum):
    """
    Declarative languages supported by the rule engine.

    Rules MUST NOT be represented as executable Python source.
    """

    RULE_ENGINE = "rule-engine"


class IRConstraintKind(StrEnum):
    """Supported normalized field constraint categories."""

    MIN_LENGTH = "min_length"
    MAX_LENGTH = "max_length"
    MIN_VALUE = "min_value"
    MAX_VALUE = "max_value"
    PATTERN = "pattern"
    MULTIPLE_OF = "multiple_of"
    ENUM = "enum"


# -----------------------------------------------------------------------------
# Field metadata
# -----------------------------------------------------------------------------


class IRConstraint(BaseModel):
    """Normalized validation constraint for a generated field."""

    kind: IRConstraintKind
    value: ScalarValue

    model_config = IR_MODEL_CONFIG


class IRField(BaseModel):
    """
    Immutable normalized field representation.

    The IR separates database nullability from API requiredness. A nullable
    database column does not necessarily imply an optional API field, and an
    API-optional field does not necessarily imply a nullable database column.
    """

    name: str
    original_name: str
    python_type: str
    sql_type: str

    # Database semantics.
    is_primary_key: bool = False
    is_nullable: bool = False
    is_unique: bool = False
    is_indexed: bool = False

    # External/database naming.
    db_column_name: str | None = None
    api_name: str | None = None

    # API semantics are deliberately independent of DB nullability.
    create_required: bool = True
    update_required: bool = False
    response_nullable: bool = False

    # Defaults.
    default_value: ScalarValue = None
    default_factory: str | None = None

    # Validation and security metadata.
    constraints: tuple[IRConstraint, ...] = Field(default_factory=tuple)
    validation: tuple[str, ...] = Field(default_factory=tuple)
    sensitive: bool = False

    # Foreign-key metadata.
    foreign_key_target: str | None = None
    foreign_key_on_delete: Literal[
        "CASCADE",
        "SET NULL",
        "RESTRICT",
        "NO ACTION",
    ] | None = None
    foreign_key_on_update: Literal[
        "CASCADE",
        "SET NULL",
        "RESTRICT",
        "NO ACTION",
    ] | None = None

    model_config = IR_MODEL_CONFIG

    @field_validator(
        "name",
        "original_name",
        "python_type",
        "sql_type",
        mode="before",
    )
    @classmethod
    def _reject_empty_strings(cls, value: str) -> str:
        if not isinstance(value, str):
            raise TypeError(
                f"Expected string, got {type(value).__name__}."
            )

        if not value.strip():
            raise ValueError("IR field string values cannot be empty.")

        return value

    @model_validator(mode="after")
    def _validate_field_semantics(self) -> "IRField":
        if self.is_primary_key and self.is_nullable:
            raise ValueError(
                f"Primary-key field '{self.name}' cannot be nullable."
            )

        if self.default_factory is not None and self.default_value is not None:
            raise ValueError(
                f"Field '{self.name}' cannot define both default_value "
                "and default_factory."
            )

        if (
                self.foreign_key_on_delete == "SET NULL"
                and not self.is_nullable
        ):
            raise ValueError(
                f"Foreign-key field '{self.name}' uses ON DELETE SET NULL "
                "but is not nullable."
            )

        if self.foreign_key_target is not None:
            if not self.foreign_key_target.strip():
                raise ValueError(
                    f"Field '{self.name}' has an empty foreign key target."
                )

            if "." not in self.foreign_key_target:
                raise ValueError(
                    f"Field '{self.name}' foreign_key_target must identify "
                    "a referenced table and physical database column, "
                    "for example 'orders.id'."
                )

        if self.db_column_name is None:
            object.__setattr__(
                self,
                "db_column_name",
                self.original_name,
            )

        if self.api_name is None:
            object.__setattr__(
                self,
                "api_name",
                self.original_name,
            )

        if self.is_primary_key:
            # Generated create DTOs normally omit database-generated keys.
            # This remains explicit in the IR rather than being inferred by
            # the renderer.
            object.__setattr__(
                self,
                "create_required",
                False,
            )

        return self


# -----------------------------------------------------------------------------
# Relationship metadata
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
# Relationship metadata
# -----------------------------------------------------------------------------


class IRRelationship(BaseModel):
    """
    Normalized relationship metadata.

    Relationships explicitly represent ownership, foreign keys, nullability,
    cascade behavior, loading strategy, and serialization direction.
    """

    name: str
    original_name: str

    source_entity: str | None = None
    target_entity: str
    target_class_name: str

    cardinality: IRCardinality | str

    # Foreign-key column on the source/owning table.
    #
    # For a normal one-to-one / one-to-many relationship this should identify
    # the actual source-side column that contains the FK.
    foreign_key: str | None = None

    # Referenced target-side FK representation.
    #
    # This is required for target-owned relationships because the FK lives on
    # the target table rather than the source table.
    foreign_key_target: str | None = None

    ownership: IROwnership = IROwnership.SOURCE

    nullable: bool = False

    cascade: tuple[str, ...] = Field(default_factory=tuple)

    loading: IRLoadingStrategy = IRLoadingStrategy.SELECTIN

    serialize: IRSerializationDirection = (
        IRSerializationDirection.FORWARD
    )

    is_circular: bool = False

    back_populates: str | None = None
    secondary_table: str | None = None

    model_config = IR_MODEL_CONFIG

    @model_validator(mode="after")
    def _validate_relationship(self) -> "IRRelationship":
        if not self.target_entity.strip():
            raise ValueError(
                f"Relationship '{self.name}' has an empty target entity."
            )

        if not self.target_class_name.strip():
            raise ValueError(
                f"Relationship '{self.name}' has an empty target class name."
            )

        if self.source_entity is not None and not self.source_entity.strip():
            raise ValueError(
                f"Relationship '{self.name}' has an empty source entity."
            )

        if self.foreign_key is not None and not self.foreign_key.strip():
            raise ValueError(
                f"Relationship '{self.name}' has an empty foreign key."
            )

        if (
                self.foreign_key_target is not None
                and not self.foreign_key_target.strip()
        ):
            raise ValueError(
                f"Relationship '{self.name}' has an empty "
                "foreign_key_target."
            )

        if self.back_populates is not None and not self.back_populates.strip():
            raise ValueError(
                f"Relationship '{self.name}' has an empty back_populates."
            )

        if self.cardinality == IRCardinality.MANY_TO_MANY:
            if self.secondary_table is None:
                raise ValueError(
                    f"Many-to-many relationship '{self.name}' requires "
                    "secondary_table."
                )

            if not self.secondary_table.strip():
                raise ValueError(
                    f"Many-to-many relationship '{self.name}' has an empty "
                    "secondary_table."
                )

        elif self.secondary_table is not None:
            raise ValueError(
                f"Relationship '{self.name}' defines secondary_table but is "
                f"not many-to-many."
            )

        # Only source-owned relationships require the source-side FK.
        #
        # Target-owned relationships may legitimately omit both FK values
        # from this relationship record because the FK is represented by
        # the inverse/target relationship.
        if (
                self.cardinality != IRCardinality.MANY_TO_MANY
                and self.ownership == IROwnership.SOURCE
                and self.foreign_key is None
        ):
            raise ValueError(
                f"Relationship '{self.name}' is source-owned but does not "
                "define a foreign_key."
            )

        return self


# -----------------------------------------------------------------------------
# FSM metadata
# -----------------------------------------------------------------------------


class IRFSMHook(BaseModel):
    """Lifecycle hook invoked when entering or exiting an FSM state."""

    name: str
    action: str

    model_config = IR_MODEL_CONFIG


class IRTransitionAction(BaseModel):
    """Action executed as part of an FSM transition."""

    name: str
    action: str

    model_config = IR_MODEL_CONFIG


class IRTransition(BaseModel):
    """Represents a single valid FSM state transition."""

    trigger: str
    source_state: str
    target_state: str

    guards: tuple[str, ...] = Field(default_factory=tuple)
    actions: tuple[IRTransitionAction, ...] = Field(
        default_factory=tuple
    )

    model_config = IR_MODEL_CONFIG

    @model_validator(mode="after")
    def _validate_transition(self) -> "IRTransition":
        if self.source_state == self.target_state:
            logger.debug(
                "FSM transition '%s' is a self-transition.",
                self.trigger,
            )

        return self


class IRFSM(BaseModel):
    """
    Immutable finite-state-machine definition.

    FSM definitions contain the state field, states, transitions, initial
    state, entry hooks, exit hooks, and transition guards.
    """

    state_attribute: str
    initial_state: str
    states: tuple[str, ...]

    transitions: tuple[IRTransition, ...]

    entry_hooks: tuple[IRFSMHook, ...] = Field(default_factory=tuple)
    exit_hooks: tuple[IRFSMHook, ...] = Field(default_factory=tuple)

    transition_guards: tuple[str, ...] = Field(default_factory=tuple)

    model_config = IR_MODEL_CONFIG

    @model_validator(mode="after")
    def _validate_fsm(self) -> "IRFSM":
        state_set = set(self.states)

        if not state_set:
            raise ValueError("FSM must contain at least one state.")

        if self.initial_state not in state_set:
            raise ValueError(
                f"FSM initial state '{self.initial_state}' is not "
                "defined in states."
            )

        triggers: set[str] = set()

        for transition in self.transitions:
            if transition.source_state not in state_set:
                raise ValueError(
                    f"FSM transition '{transition.trigger}' references "
                    f"unknown source state '{transition.source_state}'."
                )

            if transition.target_state not in state_set:
                raise ValueError(
                    f"FSM transition '{transition.trigger}' references "
                    f"unknown target state '{transition.target_state}'."
                )

            transition_key = (
                transition.trigger,
                transition.source_state,
            )

            if transition_key in triggers:
                raise ValueError(
                    "Duplicate FSM transition for trigger "
                    f"'{transition.trigger}' from state "
                    f"'{transition.source_state}'."
                )

            triggers.add(transition_key)

        return self


# -----------------------------------------------------------------------------
# Rule metadata
# -----------------------------------------------------------------------------


class IRRuleCondition(BaseModel):
    """
    Declarative rule condition.

    The condition is data consumed by the rule engine and is never treated as
    executable Python source.
    """

    expression: str

    model_config = IR_MODEL_CONFIG

    @field_validator("expression")
    @classmethod
    def _validate_expression(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "Rule condition expression cannot be empty."
            )

        return value


class IRRuleAction(BaseModel):
    """Declarative action associated with a business rule."""

    name: str
    action: str

    model_config = IR_MODEL_CONFIG


class IRRule(BaseModel):
    """
    Immutable normalized business-rule definition.

    Rules MUST represent rule_id, priority, preconditions, conditions,
    actions, postconditions, failure_code, and failure_message.

    The representation is deliberately declarative so that rule expressions
    cannot become arbitrary generated Python.
    """

    name: str
    target_entity: str

    expression_language: IRExpressionLanguage = (
        IRExpressionLanguage.RULE_ENGINE
    )

    expression: str

    priority: int = 0

    preconditions: tuple[IRRuleCondition, ...] = Field(
        default_factory=tuple
    )
    conditions: tuple[IRRuleCondition, ...] = Field(
        default_factory=tuple
    )
    actions: tuple[IRRuleAction, ...] = Field(
        default_factory=tuple
    )
    postconditions: tuple[IRRuleCondition, ...] = Field(
        default_factory=tuple
    )

    error_code: str = "ERR_BUSINESS_RULE_VIOLATION"
    error_message: str = ""

    model_config = IR_MODEL_CONFIG

    @field_validator("expression")
    @classmethod
    def _validate_expression(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "Business-rule expression cannot be empty."
            )

        return value

    @field_validator("error_message")
    @classmethod
    def _validate_error_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "Business-rule error_message cannot be empty."
            )

        return value


# -----------------------------------------------------------------------------
# Workflow metadata
# -----------------------------------------------------------------------------


class IRRetryPolicy(BaseModel):
    """Immutable retry policy consumed by generated workflow execution."""

    max_retries: int = Field(default=0, ge=0, le=20)

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

    model_config = IR_MODEL_CONFIG

    @model_validator(mode="after")
    def _validate_backoff_range(self) -> "IRRetryPolicy":
        if self.max_seconds < self.min_seconds:
            raise ValueError(
                "Retry max_seconds cannot be less than min_seconds."
            )

        return self


class IRCompensation(BaseModel):
    """Compensating operation for a workflow step."""

    action: str
    timeout_seconds: float | None = Field(
        default=None,
        gt=0,
    )

    model_config = IR_MODEL_CONFIG


class IRWorkflowStep(BaseModel):
    """Immutable normalized workflow step definition."""

    name: str
    action: str
    depends_on: tuple[str, ...]

    # Backward-compatible representation retained for current IRBuilder
    # callers. retry_policy is the canonical Phase-2 representation.
    max_retries: int = Field(
        default=0,
        ge=0,
        le=20,
    )

    retry_policy: IRRetryPolicy | None = None

    timeout_seconds: float | None = Field(
        default=None,
        gt=0,
    )

    compensation: IRCompensation | None = None

    model_config = IR_MODEL_CONFIG

    @model_validator(mode="after")
    def _normalize_retry_policy(self) -> "IRWorkflowStep":
        if self.retry_policy is None:
            object.__setattr__(
                self,
                "retry_policy",
                IRRetryPolicy(
                    max_retries=self.max_retries,
                ),
            )
        elif self.max_retries != 0 and (
            self.retry_policy.max_retries != self.max_retries
        ):
            raise ValueError(
                f"Workflow step '{self.name}' specifies conflicting "
                "max_retries and retry_policy.max_retries values."
            )

        return self


class IRWorkflow(BaseModel):
    """
    Immutable normalized workflow definition.

    Workflow IR supports workflow_id, steps, dependencies,
    execution_mode, transaction_boundary, retry_policy, timeout,
    and compensation.

    Steps MUST form a valid DAG.
    """

    name: str
    steps: tuple[IRWorkflowStep, ...]

    execution_mode: IRWorkflowExecutionMode = (
        IRWorkflowExecutionMode.PARALLEL
    )

    transaction_boundary: IRTransactionBoundary = (
        IRTransactionBoundary.WORKFLOW
    )

    retry_policy: IRRetryPolicy = Field(
        default_factory=IRRetryPolicy
    )

    timeout_seconds: float | None = Field(
        default=None,
        gt=0,
    )

    compensation_enabled: bool = False

    model_config = IR_MODEL_CONFIG

    @model_validator(mode="after")
    def _validate_workflow(self) -> "IRWorkflow":
        step_names = [step.name for step in self.steps]

        if len(step_names) != len(set(step_names)):
            duplicates = sorted(
                {
                    name
                    for name in step_names
                    if step_names.count(name) > 1
                }
            )
            raise ValueError(
                f"Workflow '{self.name}' contains duplicate steps: "
                f"{duplicates}."
            )

        step_set = set(step_names)

        for step in self.steps:
            missing_dependencies = sorted(
                set(step.depends_on) - step_set
            )

            if missing_dependencies:
                raise ValueError(
                    f"Workflow '{self.name}' step '{step.name}' "
                    "references unknown dependencies: "
                    f"{missing_dependencies}."
                )

            if step.name in step.depends_on:
                raise ValueError(
                    f"Workflow '{self.name}' step '{step.name}' "
                    "cannot depend on itself."
                )

            if self.compensation_enabled and step.compensation is None:
                logger.debug(
                    "Workflow '%s' has compensation enabled but step "
                    "'%s' has no step-specific compensation.",
                    self.name,
                    step.name,
                )

        return self


# -----------------------------------------------------------------------------
# Authorization / policy metadata
# -----------------------------------------------------------------------------


class IRAttributeRequirement(BaseModel):
    """ABAC attribute requirement used by a generated policy."""

    attribute: str
    operator: Literal[
        "eq",
        "neq",
        "in",
        "not_in",
        "lt",
        "lte",
        "gt",
        "gte",
        "contains",
        "exists",
    ]
    value: ScalarValue = None
    request_attribute: str | None = None
    resource_attribute: str | None = None

    model_config = IR_MODEL_CONFIG


class IRPolicy(BaseModel):
    """
    Immutable authorization policy.

    Policy IR supports RBAC, ABAC, endpoint-level authorization, required
    roles, required attributes, and resource/request comparisons.
    """

    name: str

    roles: tuple[str, ...]
    actions: tuple[str, ...]

    claims_required: tuple[str, ...] = Field(
        default_factory=tuple
    )

    attributes_required: tuple[IRAttributeRequirement, ...] = Field(
        default_factory=tuple
    )

    endpoint_methods: tuple[IRHttpMethod, ...] = Field(
        default_factory=tuple
    )

    endpoint_paths: tuple[str, ...] = Field(
        default_factory=tuple
    )

    resource_type: str | None = None

    model_config = IR_MODEL_CONFIG

    @model_validator(mode="after")
    def _validate_policy(self) -> "IRPolicy":
        if not self.roles:
            raise ValueError(
                f"Policy '{self.name}' must define at least one role."
            )

        if not self.actions:
            raise ValueError(
                f"Policy '{self.name}' must define at least one action."
            )

        return self


# -----------------------------------------------------------------------------
# Endpoint / API metadata
# -----------------------------------------------------------------------------


class IRIdempotency(BaseModel):
    """Endpoint idempotency configuration."""

    enabled: bool = False
    header_name: str = "Idempotency-Key"

    ttl_seconds: int = Field(
        default=86400,
        gt=0,
    )

    model_config = IR_MODEL_CONFIG


class IREndpoint(BaseModel):
    """
    Immutable endpoint definition consumed by router generation.

    Each endpoint contains operation, method, path, entity, request schema,
    response schema, status code, authorization policy, workflow, and
    idempotency semantics.
    """

    name: str
    operation: str

    method: IRHttpMethod
    path: str

    entity: str

    request_schema: str | None = None
    response_schema: str | None = None

    status_code: int = Field(
        default=200,
        ge=100,
        le=599,
    )

    authorization_policy: str | None = None
    workflow: str | None = None

    idempotency: IRIdempotency = Field(
        default_factory=IRIdempotency
    )

    model_config = IR_MODEL_CONFIG

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError(
                f"Endpoint path must start with '/': {value!r}."
            )

        if "://" in value:
            raise ValueError(
                f"Endpoint path cannot contain a URL scheme: {value!r}."
            )

        return value


# -----------------------------------------------------------------------------
# Model / entity metadata
# -----------------------------------------------------------------------------


class IRModel(BaseModel):
    """
    Immutable normalized entity representation.

    An entity MUST contain enough information to generate:

    - DB model;
    - Create DTO;
    - Update DTO;
    - Response DTO;
    - Search DTO;
    - repository;
    - router;
    - execution-layer bindings;
    - tests.
    """

    name: str
    class_name: str
    table_name: str

    fields: tuple[IRField, ...]

    relationships: tuple[IRRelationship, ...] = Field(
        default_factory=tuple
    )

    endpoints: tuple[IREndpoint, ...] = Field(
        default_factory=tuple
    )

    fsm: IRFSM | None = None

    has_circular_dependencies: bool = False

    soft_delete: bool = False
    optimistic_locking: bool = False
    version_field: str | None = None

    model_config = IR_MODEL_CONFIG

    @model_validator(mode="after")
    def _validate_model(self) -> "IRModel":
        field_names = [field.name for field in self.fields]

        if len(field_names) != len(set(field_names)):
            duplicates = sorted(
                {
                    name
                    for name in field_names
                    if field_names.count(name) > 1
                }
            )

            raise ValueError(
                f"IR model '{self.name}' contains duplicate fields: "
                f"{duplicates}."
            )

        if self.optimistic_locking:
            if self.version_field is None:
                raise ValueError(
                    f"IR model '{self.name}' enables optimistic locking "
                    "but does not define version_field."
                )

            if self.version_field not in set(field_names):
                raise ValueError(
                    f"IR model '{self.name}' optimistic-locking "
                    f"version field '{self.version_field}' does not exist."
                )

        relationship_names = [
            relationship.name
            for relationship in self.relationships
        ]

        if len(relationship_names) != len(set(relationship_names)):
            raise ValueError(
                f"IR model '{self.name}' contains duplicate "
                "relationship names."
            )

        return self


# -----------------------------------------------------------------------------
# Service IR
# -----------------------------------------------------------------------------


class ServiceIR(BaseModel):
    """
    Immutable canonical normalized representation consumed by all later
    generation stages.

    The IR is deliberately independent of raw JSON/YAML manifest structures.
    """

    service_name: str
    version: str

    models: tuple[IRModel, ...]

    endpoints: tuple[IREndpoint, ...] = Field(
        default_factory=tuple
    )

    rules: tuple[IRRule, ...] = Field(
        default_factory=tuple
    )

    workflows: tuple[IRWorkflow, ...] = Field(
        default_factory=tuple
    )

    policies: tuple[IRPolicy, ...] = Field(
        default_factory=tuple
    )

    model_config = IR_MODEL_CONFIG

    @model_validator(mode="after")
    @trace_span("ir.model.validate_service_ir")
    def _validate_service_ir(self) -> "ServiceIR":
        model_names = [model.name for model in self.models]

        if len(model_names) != len(set(model_names)):
            duplicates = sorted(
                {
                    name
                    for name in model_names
                    if model_names.count(name) > 1
                }
            )

            logger.error(
                "Duplicate IR model names detected: %s",
                duplicates,
            )

            raise ValueError(
                f"Duplicate IR model names: {duplicates}."
            )

        model_set = set(model_names)

        for rule in self.rules:
            if rule.target_entity not in model_set:
                raise ValueError(
                    f"Rule '{rule.name}' references unknown entity "
                    f"'{rule.target_entity}'."
                )

        workflow_names = [
            workflow.name
            for workflow in self.workflows
        ]

        if len(workflow_names) != len(set(workflow_names)):
            raise ValueError(
                "Duplicate IR workflow names detected."
            )

        policy_names = [
            policy.name
            for policy in self.policies
        ]

        if len(policy_names) != len(set(policy_names)):
            raise ValueError(
                "Duplicate IR policy names detected."
            )

        endpoint_names = [
            endpoint.name
            for endpoint in self.endpoints
        ]

        if len(endpoint_names) != len(set(endpoint_names)):
            raise ValueError(
                "Duplicate IR endpoint names detected."
            )

        for endpoint in self.endpoints:
            if endpoint.entity not in model_set:
                raise ValueError(
                    f"Endpoint '{endpoint.name}' references unknown "
                    f"entity '{endpoint.entity}'."
                )

            if endpoint.authorization_policy is not None:
                policy_set = set(policy_names)

                if endpoint.authorization_policy not in policy_set:
                    raise ValueError(
                        f"Endpoint '{endpoint.name}' references unknown "
                        f"authorization policy "
                        f"'{endpoint.authorization_policy}'."
                    )

            if endpoint.workflow is not None:
                workflow_set = set(workflow_names)

                if endpoint.workflow not in workflow_set:
                    raise ValueError(
                        f"Endpoint '{endpoint.name}' references unknown "
                        f"workflow '{endpoint.workflow}'."
                    )

        logger.debug(
            "Validated ServiceIR: service=%s version=%s models=%d "
            "endpoints=%d rules=%d workflows=%d policies=%d",
            self.service_name,
            self.version,
            len(self.models),
            len(self.endpoints),
            len(self.rules),
            len(self.workflows),
            len(self.policies),
        )

        return self

    @property
    def model_map(self) -> dict[str, IRModel]:
        """Returns a deterministic model-name lookup for compiler consumers."""

        return {
            model.name: model
            for model in self.models
        }

    @property
    def rule_map(self) -> dict[str, IRRule]:
        """Returns a deterministic rule-name lookup."""

        return {
            rule.name: rule
            for rule in self.rules
        }

    @property
    def workflow_map(self) -> dict[str, IRWorkflow]:
        """Returns a deterministic workflow-name lookup."""

        return {
            workflow.name: workflow
            for workflow in self.workflows
        }

    @property
    def policy_map(self) -> dict[str, IRPolicy]:
        """Returns a deterministic policy-name lookup."""

        return {
            policy.name: policy
            for policy in self.policies
        }

    @property
    def endpoint_map(self) -> dict[str, IREndpoint]:
        """Returns a deterministic endpoint-name lookup."""

        return {
            endpoint.name: endpoint
            for endpoint in self.endpoints
        }

    @trace_span("ir.model.serialize")
    def to_serializable(self) -> dict[str, Any]:
        """
        Returns the canonical IR representation used for diagnostics,
        debugging, and generation provenance.

        Pydantic's model_dump() is used instead of exposing internal model
        objects to renderers.
        """

        try:
            return self.model_dump(mode="json")
        except Exception:
            logger.exception(
                "Failed to serialize ServiceIR for service '%s'.",
                self.service_name,
            )
            raise