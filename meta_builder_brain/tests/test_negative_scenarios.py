"""Comprehensive test suite validating negative paths across meta_builder_brain modules."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import httpx

from meta_builder_brain.config import BrainSettings, bootstrap_configuration
from meta_builder_brain.telemetry import setup_telemetry
from meta_builder_brain.dag_engine import ComponentDAGEngine
from meta_builder_brain.governance.opa import OPAEvaluator
from meta_builder_brain.persistence.models import Base
from meta_builder_brain.persistence.orm_builder import DynamicMetaclassBuilder
from meta_builder_brain.ingestion.hermes import HermesSynthesisAgent

from meta_builder_brain.exceptions import (
    ConfigurationError,
    TelemetryInitError,
    DAGCycleError,
    DAGNodeNotFoundError,
    EmptyDAGError,
    GovernancePolicyViolationError,
    OPAServiceUnavailableError,
    PersistenceError,
    UnsupportedTypeMappingError,
    HermesSynthesisError,
)


# --- 1. Configuration & Telemetry Tests ---

def test_config_bootstrap_failure():
    with patch("meta_builder_brain.config.BrainSettings", side_effect=Exception("Env loading failed")):
        with pytest.raises(ConfigurationError) as exc_info:
            bootstrap_configuration()
        assert "Unexpected error bootstrapping BrainSettings" in str(exc_info.value)


def test_telemetry_invalid_log_level():
    with pytest.raises(TelemetryInitError) as exc_info:
        setup_telemetry(log_level="INVALID_LEVEL_NAME")
    assert "Invalid log level" in str(exc_info.value)


def test_telemetry_file_permission_denied():
    with patch("os.makedirs", side_effect=OSError("Permission denied")):
        with pytest.raises(TelemetryInitError) as exc_info:
            setup_telemetry(log_level="INFO", log_file_path="/sys/forbidden.log")
        assert "Cannot write logs to file path" in str(exc_info.value)


# --- 2. DAG Engine Tests ---

def test_dag_empty_execution():
    dag = ComponentDAGEngine()
    with pytest.raises(EmptyDAGError) as exc_info:
        dag.compute_execution_order()
    assert "Cannot compute execution order on an empty graph" in str(exc_info.value)


def test_dag_cyclical_dependency():
    dag = ComponentDAGEngine()
    dag.add_component("A", ["B"])
    dag.add_component("B", ["C"])
    dag.add_component("C", ["A"])

    with pytest.raises(DAGCycleError) as exc_info:
        dag.compute_execution_order()
    assert "Cyclic dependency detected" in str(exc_info.value)


def test_dag_missing_node_queries():
    dag = ComponentDAGEngine()
    dag.add_component("A", [])

    with pytest.raises(DAGNodeNotFoundError) as exc_info:
        dag.get_upstream_dependencies("NON_EXISTENT_NODE")
    assert "not found in DAG engine" in str(exc_info.value)


# --- 3. OPA Governance Tests ---

@pytest.mark.asyncio
async def test_opa_service_unreachable(mock_settings: BrainSettings):
    evaluator = OPAEvaluator(mock_settings)
    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection refused")):
        with pytest.raises(OPAServiceUnavailableError) as exc_info:
            await evaluator.validate_component_governance("urn:meta:bcr:a", {})
        assert "unreachable" in str(exc_info.value)


@pytest.mark.asyncio
async def test_opa_policy_denial(mock_settings: BrainSettings):
    evaluator = OPAEvaluator(mock_settings)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": {"allow": False, "reasons": ["Missing required field 'owner'"]}
    }
    mock_response.raise_for_status = lambda: None

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        with pytest.raises(GovernancePolicyViolationError) as exc_info:
            await evaluator.validate_component_governance("urn:meta:bcr:a", {})
        assert "Missing required field 'owner'" in str(exc_info.value)


# --- 4. Dynamic ORM Persistence Tests ---

def test_orm_builder_empty_class_name():
    with pytest.raises(PersistenceError) as exc_info:
        DynamicMetaclassBuilder.create_orm_model("", "user_table", {}, Base)
    assert "class_name identifier cannot be empty" in str(exc_info.value)


def test_orm_builder_unsupported_type():
    fields = {"unsupported_col": {"type": "unknown_type"}}
    with pytest.raises(UnsupportedTypeMappingError) as exc_info:
        DynamicMetaclassBuilder.create_orm_model("CustomModel", "custom_table", fields, Base)
    assert "Unsupported dynamic field type 'unknown_type'" in str(exc_info.value)


def test_orm_builder_invalid_field_format():
    fields = {"invalid_col": 12345}
    with pytest.raises(PersistenceError) as exc_info:
        DynamicMetaclassBuilder.create_orm_model("CustomModel", "custom_table", fields, Base)
    assert "Invalid specification format for field 'invalid_col'" in str(exc_info.value)


# --- 5. Hermes Ingestion Tests ---

@pytest.mark.asyncio
async def test_hermes_empty_payload():
    agent = HermesSynthesisAgent()
    with pytest.raises(HermesSynthesisError) as exc_info:
        await agent.synthesize_rfc_spec("")
    assert "RFC text payload cannot be empty" in str(exc_info.value)


@pytest.mark.asyncio
async def test_hermes_unparseable_text():
    agent = HermesSynthesisAgent()
    with pytest.raises(HermesSynthesisError) as exc_info:
        await agent.synthesize_rfc_spec("Text without key-value specs")
    assert "Failed to extract valid key-value schema definitions" in str(exc_info.value)