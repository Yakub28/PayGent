import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

@pytest.fixture
def client(tmp_path, monkeypatch):
    import sys
    monkeypatch.setattr("database.DB_PATH", str(tmp_path / "test.db"))
    from database import init_db
    init_db()
    # Remove cached modules so main/registry are freshly imported under the patch
    for mod in list(sys.modules.keys()):
        if mod in ("main", "services.registry"):
            del sys.modules[mod]
    with patch("services.registry.get_marketplace_wallet") as mock_wallet:
        mock_info = MagicMock()
        mock_info.node_pk = "abc123"
        mock_wallet.return_value.node_info.return_value = mock_info
        from main import app
        yield TestClient(app)

def test_register_service(client):
    response = client.post("/api/services/register", json={
        "name": "Test Service",
        "description": "A test",
        "price_sats": 25,
        "endpoint_url": "http://localhost:8000/api/providers/test"
    })
    assert response.status_code == 200
    data = response.json()
    assert "service_id" in data
    assert "provider_wallet" in data

def test_list_services(client):
    client.post("/api/services/register", json={
        "name": "Test Service",
        "description": "A test",
        "price_sats": 25,
        "endpoint_url": "http://localhost:8000/api/providers/test"
    })
    response = client.get("/api/services")
    assert response.status_code == 200
    services = response.json()
    assert len(services) == 1
    assert services[0]["name"] == "Test Service"
    assert "endpoint_url" not in services[0]

def test_list_services_excludes_inactive(client):
    r = client.post("/api/services/register", json={
        "name": "To Delete",
        "description": "x",
        "price_sats": 10,
        "endpoint_url": "http://x"
    })
    service_id = r.json()["service_id"]
    client.delete(f"/api/services/{service_id}")
    response = client.get("/api/services")
    assert response.json() == []
