"""Action registry module for meta_compiler core.

Provides a thread-safe, central registry to resolve string-based manifest action identifiers
into validated, executable callables and explicit typing schemas for contract verification.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import Any

from pydantic import BaseModel

from meta_compiler.exceptions import ContractValidationError

logger = logging.getLogger("meta_compiler.core.action_registry")


@dataclass(frozen=True)
class ActionSpec:
    """Executable metadata definition associated with a manifest action identifier."""

    action_name: str
    callable_func: Callable[..., Any]
    input_schema: type[BaseModel] | None = None
    output_schema: type[BaseModel] | None = None
    version: str = "1.0.0"

    def __post_init__(self) -> None:
        """Enforces schema type hierarchy validation upon instantiation."""
        if self.input_schema is not None and not (
            isinstance(self.input_schema, type) and issubclass(self.input_schema, BaseModel)
        ):
            raise ContractValidationError(
                f"ActionSpec 'input_schema' for '{self.action_name}' must be a BaseModel subclass.",
                action_name=self.action_name,
                details={"provided_input_schema": repr(self.input_schema)},
            )
        if self.output_schema is not None and not (
            isinstance(self.output_schema, type) and issubclass(self.output_schema, BaseModel)
        ):
            raise ContractValidationError(
                f"ActionSpec 'output_schema' for '{self.action_name}' must be a BaseModel subclass.",
                action_name=self.action_name,
                details={"provided_output_schema": repr(self.output_schema)},
            )


class ActionRegistry:
    """Thread-safe registry mapping action identifiers to callables and schema contracts."""

    def __init__(self) -> None:
        self._actions: dict[str, ActionSpec] = {}
        self._lock = RLock()

    def register(
        self,
        action_name: str,
        callable_func: Callable[..., Any],
        input_schema: type[BaseModel] | None = None,
        output_schema: type[BaseModel] | None = None,
        version: str = "1.0.0",
        allow_override: bool = False,
    ) -> ActionSpec:
        """Registers an executable unit and its boundary schemas under an action key.

        Args:
            action_name: Canonical string identifier for the action.
            callable_func: Executable callable object.
            input_schema: Optional Pydantic BaseModel class for input validation.
            output_schema: Optional Pydantic BaseModel class for output validation.
            version: Semantic version string for the action definition.
            allow_override: If False, raises ContractValidationError when re-registering an existing key.

        Returns:
            The created and registered ActionSpec instance.
        """
        clean_name = action_name.strip()
        if not clean_name:
            raise ContractValidationError("Action name cannot be empty or whitespace.")

        if not callable(callable_func):
            raise ContractValidationError(
                f"Cannot register non-callable object for action '{clean_name}'.",
                action_name=clean_name,
                details={"provided_type": type(callable_func).__name__},
            )

        spec = ActionSpec(
            action_name=clean_name,
            callable_func=callable_func,
            input_schema=input_schema,
            output_schema=output_schema,
            version=version,
        )

        with self._lock:
            if clean_name in self._actions and not allow_override:
                logger.error(
                    "Attempted to override registered action '%s' without allow_override=True",
                    clean_name,
                )
                raise ContractValidationError(
                    f"Action '{clean_name}' is already registered. Set allow_override=True to replace.",
                    action_name=clean_name,
                    details={"existing_version": self._actions[clean_name].version},
                )

            self._actions[clean_name] = spec
            logger.info("Successfully registered action '%s' (v%s)", clean_name, version)

        return spec

    def resolve(self, action_name: str) -> ActionSpec:
        """Resolves an action string to its ActionSpec or raises ContractValidationError."""
        clean_name = action_name.strip()
        with self._lock:
            spec = self._actions.get(clean_name)
            if spec is None:
                logger.error("Action resolution failed for key '%s'", clean_name)
                raise ContractValidationError(
                    f"Action '{clean_name}' is not registered in the ActionRegistry.",
                    action_name=clean_name,
                    details={"registered_actions": list(self._actions.keys())},
                )
            return spec

    def has_action(self, action_name: str) -> bool:
        """Checks if an action key is registered."""
        with self._lock:
            return action_name.strip() in self._actions

    def unregister(self, action_name: str) -> bool:
        """Removes an action from the registry if present."""
        clean_name = action_name.strip()
        with self._lock:
            if clean_name in self._actions:
                del self._actions[clean_name]
                logger.info("Unregistered action '%s'", clean_name)
                return True
            return False

    def clear(self) -> None:
        """Clears all registered actions (primarily for test isolation)."""
        with self._lock:
            self._actions.clear()
            logger.debug("Cleared all actions from ActionRegistry")

    def list_actions(self) -> list[str]:
        """Returns a list of all registered action names."""
        with self._lock:
            return list(self._actions.keys())
