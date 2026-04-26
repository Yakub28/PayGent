import pytest
import sys
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setattr("database.DB_PATH", str(tmp_path / "test.db"))
    from database import init_db
    init_db()
    
    # Force reload of main to pick up new routers
    modules_to_clear = ["main", "services.admin", "services.registry"]
    for mod in modules_to_clear:
        sys.modules.pop(mod, None)
        
    with patch("services.registry.get_marketplace_wallet") as mock_wallet:
        mock_info = MagicMock()
        mock_info.id = "abc123"
        mock_wallet.return_value.node_info.return_value = mock_info
        from main import app
        yield TestClient(app)


def test_create_provider_returns_key(client):
    response = client.post("/api/admin/providers", json={"company_name": "Anthropic"})
    assert response.status_code == 200
    data = response.json()
    assert data["company_name"] == "Anthropic"
    assert data["api_key"].startswith("pvd_")
    assert "provider_id" in data


def test_create_provider_persists_in_db(client, tmp_path, monkeypatch):
    response = client.post("/api/admin/providers", json={"company_name": "Acme"})
    api_key = response.json()["api_key"]

    from database import get_db
    with get_db() as conn:
        row = conn.execute(
            "SELECT company_name FROM providers WHERE api_key=?", (api_key,)
        ).fetchone()
    assert row is not None
    assert row["company_name"] == "Acme"


def test_create_two_providers_get_unique_keys(client):
    r1 = client.post("/api/admin/providers", json={"company_name": "Acme"})
    r2 = client.post("/api/admin/providers", json={"company_name": "Beta"})
    assert r1.json()["api_key"] != r2.json()["api_key"]
