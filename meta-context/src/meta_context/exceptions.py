"""Domain exception hierarchy for meta-context."""

from __future__ import annotations


class MetaContextError(Exception):
    """Base exception for all meta-context errors."""


class ContextNotSetError(MetaContextError):
    """Raised when attempting to access a context variable that has not been initialized."""


class ContextValidationError(MetaContextError):
    """Raised when validation fails for tenant or execution context data."""


class ContextScopeError(MetaContextError):
    """Raised when context scoping or lifecycle operations encounter an invalid state."""