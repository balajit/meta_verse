import pytest
from experience.api_gateway.submit_endpoint import BuildSubmitRequest
from experience.api_gateway.submit_endpoint import router as submit_router
from experience.cli_tool.direct_mode import DirectModeExecutionError, DirectModeRunner
from fastapi import FastAPI
from fastapi.testclient import TestClient

app_test = FastAPI()
app_test.include_router(submit_router)
client = TestClient(app_test)

def test_submit_endpoint_success():
    headers = {"X-Idempotency-Key": "test-key-123"}
    payload = {"blueprint_id": "bp-001", "spec_payload": {"model": "User"}}
    response = client.post("/v1/build/submit", json=payload, headers=headers)
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "QUEUED"

def test_submit_endpoint_missing_idempotency_key():
    payload = {"blueprint_id": "bp-001", "spec_payload": {}}
    response = client.post("/v1/build/submit", json=payload)
    assert response.status_code == 400

def test_direct_mode_runner_missing_file(tmp_path):
    bad_path = tmp_path / "nonexistent.yaml"
    out_dir = tmp_path / "out"
    with pytest.raises(DirectModeExecutionError):
        DirectModeRunner.execute_local_build(bad_path, out_dir)