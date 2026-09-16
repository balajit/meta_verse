"""Pytest fixtures for context cleanup."""

from __future__ import annotations

from typing import Generator
import pytest

from meta_context.context import _CORRELATION_ID, _EXECUTION_STATE, _TENANT_CONTEXT


@pytest.fixture(autouse=True)
def reset_contextvars() -> Generator[None, None, None]:
    """Ensure contextvars are completely clean before and after each test."""
    t1 = _CORRELATION_ID.set(None)
    t2 = _TENANT_CONTEXT.set(None)
    t3 = _EXECUTION_STATE.set(None)
    try:
        yield
    finally:
        _CORRELATION_ID.reset(t1)
        _TENANT_CONTEXT.reset(t2)
        _EXECUTION_STATE.reset(t3)