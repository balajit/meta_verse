"""Unit tests for telemetry context propagation and span error recording."""

from unittest.mock import MagicMock, patch
from meta_resiliency.telemetry import (
    get_observability_context,
    log_resilience_error,
    log_resilience_event,
    mark_span_error,
)


def test_telemetry_observability_context_full() -> None:
    tenant_mock = MagicMock()
    tenant_mock.tenant_id = "tenant-123"
    tenant_mock.organization_id = "org-456"
    tenant_mock.environment = "production"

    with patch("meta_resiliency.telemetry.get_correlation_id", return_value="corr-789"), \
            patch("meta_resiliency.telemetry.get_tenant_context", return_value=tenant_mock), \
            patch("meta_resiliency.telemetry.get_execution_state", return_value={"step": "execution"}):
        ctx = get_observability_context()
        assert ctx["correlation_id"] == "corr-789"
        assert ctx["tenant_id"] == "tenant-123"
        assert ctx["organization_id"] == "org-456"
        assert ctx["environment"] == "production"
        assert ctx["execution_state"] == {"step": "execution"}


def test_telemetry_span_recording() -> None:
    mock_span = MagicMock()
    mock_span.is_recording.return_value = True

    exc = ValueError("Span error")
    mark_span_error(mock_span, exc)

    mock_span.record_exception.assert_called_once_with(exc)
    mock_span.set_status.assert_called_once()


def test_telemetry_logging_invocations() -> None:
    log_resilience_event("event_type", "ok", {"meta": "data"})
    log_resilience_error("event_error", RuntimeError("err"), {"meta": "data"})