from __future__ import annotations

import importlib
import types
import unittest.mock as mock
from typing import Any

import pytest
from pydantic import BaseModel

from meta_service_generator.exceptions import CodeGenerationError
from meta_service_generator.extensions.contracts import (
    AbstractFSMHook,
    AbstractRuleOverride,
    AbstractWorkflowHook,
    ExtensionContext,
)
from meta_service_generator.extensions.registry import ExtensionRegistry


class RegistryPayload(BaseModel):
    key: str


class MockWorkflowHookA(AbstractWorkflowHook[RegistryPayload]):
    async def before_step(
        self, step_name: str, context: ExtensionContext[RegistryPayload]
    ) -> ExtensionContext[RegistryPayload] | None:
        return ExtensionContext(
            execution_id=f"{context.execution_id}_modified",
            payload=context.payload,
        )

    async def after_step(
        self, step_name: str, result: Any, context: ExtensionContext[RegistryPayload]
    ) -> Any | None:
        return {"step": step_name, "original": result, "modified": True}

    async def override_step(
        self, step_name: str, context: ExtensionContext[RegistryPayload]
    ) -> Any | None:
        if step_name == "overridden_step":
            return "override_value"
        return None


class MockWorkflowHookB(AbstractWorkflowHook[RegistryPayload]):
    async def before_step(
        self, step_name: str, context: ExtensionContext[RegistryPayload]
    ) -> ExtensionContext[RegistryPayload] | None:
        return None

    async def after_step(
        self, step_name: str, result: Any, context: ExtensionContext[RegistryPayload]
    ) -> Any | None:
        return None

    async def override_step(
        self, step_name: str, context: ExtensionContext[RegistryPayload]
    ) -> Any | None:
        return None


class MockRuleOverrideA(AbstractRuleOverride[RegistryPayload]):
    async def evaluate_rule_override(
        self,
        rule_name: str,
        context: ExtensionContext[RegistryPayload],
        default_result: bool,
    ) -> bool | None:
        if rule_name == "force_true":
            return True
        return None


class MockFSMHookA(AbstractFSMHook[RegistryPayload]):
    def __init__(self) -> None:
        self.before_called = False
        self.after_called = False

    async def before_transition(
        self,
        source_state: str,
        target_state: str,
        event: str,
        context: ExtensionContext[RegistryPayload],
    ) -> None:
        if event == "block":
            raise ValueError("Transition blocked")
        self.before_called = True

    async def after_transition(
        self,
        source_state: str,
        target_state: str,
        event: str,
        context: ExtensionContext[RegistryPayload],
    ) -> None:
        if event == "fail_after":
            raise RuntimeError("Post transition failure")
        self.after_called = True


class MockInvalidInitHook(AbstractWorkflowHook[RegistryPayload]):
    def __init__(self, required_arg: str) -> None:
        self.required_arg = required_arg

    async def before_step(self, step_name: str, context: ExtensionContext[RegistryPayload]):
        return None

    async def after_step(self, step_name: str, result: Any, context: ExtensionContext[RegistryPayload]):
        return None

    async def override_step(self, step_name: str, context: ExtensionContext[RegistryPayload]):
        return None


@pytest.fixture
def registry() -> ExtensionRegistry[RegistryPayload]:
    return ExtensionRegistry[RegistryPayload]()


@pytest.fixture
def context() -> ExtensionContext[RegistryPayload]:
    return ExtensionContext(
        execution_id="exec_reg_100",
        payload=RegistryPayload(key="val"),
    )


class TestExtensionRegistryDiscovery:
    @pytest.mark.asyncio
    async def test_discover_empty_package_path_raises_error(
        self, registry: ExtensionRegistry[RegistryPayload]
    ) -> None:
        with pytest.raises(CodeGenerationError) as exc_info:
            await registry.discover_and_register("   ")
        assert exc_info.value.error_code == "ERR_EXTENSION_PACKAGE_INVALID"

    @pytest.mark.asyncio
    async def test_discover_non_existent_package_bypasses(
        self, registry: ExtensionRegistry[RegistryPayload]
    ) -> None:
        await registry.discover_and_register("non_existent_package_xyz_99")
        assert registry.initialized is True
        assert len(registry.workflow_hooks) == 0

    @pytest.mark.asyncio
    async def test_discover_missing_dependency_raises_error(
        self, registry: ExtensionRegistry[RegistryPayload]
    ) -> None:
        err = ModuleNotFoundError("No module named 'sub_dep'", name="sub_dep")
        with mock.patch("importlib.import_module", side_effect=err):
            with pytest.raises(CodeGenerationError) as exc_info:
                await registry.discover_and_register("custom_ext")
            assert exc_info.value.error_code == "ERR_EXTENSION_DEPENDENCY_MISSING"

    @pytest.mark.asyncio
    async def test_discover_general_import_error_raises_error(
        self, registry: ExtensionRegistry[RegistryPayload]
    ) -> None:
        with mock.patch("importlib.import_module", side_effect=ImportError("Syntax Error")):
            with pytest.raises(CodeGenerationError) as exc_info:
                await registry.discover_and_register("custom_ext")
            assert exc_info.value.error_code == "ERR_EXTENSION_PACKAGE_LOAD_FAILED"

    @pytest.mark.asyncio
    async def test_discover_already_initialized_skips(
        self, registry: ExtensionRegistry[RegistryPayload]
    ) -> None:
        registry._initialized = True
        with mock.patch("importlib.import_module") as mock_import:
            await registry.discover_and_register("some_pkg")
            mock_import.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_from_single_module_success(
        self, registry: ExtensionRegistry[RegistryPayload]
    ) -> None:
        dummy_mod = types.ModuleType("dummy_ext_mod")
        dummy_mod.__name__ = "dummy_ext_mod"

        # Explicitly set __module__ so registry does not skip imported attributes
        class HookA(MockWorkflowHookA):
            __module__ = "dummy_ext_mod"

        class RuleA(MockRuleOverrideA):
            __module__ = "dummy_ext_mod"

        class FSMA(MockFSMHookA):
            __module__ = "dummy_ext_mod"

        dummy_mod.HookA = HookA
        dummy_mod.RuleA = RuleA
        dummy_mod.FSMA = FSMA
        dummy_mod.HookA2 = HookA  # Duplicate class should be skipped

        with mock.patch("importlib.import_module", return_value=dummy_mod):
            await registry.discover_and_register("dummy_ext_mod")

        assert registry.initialized is True
        assert len(registry.workflow_hooks) == 1
        assert len(registry.rule_overrides) == 1
        assert len(registry.fsm_hooks) == 1

    @pytest.mark.asyncio
    async def test_register_instantiation_failed_raises_error(
        self, registry: ExtensionRegistry[RegistryPayload]
    ) -> None:
        dummy_mod = types.ModuleType("bad_mod")
        dummy_mod.__name__ = "bad_mod"

        class BadHook(MockInvalidInitHook):
            __module__ = "bad_mod"

        dummy_mod.BadHook = BadHook

        with mock.patch("importlib.import_module", return_value=dummy_mod):
            with pytest.raises(CodeGenerationError) as exc_info:
                await registry.discover_and_register("bad_mod")
            assert exc_info.value.error_code == "ERR_EXTENSION_INSTANTIATION_FAILED"

    @pytest.mark.asyncio
    async def test_register_package_submodule_load_failure(
        self, registry: ExtensionRegistry[RegistryPayload]
    ) -> None:
        pkg_mod = types.ModuleType("pkg")
        pkg_mod.__name__ = "pkg"
        pkg_mod.__path__ = ["/fake/path"]  # type: ignore[attr-defined]

        mock_pkginfo = mock.Mock()
        mock_pkginfo.name = "pkg.submodule"

        real_import = importlib.import_module

        def import_side_effect(name: str, *args: Any, **kwargs: Any):
            if name == "pkg":
                return pkg_mod
            if name.startswith("pkg."):
                raise RuntimeError("Submodule syntax error")
            return real_import(name, *args, **kwargs)

        with mock.patch("pkgutil.walk_packages", return_value=[mock_pkginfo]), \
             mock.patch("importlib.import_module", side_effect=import_side_effect):
            with pytest.raises(CodeGenerationError) as exc_info:
                await registry.discover_and_register("pkg")
            assert exc_info.value.error_code == "ERR_EXTENSION_LOAD_FAILED"


class TestExtensionRegistryExecution:
    @pytest.mark.asyncio
    async def test_execution_uninitialized_raises_error(
        self,
        registry: ExtensionRegistry[RegistryPayload],
        context: ExtensionContext[RegistryPayload],
    ) -> None:
        with pytest.raises(CodeGenerationError) as exc_info:
            await registry.execute_before_step("step1", context)
        assert exc_info.value.error_code == "ERR_EXTENSION_REGISTRY_NOT_INITIALIZED"

    @pytest.mark.asyncio
    async def test_workflow_before_step_chain_and_error(
        self,
        registry: ExtensionRegistry[RegistryPayload],
        context: ExtensionContext[RegistryPayload],
    ) -> None:
        registry._initialized = True
        hook_a = MockWorkflowHookA()
        hook_b = MockWorkflowHookB()
        registry._workflow_hooks.extend([hook_a, hook_b])

        res_ctx = await registry.execute_before_step("step1", context)
        assert res_ctx.execution_id == "exec_reg_100_modified"

        # Test error propagation and isolation log
        failing_hook = mock.AsyncMock(side_effect=RuntimeError("Hook failure"))
        failing_hook_inst = mock.Mock()
        failing_hook_inst.before_step = failing_hook
        registry._workflow_hooks.append(failing_hook_inst)

        with pytest.raises(RuntimeError, match="Hook failure"):
            await registry.execute_before_step("step1", context)

    @pytest.mark.asyncio
    async def test_workflow_after_step_chain_and_error(
        self,
        registry: ExtensionRegistry[RegistryPayload],
        context: ExtensionContext[RegistryPayload],
    ) -> None:
        registry._initialized = True
        hook_a = MockWorkflowHookA()
        hook_b = MockWorkflowHookB()
        registry._workflow_hooks.extend([hook_a, hook_b])

        res = await registry.execute_after_step("step1", "initial_res", context)
        assert res == {"step": "step1", "original": "initial_res", "modified": True}

        failing_hook = mock.AsyncMock(side_effect=ValueError("After step fail"))
        failing_hook_inst = mock.Mock()
        failing_hook_inst.after_step = failing_hook
        registry._workflow_hooks.append(failing_hook_inst)

        with pytest.raises(ValueError, match="After step fail"):
            await registry.execute_after_step("step1", "res", context)

    @pytest.mark.asyncio
    async def test_workflow_step_override(
        self,
        registry: ExtensionRegistry[RegistryPayload],
        context: ExtensionContext[RegistryPayload],
    ) -> None:
        registry._initialized = True
        hook_a = MockWorkflowHookA()
        registry._workflow_hooks.append(hook_a)

        overridden, val = await registry.execute_step_override("overridden_step", context)
        assert overridden is True
        assert val == "override_value"

        not_overridden, val2 = await registry.execute_step_override("other_step", context)
        assert not_overridden is False
        assert val2 is None

        failing_hook = mock.AsyncMock(side_effect=RuntimeError("Override fail"))
        failing_hook_inst = mock.Mock()
        failing_hook_inst.override_step = failing_hook
        registry._workflow_hooks.insert(0, failing_hook_inst)

        with pytest.raises(RuntimeError, match="Override fail"):
            await registry.execute_step_override("step", context)

    @pytest.mark.asyncio
    async def test_evaluate_rule_override(
        self,
        registry: ExtensionRegistry[RegistryPayload],
        context: ExtensionContext[RegistryPayload],
    ) -> None:
        registry._initialized = True
        rule_a = MockRuleOverrideA()
        registry._rule_overrides.append(rule_a)

        res_true = await registry.evaluate_rule_override("force_true", context, default_result=False)
        assert res_true is True

        res_default = await registry.evaluate_rule_override("normal_rule", context, default_result=False)
        assert res_default is False

        failing_override = mock.AsyncMock(side_effect=RuntimeError("Rule fail"))
        failing_inst = mock.Mock()
        failing_inst.evaluate_rule_override = failing_override
        registry._rule_overrides.append(failing_inst)

        with pytest.raises(RuntimeError, match="Rule fail"):
            await registry.evaluate_rule_override("rule", context, False)

    @pytest.mark.asyncio
    async def test_fsm_hooks_before_and_after_transition(
        self,
        registry: ExtensionRegistry[RegistryPayload],
        context: ExtensionContext[RegistryPayload],
    ) -> None:
        registry._initialized = True
        fsm_hook = MockFSMHookA()
        registry._fsm_hooks.append(fsm_hook)

        await registry.execute_before_transition("draft", "active", "publish", context)
        assert fsm_hook.before_called is True

        await registry.execute_after_transition("draft", "active", "publish", context)
        assert fsm_hook.after_called is True

        with pytest.raises(ValueError, match="Transition blocked"):
            await registry.execute_before_transition("draft", "active", "block", context)

        with pytest.raises(RuntimeError, match="Post transition failure"):
            await registry.execute_after_transition("draft", "active", "fail_after", context)