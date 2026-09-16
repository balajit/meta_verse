import httpx
import pytest
import respx

from meta_application_builder.foundation.security_context.claims import SecurityClaims
from meta_application_builder.foundation.security_context.identity import (
    IdentityContextManager,
)
from meta_application_builder.spec_governance.phase_a_static.immutability_eval import (
    GovernanceImmutabilityError,
    ImmutabilityEvaluator,
)
from meta_application_builder.spec_governance.phase_a_static.syntax_checker import (
    GovernanceSyntaxError,
    StaticSyntaxChecker,
)
from meta_application_builder.spec_governance.phase_c_policy.opa_client import (
    GovernancePolicyError,
    OPAGovernanceClient,
)
from meta_application_builder.spec_governance.schemas.det_schema import (
    AttributeDefinition,
    DomainEntityTemplate,
    ImmutabilityTier,
)


@pytest.mark.asyncio
async def test_async_syntax_checker_valid_json():
    raw_json = """
    {
        "urn": "urn:meta:bcr:acme:entities:user",
        "version": "1.0.0",
        "name": "User",
        "immutability_tier": "OVERRIDABLE",
        "attributes": {
            "id": {
                "name": "id",
                "data_type": "string",
                "required": true,
                "immutability_tier": "FINAL"
            }
        },
        "dependencies": []
    }
    """
    model = await StaticSyntaxChecker.parse_and_validate_async(raw_json, "json", "/api/v1/validate")
    assert model.urn == "urn:meta:bcr:acme:entities:user"
    assert model.attributes["id"].immutability_tier == ImmutabilityTier.FINAL


def test_iterative_inheritance_chain_eval():
    root = DomainEntityTemplate(
        urn="urn:meta:bcr:acme:entities:root",
        version="1.0.0",
        name="Root",
        immutability_tier=ImmutabilityTier.OVERRIDABLE,
        attributes={"id": AttributeDefinition(name="id", data_type="string", immutability_tier=ImmutabilityTier.FINAL)},
    )
    middle = DomainEntityTemplate(
        urn="urn:meta:bcr:acme:entities:middle",
        version="1.0.0",
        name="Middle",
        parent_urn=root.urn,
        immutability_tier=ImmutabilityTier.OVERRIDABLE,
        attributes={"id": AttributeDefinition(name="id", data_type="string", immutability_tier=ImmutabilityTier.FINAL)},
    )
    leaf = DomainEntityTemplate(
        urn="urn:meta:bcr:acme:entities:leaf",
        version="1.0.0",
        name="Leaf",
        parent_urn=middle.urn,
        immutability_tier=ImmutabilityTier.OVERRIDABLE,
        attributes={"id": AttributeDefinition(name="id", data_type="string", immutability_tier=ImmutabilityTier.FINAL)},
    )

    # Iterative chain execution without stack recursion
    ImmutabilityEvaluator.evaluate_inheritance_chain([root, middle, leaf], "/api/v1/validate")


@pytest.mark.asyncio
@respx.mock
async def test_opa_client_timeout():
    opa_url = "http://localhost:8181/v1/data/governance/allow"
    claims = SecurityClaims(tenant_id="tenant_alpha", sub="usr_1", iss="auth", aud="builder")
    IdentityContextManager.set_current_claims(claims)

    client = OPAGovernanceClient(opa_url, timeout_seconds=0.01)
    spec = DomainEntityTemplate(
        urn="urn:meta:bcr:acme:entities:user",
        version="1.0.0",
        name="User",
        immutability_tier=ImmutabilityTier.OVERRIDABLE,
    )

    # Simulate Gateway Timeout
    respx.post(opa_url).mock(side_effect=httpx.TimeoutException("Read timeout"))

    with pytest.raises(GovernancePolicyError) as exc_info:
        await client.evaluate_specification(spec, "/api/v1/validate")
    assert exc_info.value.problem.status == 504
    assert "configured 2.0 second limit" in exc_info.value.problem.detail

    await client.close()
    IdentityContextManager.clear()