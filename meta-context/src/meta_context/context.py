"""Central contextvars storage, context propagation mechanics, and OpenTelemetry bridging."""

from __future__ import annotations

import asyncio
from concurrent.futures import Executor
from contextlib import contextmanager
import contextvars
from functools import wraps
import uuid
from typing import Any, Callable, Generator, Mapping, TypeVar, ParamSpec

from meta_context.exceptions import ContextNotSetError, ContextScopeError
from meta_context.types import ContextSnapshot, TenantContext

_CORRELATION_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "meta_context_correlation_id", default=None
)
_TENANT_CONTEXT: contextvars.ContextVar[TenantContext | None] = contextvars.ContextVar(
    "meta_context_tenant", default=None
)
_EXECUTION_STATE: contextvars.ContextVar[Mapping[str, Any] | None] = contextvars.ContextVar(
    "meta_context_execution_state", default=None
)

P = ParamSpec("P")
R = TypeVar("R")


def generate_correlation_id() -> str:
    """Generate a standard RFC 4122 compliant UUIDv4 correlation ID."""
    return str(uuid.uuid4())


def get_correlation_id(required: bool = False) -> str | None:
    """Retrieve active correlation ID.

    :param required: If True, raises ContextNotSetError when correlation_id is None.
    :return: Active correlation ID string, or None if not set.
    """
    cid = _CORRELATION_ID.get()
    if cid is None and required:
        raise ContextNotSetError("No correlation ID found in active context.")
    return cid


def get_tenant_context(required: bool = False) -> TenantContext | None:
    """Retrieve active TenantContext object."""
    tenant = _TENANT_CONTEXT.get()
    if tenant is None and required:
        raise ContextNotSetError("No TenantContext found in active context.")
    return tenant


def get_execution_state() -> Mapping[str, Any]:
    """Retrieve current execution state metadata dictionary."""
    state = _EXECUTION_STATE.get()
    return state if state is not None else {}


def capture_snapshot() -> ContextSnapshot:
    """Capture an immutable snapshot of all active context fields."""
    return ContextSnapshot(
        correlation_id=get_correlation_id(required=False),
        tenant_context=get_tenant_context(required=False),
        execution_state=get_execution_state(),
    )


def _sync_to_opentelemetry_span(
    correlation_id: str | None,
    tenant_context: TenantContext | None,
) -> None:
    """Sync active meta-context attributes to OpenTelemetry span if opentelemetry is installed."""
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
        span = trace.get_current_span()
        if span.is_recording():
            if correlation_id:
                span.set_attribute("correlation_id", correlation_id)
            if tenant_context:
                span.set_attribute("tenant.id", tenant_context.tenant_id)
                if tenant_context.organization_id:
                    span.set_attribute("tenant.organization_id", tenant_context.organization_id)
                span.set_attribute("tenant.environment", tenant_context.environment)
    except ImportError:
        pass


class ContextScope:
    """Active context manager scope holding contextvar tokens for restoration."""

    __slots__ = ("_tokens", "_active")

    def __init__(self, tokens: list[tuple[contextvars.ContextVar[Any], contextvars.Token[Any]]]) -> None:
        self._tokens = tokens
        self._active = True

    def reset(self) -> None:
        """Reset contextvars back to their prior token state."""
        if not self._active:
            raise ContextScopeError("ContextScope has already been reset.")
        for var, token in reversed(self._tokens):
            var.reset(token)
        self._active = False

    @property
    def is_active(self) -> bool:
        """Check if the context scope is currently active."""
        return self._active


@contextmanager
def bind_context(
    correlation_id: str | None = None,
    tenant_context: TenantContext | None = None,
    execution_state: Mapping[str, Any] | None = None,
) -> Generator[ContextScope, None, None]:
    """Bind specified context variables within a managed context block."""
    tokens: list[tuple[contextvars.ContextVar[Any], contextvars.Token[Any]]] = []

    if correlation_id is None:
        existing_id = _CORRELATION_ID.get()
        correlation_id = existing_id if existing_id is not None else generate_correlation_id()

    tokens.append((_CORRELATION_ID, _CORRELATION_ID.set(correlation_id)))

    if tenant_context is not None:
        tokens.append((_TENANT_CONTEXT, _TENANT_CONTEXT.set(tenant_context)))

    if execution_state is not None:
        merged_state = {**get_execution_state(), **execution_state}
        tokens.append((_EXECUTION_STATE, _EXECUTION_STATE.set(merged_state)))

    _sync_to_opentelemetry_span(correlation_id, tenant_context)

    scope = ContextScope(tokens)
    try:
        yield scope
    finally:
        if scope.is_active:
            scope.reset()


def run_with_context(
    snapshot: ContextSnapshot,
    func: Callable[P, R],
    *args: P.args,
    **kwargs: P.kwargs,
) -> R:
    """Execute a function within a context restored from a ContextSnapshot."""
    with bind_context(
        correlation_id=snapshot.correlation_id,
        tenant_context=snapshot.tenant_context,
        execution_state=snapshot.execution_state,
    ):
        return func(*args, **kwargs)


def bind_async_executor(
    executor: Executor,
) -> Executor:
    """Wrap a concurrent.futures.Executor to propagate contextvars across threads."""
    original_submit = executor.submit

    def submit_with_context(
        fn: Callable[P, R],
        *args: P.args,
        **kwargs: P.kwargs
    ) -> Any:
        ctx = contextvars.copy_context()
        return original_submit(ctx.run, fn, *args, **kwargs)

    executor.submit = submit_with_context  # type: ignore[assignment]
    return executor