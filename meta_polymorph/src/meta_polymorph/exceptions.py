"""Domain exception hierarchy for meta_polymorph."""

from typing import Any, Optional


class PolymorphicError(Exception):
    """Base exception for all meta_polymorph domain errors."""

    pass


class PolymorphicCompilationError(PolymorphicError):
    """Raised when a hydrated polymorphic payload fails to compile into ManifestIR."""

    def __init__(
        self,
        message: str,
        tenant_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.tenant_id = tenant_id
        self.entity_id = entity_id
        self.original_exception = original_exception

    def to_agent_context(self) -> dict[str, Any]:
        """Returns structured JSON-serializable metadata for automated agentic triage."""
        return {
            "error_type": self.__class__.__name__,
            "message": str(self),
            "tenant_id": self.tenant_id,
            "entity_id": self.entity_id,
            "original_exception_type": type(self.original_exception).__name__ if self.original_exception else None,
            "original_exception_details": str(self.original_exception) if self.original_exception else None,
        }

    def __str__(self) -> str:
        ctx = []
        if self.tenant_id:
            ctx.append(f"tenant_id='{self.tenant_id}'")
        if self.entity_id:
            ctx.append(f"entity_id='{self.entity_id}'")

        context_str = f" [{', '.join(ctx)}]" if ctx else ""
        return f"{super().__str__()}{context_str}"