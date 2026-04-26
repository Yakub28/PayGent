import pytest
from fastapi.testclient import TestClient
from datetime import datetime, UTC
from unittest.mock import patch

@pytest.fixture
def client(tmp_path, monkeypatch):
    # Setup tmp database
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("database.DB_PATH", db_path)
    
    # Setup tmp mock lightning file
    lightning_path = str(tmp_path / "mock_lightning.json")
    monkeypatch.setattr("services.mock_wallet.STATE_FILE", lightning_path)
    
    from database import init_db
    init_db()
    
    import sys
    # Clear modules to ensure fresh import with mocked paths
    for mod in ["main", "services.agents", "services.wallet_manager", "services.mock_wallet"]:
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
    found = next(a for i, a in enumerate(agents) if a["id"] == data["id"])
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
