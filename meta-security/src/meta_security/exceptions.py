"""Domain exception hierarchy for meta-security."""

from typing import Any


class MetaSecurityError(Exception):
    """Base exception for all meta-security errors."""

    def __init__(
        self,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.context = dict(context) if context is not None else {}


class TokenValidationError(MetaSecurityError):
    """Raised when token signature validation or verification fails."""


class ClaimExtractionError(MetaSecurityError):
    """Raised when the parsed token lacks required fields or fails schema coercion."""


class PolicyViolationError(MetaSecurityError):
    """Raised when a validated identity fails to satisfy the required authorization policy."""