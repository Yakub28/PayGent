import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys

@pytest.fixture
def client(isolated_env):
    # isolated_env in conftest already set up fresh DB
    for mod in ["main", "services.registry"]:
        sys.modules.pop(mod, None)
    
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


def test_update_price_within_ceiling_succeeds(client):
    r = client.post("/api/services/register", json={
        "name": "Test Service",
        "description": "A test",
        "price_sats": 50,
        "endpoint_url": "http://localhost:8000/api/providers/test"
    })
    service_id = r.json()["service_id"]

    response = client.patch(f"/api/services/{service_id}/price", json={"price_sats": 100})
    assert response.status_code == 200
    data = response.json()
    assert data["price_sats"] == 100
    assert data["tier"] == "bronze"
    assert data["tier_ceiling"] == 150


def test_update_price_exceeds_bronze_ceiling_returns_400(client):
    r = client.post("/api/services/register", json={
        "name": "Test Service",
        "description": "A test",
        "price_sats": 50,
        "endpoint_url": "http://localhost:8000/api/providers/test"
    })
    service_id = r.json()["service_id"]

    response = client.patch(f"/api/services/{service_id}/price", json={"price_sats": 200})
    assert response.status_code == 400
    assert "Bronze" in response.json()["detail"]
    assert "150" in response.json()["detail"]


def test_update_price_unknown_service_returns_404(client):
    response = client.patch("/api/services/nonexistent/price", json={"price_sats": 50})
    assert response.status_code == 404


def test_list_services_includes_tier_and_call_count(client):
    client.post("/api/services/register", json={
        "name": "Test Service",
        "description": "A test",
        "price_sats": 25,
        "endpoint_url": "http://localhost:8000/api/providers/test"
    })
    response = client.get("/api/services")
    assert response.status_code == 200
    svc = response.json()[0]
    assert svc["tier"] == "bronze"
    assert "call_count" in svc
    assert "avg_quality_score" in svc
