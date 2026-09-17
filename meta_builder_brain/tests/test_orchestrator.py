import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession
from meta_builder_brain.config import BrainSettings
from meta_builder_brain.orchestrator import BuildOrchestrator


@pytest.mark.asyncio
async def test_orchestrator_compile_namespace_success(
        mock_settings: BrainSettings, async_session: AsyncSession
):
    orchestrator = BuildOrchestrator(mock_settings)

    comp_urn = "urn:meta:bcr:global:test_comp:v1.0"
    components = {comp_urn: []}
    base_schemas = {
        comp_urn: {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }
    }
    spec_deltas = {
        comp_urn: {"properties": {"age": {"type": "integer"}}}
    }

    with patch.object(
            orchestrator.opa_evaluator,
            "validate_component_governance",
            new=AsyncMock(return_value=True),
    ):
        result = await orchestrator.compile_blueprint_namespace(
            session=async_session,
            job_id="job_test_001",
            namespace_id="global",
            components=components,
            spec_deltas=spec_deltas,
            base_schemas=base_schemas,
        )

        assert result["job_id"] == "job_test_001"
        assert comp_urn in result["artifacts"]
        assert "properties" in result["artifacts"][comp_urn]