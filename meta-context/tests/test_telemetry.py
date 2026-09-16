"""Tests for meta-telemetry integration helper extractors."""

from __future__ import annotations

from meta_context import TenantContext, bind_context, extract_context_attributes


def test_extract_context_attributes_with_active_context() -> None:
    tenant = TenantContext(tenant_id="tenant_telemetry", organization_id="org_telemetry")
    with bind_context(correlation_id="corr-telemetry-123", tenant_context=tenant, execution_state={"stage": "ingest"}):
        attrs = extract_context_attributes()
        assert attrs["correlation_id"] == "corr-telemetry-123"
        assert attrs["tenant.id"] == "tenant_telemetry"
        assert attrs["tenant.organization_id"] == "org_telemetry"
        assert attrs["context.state.stage"] == "ingest"


def test_extract_context_attributes_empty_context() -> None:
    attrs = extract_context_attributes()
    assert attrs == {}