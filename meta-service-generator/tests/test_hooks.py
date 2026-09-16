from __future__ import annotations

import pytest
from pydantic import BaseModel

from meta_service_generator.extensions.contracts import ExtensionContext
from meta_service_generator.extensions.hooks import (
    DefaultFSMHook,
    DefaultRuleOverride,
    DefaultWorkflowHook,
)


class DummyPayload(BaseModel):
    value: str


class TestDefaultHooks:
    @pytest.fixture
    def dummy_context(self) -> ExtensionContext[DummyPayload]:
        return ExtensionContext(
            execution_id="exec_test_001",
            payload=DummyPayload(value="test"),
        )

    @pytest.mark.asyncio
    async def test_default_workflow_hook(
        self, dummy_context: ExtensionContext[DummyPayload]
    ) -> None:
        hook = DefaultWorkflowHook[DummyPayload]()

        before_res = await hook.before_step("process_data", dummy_context)
        assert before_res is None

        after_res = await hook.after_step("process_data", {"ok": True}, dummy_context)
        assert after_res is None

        override_res = await hook.override_step("process_data", dummy_context)
        assert override_res is None

    @pytest.mark.asyncio
    async def test_default_rule_override(
        self, dummy_context: ExtensionContext[DummyPayload]
    ) -> None:
        override = DefaultRuleOverride[DummyPayload]()

        rule_res = await override.evaluate_rule_override(
            "check_limit", dummy_context, default_result=True
        )
        assert rule_res is None

    @pytest.mark.asyncio
    async def test_default_fsm_hook(
        self, dummy_context: ExtensionContext[DummyPayload]
    ) -> None:
        fsm_hook = DefaultFSMHook[DummyPayload]()

        # Verify no exceptions raised on execution
        await fsm_hook.before_transition("created", "processing", "start", dummy_context)
        await fsm_hook.after_transition("created", "processing", "start", dummy_context)