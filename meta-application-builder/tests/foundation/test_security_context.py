import asyncio

import pytest
from pydantic import ValidationError

from meta_application_builder.foundation.security_context.claims import (
    InvalidTenantIdentifierError,
    SecurityClaims,
    SecurityClaimsException,
)
from meta_application_builder.foundation.security_context.identity import (
    IdentityContextManager,
    UnauthenticatedContextError,
)


def get_valid_claims_dict():
    return {
        "iss": "https://identity.meta.internal",
        "sub": "usr_test123",
        "aud": "meta-application-builder",
        "exp": 1800000000,
        "nbf": 1700000000,
        "iat": 1700000000,
        "jti": "jti_unique_12345",
        "tenant_id": "tenant_acme_corp",
        "roles": ["developer"],
        "permissions": ["bcr:write"],
    }


def test_valid_security_claims_instantiation():
    claims = SecurityClaims(**get_valid_claims_dict())
    assert claims.tenant_id == "tenant_acme_corp"
    assert claims.sub == "usr_test123"


def test_invalid_tenant_format_raises():
    data = get_valid_claims_dict()
    data["tenant_id"] = "invalid-tenant-name!"
    with pytest.raises(ValidationError) as exc_info:
        SecurityClaims(**data)
    assert "Invalid tenant_id" in str(exc_info.value)


def test_invalid_temporal_window_raises():
    data = get_valid_claims_dict()
    data["exp"] = 1600000000  # exp < nbf
    with pytest.raises(ValidationError):
        SecurityClaims(**data)


def test_unauthenticated_identity_access_raises():
    with pytest.raises(UnauthenticatedContextError):
        IdentityContextManager.get_current_identity()


@pytest.mark.asyncio
async def test_identity_context_isolation_across_async_tasks():
    claims_a = SecurityClaims(**get_valid_claims_dict())

    data_b = get_valid_claims_dict()
    data_b["tenant_id"] = "tenant_beta_corp"
    claims_b = SecurityClaims(**data_b)

    async def task_a():
        token = IdentityContextManager.set_current_identity(claims_a)
        await asyncio.sleep(0.01)
        assert IdentityContextManager.get_current_tenant_id() == "tenant_acme_corp"
        IdentityContextManager.reset_identity(token)

    async def task_b():
        token = IdentityContextManager.set_current_identity(claims_b)
        await asyncio.sleep(0.01)
        assert IdentityContextManager.get_current_tenant_id() == "tenant_beta_corp"
        IdentityContextManager.reset_identity(token)

    await asyncio.gather(task_a(), task_b())

@pytest.mark.parametrize("bad_tenant", [
    "tenant_../../admin",
    "tenant_acme/secret",
    "tenant_acme\\root",
    "tenant_acme..corp"
])
def test_tenant_id_path_traversal_rejection(bad_tenant):
    data = get_valid_claims_dict()
    data["tenant_id"] = bad_tenant
    with pytest.raises(ValidationError):
        SecurityClaims(**data)

@pytest.mark.asyncio
async def test_identity_context_manager_scope_cleanup():
    claims = SecurityClaims(**get_valid_claims_dict())
    async with IdentityContextManager.scope(claims):
        assert IdentityContextManager.get_current_tenant_id() == claims.tenant_id

    # Verify context was properly cleared after exiting scope block
    with pytest.raises(UnauthenticatedContextError):
        IdentityContextManager.get_current_identity()