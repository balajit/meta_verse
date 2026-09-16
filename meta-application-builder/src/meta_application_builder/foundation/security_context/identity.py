from __future__ import annotations

import contextvars
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Final, Optional

from meta_application_builder.foundation.security_context.claims import SecurityClaims


class UnauthenticatedContextError(Exception):
    """Raised when an operation requires an identity context but none is registered."""
    pass


# Thread/Async Task isolated storage for active identity claims
_SECURITY_CONTEXT: Final[contextvars.ContextVar[Optional[SecurityClaims]]] = contextvars.ContextVar(
    "security_context", default=None
)


class IdentityContextManager:
    """
    Manages task-isolated workload context propagation across async execution threads.
    Guarantees thread-safe access and zero leakages between concurrent requests.
    """

    @staticmethod
    def set_current_identity(claims: SecurityClaims) -> contextvars.Token[Optional[SecurityClaims]]:
        """Sets the validated claims context for the active execution chain."""
        return _SECURITY_CONTEXT.set(claims)

    @staticmethod
    def get_current_identity() -> SecurityClaims:
        """
        Retrieves active context or raises UnauthenticatedContextError.

        Edge Case / Failure Mode:
            Prevents unauthenticated code execution paths from silently operating
            without a tenant boundary context.
        """
        claims = _SECURITY_CONTEXT.get()
        if claims is None:
            raise UnauthenticatedContextError(
                "Execution context error: Unauthenticated request attempt. No identity claims registered."
            )
        return claims

    @staticmethod
    def get_current_tenant_id() -> str:
        """Direct accessor for active tenant_id."""
        return IdentityContextManager.get_current_identity().tenant_id

    @staticmethod
    def get_current_principal() -> str:
        """Direct accessor for active principal identity."""
        return IdentityContextManager.get_current_identity().principal

    @staticmethod
    def reset_identity(token: contextvars.Token[Optional[SecurityClaims]]) -> None:
        """Clears claims context upon request or background task cleanup."""
        _SECURITY_CONTEXT.reset(token)

    @classmethod
    @asynccontextmanager
    async def scope(cls, claims: SecurityClaims) -> AsyncGenerator[SecurityClaims, None]:
        """
        RAII async context manager enforcing token cleanup via try...finally
        to prevent cross-task leakage in worker pools.
        """
        token = cls.set_current_identity(claims)
        try:
            yield claims
        finally:
            cls.reset_identity(token)