import pytest
from fastapi.testclient import TestClient
import sys

@pytest.fixture
def client(isolated_env):
    # isolated_env fixture in conftest already set up DB and monkeypatched env
    # but we need to ensure 'main' is re-imported if it was cleared
    for mod in ["main", "services.agents"]:
        sys.modules.pop(mod, None)
    from main import app
    return TestClient(app)

def test_create_agent_sets_initial_balance(client):
    payload = {
        "name": "Test Consumer",
        "role": "consumer",
        "initial_balance_sats": 5000
    }
    response = client.post("/api/agents", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["balance_sats"] == 5000
    
    # Verify via list_agents too
    resp_list = client.get("/api/agents")
    assert resp_list.status_code == 200
    agents = resp_list.json()
    found = next(a for a in agents if a["id"] == data["id"])
    assert found["balance_sats"] == 5000

def test_create_provider_sets_initial_balance(client):
    payload = {
        "name": "Test Provider",
        "role": "provider",
        "service_type": "summarizer",
        "initial_balance_sats": 1000
    }
    response = client.post("/api/agents", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["balance_sats"] == 1000
