"""Shared test fixtures for the meta_compiler test suite."""

from typing import Any

import pytest
from pydantic import BaseModel

from meta_compiler.core.action_registry import ActionRegistry


class RecordingSession:
    """Fake AsyncSession capturing executed statements and transaction calls."""

    def __init__(self) -> None:
        self.executed: list[Any] = []
        self.commits = 0
        self.closed = False

    async def execute(self, stmt: Any) -> None:
        self.executed.append(stmt)

    async def commit(self) -> None:
        self.commits += 1

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def recording_session() -> RecordingSession:
    """Returns a fresh fake AsyncSession recording executed statements."""
    return RecordingSession()


class IntOut(BaseModel):
    value: int


class StrIn(BaseModel):
    value: str


class IntIn(BaseModel):
    value: int


def _noop(**kwargs: Any) -> None:
    return None


@pytest.fixture
def action_registry() -> ActionRegistry:
    """An ActionRegistry pre-loaded with schema-less domain actions."""
    reg = ActionRegistry()
    reg.register("alpha", _noop)
    reg.register("beta", _noop)
    reg.register("gamma", _noop)
    return reg


@pytest.fixture
def typed_registry() -> ActionRegistry:
    """A registry with typed (int-out -> str-in) boundary contracts."""
    reg = ActionRegistry()
    reg.register("int_producer", _noop, output_schema=IntOut)
    reg.register("str_consumer", _noop, input_schema=StrIn)
    return reg


def manifest_yaml(tasks: str, name: str = "wf") -> str:
    """Builds a valid manifest YAML document for the given task lines."""
    return f'version: "v1"\nnamespace: "ns"\nname: "{name}"\nentities: {{}}\ntasks:\n{tasks}'


def chain_manifest() -> str:
    """Two chained schema-less tasks: produce -> consume."""
    return manifest_yaml(
        '  - id: "produce"\n    action: "alpha"\n'
        '  - id: "consume"\n    action: "beta"\n'
        '    depends_on: ["produce"]\n'
    )
