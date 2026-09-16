from __future__ import annotations

import importlib
import inspect
import pkgutil
import types
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from meta_service_generator.exceptions import CodeGenerationError
from meta_service_generator.extensions.contracts import (
    AbstractFSMHook,
    AbstractRuleOverride,
    AbstractWorkflowHook,
    ExtensionContext,
)
from meta_telemetry import get_tracer, trace_span
from pydantic import BaseModel
from meta_service_generator.local_telemetry import get_logger

logger = get_logger("meta_service_generator.extensions.regsitry")
tracer = get_tracer("meta_service_generator.extensions.registry")

ContextDataT = TypeVar("ContextDataT", bound=BaseModel)


class ExtensionRegistry(Generic[ContextDataT]):
    """
    Registry that discovers, loads, and executes operator extension hooks
    during application startup lifespan [source: 3].

    A registry instance owns its lifecycle and is intentionally not implemented
    as a process-global asyncio singleton.
    """

    def __init__(self) -> None:
        self._workflow_hooks: list[
            AbstractWorkflowHook[ContextDataT]
        ] = []
        self._rule_overrides: list[
            AbstractRuleOverride[ContextDataT]
        ] = []
        self._fsm_hooks: list[
            AbstractFSMHook[ContextDataT]
        ] = []

        self._registered_types: set[
            tuple[str, str]
        ] = set()

        self._initialized = False

    @property
    def initialized(self) -> bool:
        """Return whether extension discovery has completed."""
        return self._initialized

    @property
    def workflow_hooks(
        self,
    ) -> Sequence[AbstractWorkflowHook[ContextDataT]]:
        return tuple(self._workflow_hooks)

    @property
    def rule_overrides(
        self,
    ) -> Sequence[AbstractRuleOverride[ContextDataT]]:
        return tuple(self._rule_overrides)

    @property
    def fsm_hooks(
        self,
    ) -> Sequence[AbstractFSMHook[ContextDataT]]:
        return tuple(self._fsm_hooks)

    @trace_span("extensions.registry.discover_and_register")
    async def discover_and_register(
        self,
        package_path: str = "extensions",
    ) -> None:
        """
        Scans the operator extensions package for plugin implementations and registers them.
        Must be invoked during FastAPI startup lifespan [source: 3].
        """
        if self._initialized:
            logger.info(
                "Extension registry already initialized; skipping rediscovery."
            )
            return

        if not package_path.strip():
            raise CodeGenerationError(
                message="Extension package path must not be empty.",
                location="extensions",
                error_code="ERR_EXTENSION_PACKAGE_INVALID",
                suggested_resolution=(
                    "Configure a valid Python package path for operator extensions."
                ),
            )

        logger.info(
            "Discovering operator extensions.",
            extra={"package_path": package_path},
        )

        try:
            module = importlib.import_module(package_path)
        except ModuleNotFoundError as err:
            if err.name == package_path:
                logger.info(
                    "No operator extension package configured.",
                    extra={"package_path": package_path},
                )
                self._initialized = True
                return

            raise CodeGenerationError(
                message=(
                    f"Extension package '{package_path}' imported a missing "
                    f"dependency '{err.name}'."
                ),
                location=package_path,
                error_code="ERR_EXTENSION_DEPENDENCY_MISSING",
                suggested_resolution=(
                    "Install the extension dependency or correct the extension import."
                ),
            ) from err
        except Exception as err:
            raise CodeGenerationError(
                message=(
                    f"Failed to import extension package "
                    f"'{package_path}': {err}"
                ),
                location=package_path,
                error_code="ERR_EXTENSION_PACKAGE_LOAD_FAILED",
                suggested_resolution=(
                    "Fix the extension package import and retry generation."
                ),
            ) from err

        if not hasattr(module, "__path__"):
            self._register_from_module(module)
        else:
            module_names = sorted(
                module_info.name
                for module_info in pkgutil.walk_packages(
                    module.__path__,
                    prefix=f"{package_path}.",
                )
            )

            for module_name in module_names:
                try:
                    submodule = importlib.import_module(module_name)
                    self._register_from_module(submodule)
                except Exception as err:
                    raise CodeGenerationError(
                        message=(
                            f"Failed to load operator extension module "
                            f"'{module_name}': {err}"
                        ),
                        location=module_name,
                        error_code="ERR_EXTENSION_LOAD_FAILED",
                        suggested_resolution=(
                            "Fix syntax or import errors in custom operator extension code."
                        ),
                    ) from err

        self._initialized = True

        logger.info(
            "Extension discovery complete.",
            extra={
                "workflow_hooks": len(self._workflow_hooks),
                "rule_overrides": len(self._rule_overrides),
                "fsm_hooks": len(self._fsm_hooks),
            },
        )

    def _register_from_module(
        self,
        module: types.ModuleType,
    ) -> None:
        for attr_name in sorted(dir(module)):
            attr = getattr(module, attr_name)

            if not inspect.isclass(attr):
                continue

            if attr in {
                AbstractWorkflowHook,
                AbstractRuleOverride,
                AbstractFSMHook,
            }:
                continue

            if attr.__module__ != module.__name__:
                continue

            if inspect.isabstract(attr):
                continue

            try:
                if issubclass(attr, AbstractWorkflowHook):
                    self._register_unique(
                        "workflow",
                        attr,
                        self._workflow_hooks,
                        attr(),
                    )

                elif issubclass(attr, AbstractRuleOverride):
                    self._register_unique(
                        "rule_override",
                        attr,
                        self._rule_overrides,
                        attr(),
                    )

                elif issubclass(attr, AbstractFSMHook):
                    self._register_unique(
                        "fsm",
                        attr,
                        self._fsm_hooks,
                        attr(),
                    )
            except TypeError as err:
                raise CodeGenerationError(
                    message=(
                        f"Extension '{module.__name__}.{attr_name}' could not "
                        f"be instantiated: {err}"
                    ),
                    location=f"{module.__name__}.{attr_name}",
                    error_code="ERR_EXTENSION_INSTANTIATION_FAILED",
                    suggested_resolution=(
                        "Ensure extension implementations expose a zero-argument constructor."
                    ),
                ) from err

    def _register_unique(
        self,
        category: str,
        extension_type: type[Any],
        registry: list[Any],
        instance: Any,
    ) -> None:
        key = (
            category,
            f"{extension_type.__module__}.{extension_type.__qualname__}",
        )

        if key in self._registered_types:
            logger.warning(
                "Duplicate extension registration skipped.",
                extra={
                    "category": category,
                    "extension": key[1],
                },
            )
            return

        self._registered_types.add(key)
        registry.append(instance)

        logger.info(
            "Extension registered.",
            extra={
                "category": category,
                "extension": key[1],
            },
        )

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise CodeGenerationError(
                message="Extension registry has not been initialized.",
                location="extensions.registry",
                error_code="ERR_EXTENSION_REGISTRY_NOT_INITIALIZED",
                suggested_resolution=(
                    "Invoke discover_and_register() during application startup "
                    "before executing extension hooks."
                ),
            )

    @trace_span("extensions.registry.execute_before_step")
    async def execute_before_step(
        self,
        step_name: str,
        context: ExtensionContext[ContextDataT],
    ) -> ExtensionContext[ContextDataT]:
        self._ensure_initialized()

        current_context = context

        for hook in self._workflow_hooks:
            try:
                updated = await hook.before_step(
                    step_name,
                    current_context,
                )

                if updated is not None:
                    current_context = updated

            except Exception as err:
                logger.error(
                    "Workflow before_step hook failed.",
                    extra={
                        "hook": hook.__class__.__name__,
                        "step_name": step_name,
                        "execution_id": context.execution_id,
                    },
                )
                raise

        return current_context

    @trace_span("extensions.registry.execute_after_step")
    async def execute_after_step(
        self,
        step_name: str,
        result: Any,
        context: ExtensionContext[ContextDataT],
    ) -> Any:
        self._ensure_initialized()

        current_result = result

        for hook in self._workflow_hooks:
            try:
                updated_result = await hook.after_step(
                    step_name,
                    current_result,
                    context,
                )

                if updated_result is not None:
                    current_result = updated_result

            except Exception:
                logger.error(
                    "Workflow after_step hook failed.",
                    extra={
                        "hook": hook.__class__.__name__,
                        "step_name": step_name,
                        "execution_id": context.execution_id,
                    },
                )
                raise

        return current_result

    @trace_span("extensions.registry.execute_step_override")
    async def execute_step_override(
        self,
        step_name: str,
        context: ExtensionContext[ContextDataT],
    ) -> tuple[bool, Any]:
        self._ensure_initialized()

        for hook in self._workflow_hooks:
            try:
                result = await hook.override_step(
                    step_name,
                    context,
                )

                if result is not None:
                    return True, result

            except Exception:
                logger.error(
                    "Workflow step override failed.",
                    extra={
                        "hook": hook.__class__.__name__,
                        "step_name": step_name,
                        "execution_id": context.execution_id,
                    },
                )
                raise

        return False, None

    @trace_span("extensions.registry.evaluate_rule_override")
    async def evaluate_rule_override(
        self,
        rule_name: str,
        context: ExtensionContext[ContextDataT],
        default_result: bool,
    ) -> bool:
        self._ensure_initialized()

        current_result = default_result

        for override in self._rule_overrides:
            try:
                result = await override.evaluate_rule_override(
                    rule_name,
                    context,
                    current_result,
                )

                if result is not None:
                    current_result = result

            except Exception:
                logger.error(
                    "Rule override evaluation failed.",
                    extra={
                        "override": override.__class__.__name__,
                        "rule_name": rule_name,
                        "execution_id": context.execution_id,
                    },
                )
                raise

        return current_result

    @trace_span("extensions.registry.execute_before_transition")
    async def execute_before_transition(
        self,
        source_state: str,
        target_state: str,
        event: str,
        context: ExtensionContext[ContextDataT],
    ) -> None:
        self._ensure_initialized()

        for hook in self._fsm_hooks:
            try:
                await hook.before_transition(
                    source_state,
                    target_state,
                    event,
                    context,
                )
            except Exception:
                logger.error(
                    "FSM before_transition hook failed.",
                    extra={
                        "hook": hook.__class__.__name__,
                        "source_state": source_state,
                        "target_state": target_state,
                        "event": event,
                        "execution_id": context.execution_id,
                    },
                )
                raise

    @trace_span("extensions.registry.execute_after_transition")
    async def execute_after_transition(
        self,
        source_state: str,
        target_state: str,
        event: str,
        context: ExtensionContext[ContextDataT],
    ) -> None:
        self._ensure_initialized()

        for hook in self._fsm_hooks:
            try:
                await hook.after_transition(
                    source_state,
                    target_state,
                    event,
                    context,
                )
            except Exception:
                logger.error(
                    "FSM after_transition hook failed.",
                    extra={
                        "hook": hook.__class__.__name__,
                        "source_state": source_state,
                        "target_state": target_state,
                        "event": event,
                        "execution_id": context.execution_id,
                    },
                )
                raise