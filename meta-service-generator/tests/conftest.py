import pytest
import networkx as nx
from typing import Dict, Any

@pytest.fixture
def base_schema() -> Dict[str, Any]:
    return {
        "title": "User",
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "username": {"type": "string"},
            "email": {"type": "string"},
            "is_active": {"type": "boolean", "default": True},
        },
        "required": ["id", "username"],
    }

@pytest.fixture
def acyclic_dag() -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_edges_from([
        ("user", "order"),
        ("order", "payment"),
        ("order", "shipping"),
        ("payment", "audit_log"),
    ])
    return G

@pytest.fixture
def direct_cycle_graph() -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_edges_from([("A", "B"), ("B", "A")])
    return G

@pytest.fixture
def indirect_cycle_graph() -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_edges_from([("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")])
    return G

@pytest.fixture
def disconnected_graph() -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_edges_from([("A", "B"), ("C", "D")])
    G.add_node("isolated_node")
    return G