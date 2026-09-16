"""Tests for TenantContext model validation and immutability."""

from __future__ import annotations

import pytest

from meta_context import ContextValidationError, TenantContext


def test_tenant_context_creation() -> None:
    tenant = TenantContext(
        tenant_id="t_100",
        organization_id="org_500",
        environment="staging",
        attributes={"tier": "enterprise"},
    )
    assert tenant.tenant_id == "t_100"
    assert tenant.organization_id == "org_500"
    assert tenant.environment == "staging"
    assert tenant.get_attribute("tier") == "enterprise"


def test_tenant_context_validation() -> None:
    with pytest.raises(ContextValidationError):
        TenantContext(tenant_id="")

    with pytest.raises(ContextValidationError):
        TenantContext(tenant_id="valid", organization_id="   ")


def test_tenant_context_immutability() -> None:
    tenant = TenantContext(tenant_id="t_100", attributes={"key": "value"})

    with pytest.raises(TypeError):
        tenant.tenant_id = "new_id"  # type: ignore[misc]

    with pytest.raises(TypeError):
        tenant.attributes["key"] = "mutated"  # type: ignore[index]