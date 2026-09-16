from __future__ import annotations

from typing import Any, Generic, TypeVar

from meta_service_generator.extensions.contracts import (
    AbstractFSMHook,
    AbstractRuleOverride,
    AbstractWorkflowHook,
    ExtensionContext,
)
from meta_telemetry import get_tracer, trace_span
from pydantic import BaseModel
from meta_service_generator.local_telemetry import get_logger

logger = get_logger("meta_service_generator.extensions.hooks")
tracer = get_tracer("meta_service_generator.extensions.hooks")

ContextDataT = TypeVar("ContextDataT", bound=BaseModel)


class DefaultWorkflowHook(
    AbstractWorkflowHook[ContextDataT],
    Generic[ContextDataT],
):
    """Default no-op fallback implementation for workflow step hooks [source: 3]."""

    @trace_span("hooks.default_workflow.before_step")
    async def before_step(
        self,
        step_name: str,
        context: ExtensionContext[ContextDataT],
    ) -> ExtensionContext[ContextDataT] | None:
        logger.debug(
            "Default workflow before_step hook executed.",
            extra={
                "step_name": step_name,
                "execution_id": context.execution_id,
            },
        )
        return None

    @trace_span("hooks.default_workflow.after_step")
    async def after_step(
        self,
        step_name: str,
        result: Any,
        context: ExtensionContext[ContextDataT],
    ) -> Any | None:
        logger.debug(
            "Default workflow after_step hook executed.",
            extra={
                "step_name": step_name,
                "execution_id": context.execution_id,
            },
        )
        return None

    @trace_span("hooks.default_workflow.override_step")
    async def override_step(
        self,
        step_name: str,
        context: ExtensionContext[ContextDataT],
    ) -> Any | None:
        logger.debug(
            "Default workflow override_step hook executed.",
            extra={
                "step_name": step_name,
                "execution_id": context.execution_id,
            },
        )
        return None


class DefaultRuleOverride(
    AbstractRuleOverride[ContextDataT],
    Generic[ContextDataT],
):
    """Default no-op fallback implementation for business rule overrides [source: 3]."""

    @trace_span("hooks.default_rule.evaluate_rule_override")
    async def evaluate_rule_override(
        self,
        rule_name: str,
        context: ExtensionContext[ContextDataT],
        default_result: bool,
    ) -> bool | None:
        logger.debug(
            "Default rule override executed.",
            extra={
                "rule_name": rule_name,
                "execution_id": context.execution_id,
            },
        )
        return None


class DefaultFSMHook(
    AbstractFSMHook[ContextDataT],
    Generic[ContextDataT],
):
    """Default no-op fallback implementation for state machine transition hooks [source: 3]."""

    @trace_span("hooks.default_fsm.before_transition")
    async def before_transition(
        self,
        source_state: str,
        target_state: str,
        event: str,
        context: ExtensionContext[ContextDataT],
    ) -> None:
        logger.debug(
            "Default FSM before_transition hook executed.",
            extra={
                "source_state": source_state,
                "target_state": target_state,
                "event": event,
                "execution_id": context.execution_id,
            },
        )

    @trace_span("hooks.default_fsm.after_transition")
    async def after_transition(
        self,
        source_state: str,
        target_state: str,
        event: str,
        context: ExtensionContext[ContextDataT],
    ) -> None:
        logger.debug(
            "Default FSM after_transition hook executed.",
            extra={
                "source_state": source_state,
                "target_state": target_state,
                "event": event,
                "execution_id": context.execution_id,
            },
        )