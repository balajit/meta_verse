"""Domain exception hierarchy for meta-config."""

from typing import Any, Dict, Mapping, Optional, Sequence


class MetaConfigError(Exception):
    """Base exception for all meta-config errors."""

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}


class ConfigValidationError(MetaConfigError):
    """Raised when configuration parsing or validation fails during application boot."""

    def __init__(
        self,
        message: str,
        errors: Sequence[Mapping[str, Any]],
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        ctx = context or {}
        ctx["validation_errors"] = list(errors)
        super().__init__(message, context=ctx)
        self.errors = list(errors)


class SecretInjectionError(MetaConfigError):
    """Raised when secrets cannot be fetched or decrypted from OpenBao."""

    def __init__(self, message: str, secret_path: str, context: Optional[Dict[str, Any]] = None) -> None:
        ctx = context or {}
        ctx["secret_path"] = secret_path
        super().__init__(message, context=ctx)
        self.secret_path = secret_path


class BootConfigurationError(MetaConfigError):
    """Fatal exception raised to immediately halt application boot sequence."""