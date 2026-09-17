import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import httpx
from meta_builder_brain.config import BrainSettings
from meta_builder_brain.governance.opa import OPAEvaluator
from meta_builder_brain.exceptions import  OPAPolicyValidationError

@pytest.mark.asyncio
async def test_opa_evaluate_policy_allow(mock_settings: BrainSettings):
    evaluator = OPAEvaluator(mock_settings)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": {"allow": True}}
    mock_response.raise_for_status = lambda: None

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        res = await evaluator.validate_component_governance(
            "urn:meta:bcr:global:user:v1.0", {"type": "object"}
        )
        assert res is True

@pytest.mark.asyncio
async def test_opa_evaluate_policy_deny(mock_settings: BrainSettings):
    evaluator = OPAEvaluator(mock_settings)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": {"allow": False, "reasons": ["Missing primary key"]}
    }
    mock_response.raise_for_status = lambda: None

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        with pytest.raises(OPAPolicyValidationError) as exc_info:
            await evaluator.validate_component_governance(
                "urn:meta:bcr:global:user:v1.0", {"type": "object"}
            )
        assert "Missing primary key" in str(exc_info.value)