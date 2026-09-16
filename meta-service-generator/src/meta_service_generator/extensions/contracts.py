from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from meta_telemetry import get_tracer, trace_span
from pydantic import BaseModel, ConfigDict, Field

tracer = get_tracer("meta_service_generator.extensions.contracts")

ContextDataT = TypeVar("ContextDataT", bound=BaseModel)


class ExtensionContext(BaseModel, Generic[ContextDataT]):
    """Immutable execution context passed to operator extension hooks [source: 3]."""

    execution_id: str = Field(
        ...,
        min_length=1,
        description="Unique ID for tracing current operation context.",
    )
    tenant_id: str | None = Field(
        default=None,
        description="Optional tenant identifier.",
    )
    actor_id: str | None = Field(
        default=None,
        description="Identifier of invoking user or service.",
    )
    payload: ContextDataT = Field(
        ...,
        description="Strongly typed payload model.",
    )

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=False,
        validate_assignment=True,
    )


class AbstractWorkflowHook(ABC, Generic[ContextDataT]):
    """Abstract base class for operator workflow step hooks and overrides [source: 3]."""

    @abstractmethod
    @trace_span("extensions.workflow.before_step")
    async def before_step(
        self,
        step_name: str,
        context: ExtensionContext[ContextDataT],
    ) -> ExtensionContext[ContextDataT] | None:
        """Executed prior to running a workflow step. Returns updated context or None."""
        raise NotImplementedError

    @abstractmethod
    @trace_span("extensions.workflow.after_step")
    async def after_step(
        self,
        step_name: str,
        result: Any,
        context: ExtensionContext[ContextDataT],
    ) -> Any | None:
        """Executed immediately after a workflow step completes."""
        raise NotImplementedError

    @abstractmethod
    @trace_span("extensions.workflow.override_step")
    async def override_step(
        self,
        step_name: str,
        context: ExtensionContext[ContextDataT],
    ) -> Any | None:
        """Replaces execution of a specific step if non-None is returned."""
        raise NotImplementedError


class AbstractRuleOverride(ABC, Generic[ContextDataT]):
    """Abstract base class for overriding or augmenting business rule evaluations [source: 3]."""

    @abstractmethod
    @trace_span("extensions.rule.evaluate_override")
    async def evaluate_rule_override(
        self,
        rule_name: str,
        context: ExtensionContext[ContextDataT],
        default_result: bool,
    ) -> bool | None:
        """Override or compose business rule logic. Return bool to force result, or None to keep default."""
        raise NotImplementedError


class AbstractFSMHook(ABC, Generic[ContextDataT]):
    """Abstract base class for state transition guards and post-commit hooks [source: 3]."""

    @abstractmethod
    @trace_span("extensions.fsm.before_transition")
    async def before_transition(
        self,
        source_state: str,
        target_state: str,
        event: str,
        context: ExtensionContext[ContextDataT],
    ) -> None:
        """Transition guard. Raise Exception to block state transition."""
        raise NotImplementedError

    @abstractmethod
    @trace_span("extensions.fsm.after_transition")
    async def after_transition(
        self,
        source_state: str,
        target_state: str,
        event: str,
        context: ExtensionContext[ContextDataT],
    ) -> None:
        """Post-commit side-effect hook after state transition succeeds."""
        raise NotImplementedError