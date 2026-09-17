import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from meta_builder_brain.main import app

@pytest.mark.asyncio
async def test_ingest_raw_schema():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "namespace_id": "global",
            "component_name": "user_profile",
            "version": "v1.0",
            "raw_schema": {"type": "object"},
        }
        response = await ac.post("/api/v1/ingest/raw", json=payload)
        assert response.status_code == 201
        assert response.json()["urn"] == "urn:meta:bcr:global:user_profile:v1.0"

@pytest.mark.asyncio
async def test_ingest_rfc():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "raw_rfc_text": "Header: Title\n\nUser ID: string description",
            "namespace_id": "global",
        }
        response = await ac.post("/api/v1/ingest/rfc", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "SYNTHESIZED"

@pytest.mark.asyncio
async def test_compile_namespace_route():
    comp_urn = "urn:meta:bcr:global:entity:v1.0"
    payload = {
        "components": {comp_urn: []},
        "spec_deltas": {comp_urn: {}},
        "base_schemas": {comp_urn: {"type": "object"}},
    }

    mock_compile_result = {
        "job_id": "job_mock_123",
        "namespace_id": "global",
        "execution_order": [comp_urn],
        "artifacts": {comp_urn: {"type": "object"}},
    }

    transport = ASGITransport(app=app)
    with patch(
        "meta_builder_brain.orchestrator.BuildOrchestrator.compile_blueprint_namespace",
        new=AsyncMock(return_value=mock_compile_result),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/v1/compile/global", json=payload)
            assert response.status_code == 200
            assert response.json()["job_id"] == "job_mock_123"