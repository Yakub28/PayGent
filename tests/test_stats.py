import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("database.DB_PATH", str(tmp_path / "test.db"))
    from database import init_db, get_db
    from datetime import datetime
    init_db()

    with get_db() as conn:
        conn.execute(
            "INSERT INTO services (id, name, description, price_sats, endpoint_url, provider_wallet, created_at, is_active) VALUES (?,?,?,?,?,?,?,?)",
            ("svc1", "Test", "desc", 100, "http://x", "wallet", datetime.utcnow().isoformat(), 1)
        )
        conn.execute(
            "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, fee_sats, provider_sats, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
            ("tx1", "svc1", "hash1", 100, 10, 90, "paid", datetime.utcnow().isoformat())
        )
        conn.execute(
            "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, fee_sats, provider_sats, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
            ("tx2", "svc1", "hash2", 100, 10, 90, "paid", datetime.utcnow().isoformat())
        )

    import sys
    sys.modules.pop("main", None)

    with patch("services.stats.get_marketplace_wallet") as mock_wallet:
        mock_info = MagicMock()
        mock_info.balance_sats = 500
        mock_wallet.return_value.node_info.return_value = mock_info
        from main import app
        yield TestClient(app)

def test_stats_returns_correct_totals(client):
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_volume_sats"] == 200
    assert data["total_fees_sats"] == 20
    assert data["total_calls"] == 2
    assert data["marketplace_balance_sats"] == 500

def test_transactions_returns_list(client):
    response = client.get("/api/transactions")
    assert response.status_code == 200
    txns = response.json()
    assert len(txns) == 2
    assert txns[0]["status"] == "paid"
