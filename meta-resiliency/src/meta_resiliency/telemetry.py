"""OpenTelemetry integration utilities and structured logging bindings."""

import logging
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode, Tracer

from meta_context import get_correlation_id, get_execution_state, get_tenant_context
from meta_telemetry import get_tracer

logger = logging.getLogger("meta_resiliency")


def get_resilience_tracer() -> Tracer:
    """Retrieves the resilience tracer dynamically from the global TracerProvider."""
    return get_tracer("meta_resiliency")


def get_observability_context() -> dict[str, Any]:
    """Extracts structured logging metadata from active execution and tenant contexts."""
    ctx_attrs: dict[str, Any] = {}

    cid = get_correlation_id(required=False)
    if cid:
        ctx_attrs["correlation_id"] = cid

    tenant = get_tenant_context(required=False)
    if tenant:
        ctx_attrs["tenant_id"] = tenant.tenant_id
        if getattr(tenant, "organization_id", None):
            ctx_attrs["organization_id"] = tenant.organization_id
        if getattr(tenant, "environment", None):
            ctx_attrs["environment"] = tenant.environment

    state = get_execution_state()
    if state:
        ctx_attrs["execution_state"] = dict(state)

    return ctx_attrs


def log_resilience_event(event_type: str, status: str, metadata: dict[str, Any]) -> None:
    """Emits structured JSON logs enriched with execution and telemetry context."""
    extra_payload: dict[str, Any] = {
        "event_type": event_type,
        "status": status,
        "metadata": metadata,
        **get_observability_context(),
    }
    logger.info("Resilience event [%s]: %s", event_type, status, extra=extra_payload)


def log_resilience_error(event_type: str, error: Exception, metadata: dict[str, Any]) -> None:
    """Emits structured error logs with actionable root-cause metadata for agentic triage."""
    extra_payload: dict[str, Any] = {
        "event_type": event_type,
        "status": "failed",
        "error_type": type(error).__name__,
        "error_message": str(error),
        "metadata": metadata,
        **get_observability_context(),
    }
    logger.error(
        "Resilience failure [%s]: %s",
        event_type,
        str(error),
        extra=extra_payload,
        exc_info=True,
    )


def mark_span_error(span: trace.Span | None, exc: Exception) -> None:
    """Helper to record exception and set status on OpenTelemetry span."""
    if span is not None and span.is_recording():
        span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR, str(exc)))