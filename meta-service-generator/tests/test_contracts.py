from __future__ import annotations

from typing import Any
import pytest
from pydantic import BaseModel, ValidationError

from meta_service_generator.extensions.contracts import (
    AbstractFSMHook,
    AbstractRuleOverride,
    AbstractWorkflowHook,
    ExtensionContext,
)


class SamplePayload(BaseModel):
    user_id: str
    item_count: int


class TestExtensionContext:
    def test_context_instantiation_valid(self) -> None:
        payload = SamplePayload(user_id="usr_123", item_count=5)
        ctx = ExtensionContext(
            execution_id="exec_999",
            tenant_id="tenant_a",
            actor_id="actor_456",
            payload=payload,
        )

        assert ctx.execution_id == "exec_999"
        assert ctx.tenant_id == "tenant_a"
        assert ctx.actor_id == "actor_456"
        assert ctx.payload.user_id == "usr_123"
        assert ctx.payload.item_count == 5

    def test_context_immutability_frozen(self) -> None:
        payload = SamplePayload(user_id="usr_123", item_count=5)
        ctx = ExtensionContext(execution_id="exec_1", payload=payload)

        with pytest.raises(ValidationError):
            ctx.execution_id = "exec_2"  # type: ignore[misc]

    def test_context_extra_fields_forbidden(self) -> None:
        payload = SamplePayload(user_id="usr_123", item_count=5)
        with pytest.raises(ValidationError):
            ExtensionContext(
                execution_id="exec_1",
                payload=payload,
                unknown_field="unsupported",  # type: ignore[call-arg]
            )


class ConcreteWorkflowHook(AbstractWorkflowHook[SamplePayload]):
    async def before_step(
        self, step_name: str, context: ExtensionContext[SamplePayload]
    ) -> ExtensionContext[SamplePayload] | None:
        return await super().before_step(step_name, context)

    async def after_step(
        self, step_name: str, result: Any, context: ExtensionContext[SamplePayload]
    ) -> Any | None:
        return await super().after_step(step_name, result, context)

    async def override_step(
        self, step_name: str, context: ExtensionContext[SamplePayload]
    ) -> Any | None:
        return await super().override_step(step_name, context)


class ConcreteRuleOverride(AbstractRuleOverride[SamplePayload]):
    async def evaluate_rule_override(
        self,
        rule_name: str,
        context: ExtensionContext[SamplePayload],
        default_result: bool,
    ) -> bool | None:
        return await super().evaluate_rule_override(rule_name, context, default_result)


class ConcreteFSMHook(AbstractFSMHook[SamplePayload]):
    async def before_transition(
        self,
        source_state: str,
        target_state: str,
        event: str,
        context: ExtensionContext[SamplePayload],
    ) -> None:
        await super().before_transition(source_state, target_state, event, context)

    async def after_transition(
        self,
        source_state: str,
        target_state: str,
        event: str,
        context: ExtensionContext[SamplePayload],
    ) -> None:
        await super().after_transition(source_state, target_state, event, context)


class TestAbstractContracts:
    @pytest.mark.asyncio
    async def test_abstract_workflow_hook_raises_not_implemented(self) -> None:
        hook = ConcreteWorkflowHook()
        payload = SamplePayload(user_id="usr_1", item_count=1)
        ctx = ExtensionContext(execution_id="ex_1", payload=payload)

        with pytest.raises(NotImplementedError):
            await hook.before_step("step1", ctx)

        with pytest.raises(NotImplementedError):
            await hook.after_step("step1", "res", ctx)

        with pytest.raises(NotImplementedError):
            await hook.override_step("step1", ctx)

    @pytest.mark.asyncio
    async def test_abstract_rule_override_raises_not_implemented(self) -> None:
        rule = ConcreteRuleOverride()
        payload = SamplePayload(user_id="usr_1", item_count=1)
        ctx = ExtensionContext(execution_id="ex_1", payload=payload)

        with pytest.raises(NotImplementedError):
            await rule.evaluate_rule_override("rule_1", ctx, True)

    @pytest.mark.asyncio
    async def test_abstract_fsm_hook_raises_not_implemented(self) -> None:
        fsm = ConcreteFSMHook()
        payload = SamplePayload(user_id="usr_1", item_count=1)
        ctx = ExtensionContext(execution_id="ex_1", payload=payload)

        with pytest.raises(NotImplementedError):
            await fsm.before_transition("draft", "active", "publish", ctx)

        with pytest.raises(NotImplementedError):
            await fsm.after_transition("draft", "active", "publish", ctx)