import pytest
from meta_builder_brain.dag_engine import TreeResolver, DAGCycleError, InvalidURNError
from meta_builder_brain.exceptions import DAGCycleError

def test_validate_urn_success():
    urn = "urn:meta:bcr:global:user_entity:v1.0"
    parsed = TreeResolver.validate_urn(urn)
    assert parsed["namespace"] == "global"
    assert parsed["component"] == "user_entity"
    assert parsed["version"] == "v1.0"

def test_validate_urn_failure():
    with pytest.raises(InvalidURNError):
        TreeResolver.validate_urn("invalid:urn:format")

def test_build_and_validate_dag_success():
    comp_a = "urn:meta:bcr:global:comp_a:v1.0"
    comp_b = "urn:meta:bcr:global:comp_b:v1.0"
    components = {
        comp_a: [comp_b],
        comp_b: [],
    }
    dag_graph = TreeResolver.build_and_validate_dag(components)
    assert dag_graph.execution_order == [comp_b, comp_a]

def test_build_and_validate_dag_cycle_detected():
    comp_a = "urn:meta:bcr:global:comp_a:v1.0"
    comp_b = "urn:meta:bcr:global:comp_b:v1.0"
    components = {
        comp_a: [comp_b],
        comp_b: [comp_a],
    }
    with pytest.raises(DAGCycleError):
        TreeResolver.build_and_validate_dag(components)