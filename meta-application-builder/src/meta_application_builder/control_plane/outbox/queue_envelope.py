from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog
from opentelemetry import propagate
from pydantic import BaseModel, ConfigDict, Field

HAS_OTEL:bool = False

# try:
#     #from opentelemetry import propagate, trace
#     #from opentelemetry.context import Context
#     HAS_OTEL = True
# except ImportError:
#     HAS_OTEL = False

logger = structlog.get_logger(__name__)


class QueueEnvelope(BaseModel):
    """
    Standardized message envelope carrying event payloads, W3C distributed tracing context,
    and multi-tenant correlation IDs across asynchronous compilation and execution boundaries.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_type: str = Field(..., min_length=1, max_length=128)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Explicit Correlation Context
    tenant_id: str = Field(..., description="Multi-tenant isolation identifier")
    job_id: Optional[str] = Field(default=None, description="Async compilation job identifier")
    saga_id: Optional[str] = Field(default=None, description="Orchestrated saga transaction identifier")
    causation_id: Optional[str] = Field(default=None, description="Direct upstream event identifier triggering this message")

    # W3C Distributed Tracing Headers (traceparent, tracestate)
    trace_headers: Dict[str, str] = Field(
        default_factory=dict,
        description="Standardized W3C propagation headers (traceparent, tracestate)"
    )

    payload: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create_with_trace_context(
        cls,
        event_type: str,
        tenant_id: str,
        payload: Dict[str, Any],
        job_id: Optional[str] = None,
        saga_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        additional_headers: Optional[Dict[str, str]] = None,
    ) -> QueueEnvelope:
        """
        Factory method that captures active OpenTelemetry context, injecting W3C traceparent/tracestate
        headers along with correlation IDs into the envelope.
        """
        headers: Dict[str, str] = dict(additional_headers or {})

        if HAS_OTEL:
            propagate.inject(headers)

        envelope = cls(
            event_type=event_type,
            tenant_id=tenant_id,
            job_id=job_id,
            saga_id=saga_id,
            causation_id=causation_id,
            trace_headers=headers,
            payload=payload,
        )
        logger.debug(
            "created_queue_envelope",
            event_id=str(envelope.event_id),
            event_type=envelope.event_type,
            tenant_id=envelope.tenant_id,
            has_traceparent="traceparent" in envelope.trace_headers,
        )
        return envelope

    def extract_trace_context(self) -> Any:
        """
        Extracts OpenTelemetry Context from W3C trace_headers to bind downstream async worker spans.
        """
        if HAS_OTEL:
            return propagate.extract(self.trace_headers)
        return None