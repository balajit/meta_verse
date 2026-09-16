"""Security policy wrappers and RBAC execution barriers."""

import asyncio
import logging
from functools import wraps
from typing import Any, Callable, TypeVar, cast

from meta_security.claims import TokenClaims
from meta_security.exceptions import PolicyViolationError
from meta_telemetry import trace_span

logger = logging.getLogger("meta_security")

F = TypeVar("F", bound=Callable[..., Any])


def _extract_policy_telemetry(
    params: dict[str, Any],
) -> dict[str, Any]:
    """Capture policy evaluation span attributes securely."""
    claims = params.get("claims")

    if not isinstance(claims, TokenClaims):
        return {
            "policy.required_roles": params.get("required_roles"),
            "subject.id": "unknown",
        }

    return {
        "policy.required_roles": params.get("required_roles"),
        "subject.id": claims.sub,
    }


def require_roles(
    required_roles: list[str],
) -> Callable[[F], F]:
    """Decorator to enforce strictly defined RBAC roles on a function executing with a validated identity.

    Expects the wrapped function to accept a `claims` parameter of type TokenClaims.
    """

    if not required_roles:
        raise ValueError("required_roles must contain at least one role.")

    if any(not isinstance(role, str) or not role.strip() for role in required_roles):
        raise ValueError("required_roles must contain only non-empty strings.")

    normalized_required_roles = tuple(dict.fromkeys(required_roles))

    def _missing_roles(claims: TokenClaims) -> tuple[str, ...]:
        claim_roles = frozenset(claims.roles)
        return tuple(
            role
            for role in normalized_required_roles
            if role not in claim_roles
        )

    def _raise_policy_violation(
        claims: TokenClaims,
        missing_roles: tuple[str, ...],
    ) -> None:
        err_msg = (
            "Subject lacks required operational roles: "
            f"{list(missing_roles)}"
        )

        logger.warning(
            "Security policy violation intercepted",
            extra={
                "event_type": "rbac_policy_violation",
                "subject": claims.sub,
                "missing_roles": list(missing_roles),
            },
        )

        raise PolicyViolationError(
            err_msg,
            context={
                "subject": claims.sub,
                "missing_roles": list(missing_roles),
            },
        )

    def decorator(func: F) -> F:
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            @trace_span(
                name="enforce_rbac_policy",
                extract_attributes=_extract_policy_telemetry,
            )
            async def async_wrapper(
                claims: TokenClaims,
                *args: Any,
                **kwargs: Any,
            ) -> Any:
                if not isinstance(claims, TokenClaims):
                    raise TypeError(
                        "The claims parameter must be a TokenClaims instance."
                    )

                missing_roles = _missing_roles(claims)

                if missing_roles:
                    _raise_policy_violation(claims, missing_roles)

                return await func(claims, *args, **kwargs)

            return cast(F, async_wrapper)

        @wraps(func)
        @trace_span(
            name="enforce_rbac_policy",
            extract_attributes=_extract_policy_telemetry,
        )
        def wrapper(
            claims: TokenClaims,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            if not isinstance(claims, TokenClaims):
                raise TypeError(
                    "The claims parameter must be a TokenClaims instance."
                )

            missing_roles = _missing_roles(claims)

            if missing_roles:
                _raise_policy_violation(claims, missing_roles)

            return func(claims, *args, **kwargs)

        return cast(F, wrapper)

    return decorator
