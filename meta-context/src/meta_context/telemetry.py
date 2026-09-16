"""Integration helpers for meta-telemetry and OpenTelemetry."""

from __future__ import annotations

from typing import Any, Dict

from meta_context.context import get_correlation_id, get_execution_state, get_tenant_context


def extract_context_attributes(params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Extractor callback suitable for use with meta-telemetry's @trace_span decorator.

    Injects active tenant_id, organization_id, environment, and correlation_id into span attributes.
    """
    attributes: Dict[str, Any] = {}

    cid = get_correlation_id(required=False)
    if cid:
        attributes["correlation_id"] = cid

    tenant = get_tenant_context(required=False)
    if tenant:
        attributes["tenant.id"] = tenant.tenant_id
        if tenant.organization_id:
            attributes["tenant.organization_id"] = tenant.organization_id
        attributes["tenant.environment"] = tenant.environment

    state = get_execution_state()
    for k, v in state.items():
        if isinstance(v, (str, int, float, bool)):
            attributes[f"context.state.{k}"] = v

    return attributes