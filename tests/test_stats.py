import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime, UTC

@pytest.fixture
def client(isolated_env):
    from database import get_db
    
    with get_db() as conn:
        conn.execute(
            "INSERT INTO services (id, name, description, price_sats, endpoint_url, provider_wallet, created_at, is_active) VALUES (?,?,?,?,?,?,?,?)",
            ("svc1", "Test", "desc", 100, "http://x", "wallet", datetime.now(UTC).isoformat(), 1)
        )
        conn.execute(
            "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, fee_sats, provider_sats, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
            ("tx1", "svc1", "hash1", 100, 10, 90, "paid", datetime.now(UTC).isoformat())
        )
        conn.execute(
            "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, fee_sats, provider_sats, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
            ("tx2", "svc1", "hash2", 100, 10, 90, "paid", datetime.now(UTC).isoformat())
        )

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

def test_stats_includes_top_rated_when_enough_calls(isolated_env):
    from main import app
    from database import get_db
    
    with get_db() as conn:
        conn.execute(
            "INSERT INTO services (id, name, description, price_sats, endpoint_url, provider_wallet, created_at, is_active, avg_quality_score) VALUES (?,?,?,?,?,?,?,?,?)",
            ("svc1", "Web Summarizer", "desc", 25, "http://x", "wallet", datetime.now(UTC).isoformat(), 1, 88.0)
        )
        # 1 scored transaction (meets minimum of 1)
        conn.execute(
            "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, status, created_at, quality_score) VALUES (?,?,?,?,?,?,?)",
            ("tx0", "svc1", "hash0", 25, "paid", datetime.now(UTC).isoformat(), 88)
        )

    with patch("services.stats.get_marketplace_wallet") as mock_wallet:
        mock_info = MagicMock()
        mock_info.balance_sats = 100
        mock_wallet.return_value.node_info.return_value = mock_info
        client = TestClient(app)
        response = client.get("/api/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["top_rated_name"] == "Web Summarizer"
    assert data["top_rated_tier"] == "bronze"


def test_stats_top_rated_is_none_without_enough_calls(isolated_env):
    from main import app
    from database import get_db
    
    with get_db() as conn:
        conn.execute(
            "INSERT INTO services (id, name, description, price_sats, endpoint_url, provider_wallet, created_at, is_active, avg_quality_score) VALUES (?,?,?,?,?,?,?,?,?)",
            ("svc1", "Web Summarizer", "desc", 25, "http://x", "wallet", datetime.now(UTC).isoformat(), 1, 90.0)
        )
        # No scored transactions

    with patch("services.stats.get_marketplace_wallet") as mock_wallet:
        mock_info = MagicMock()
        mock_info.balance_sats = 0
        mock_wallet.return_value.node_info.return_value = mock_info
        client = TestClient(app)
        response = client.get("/api/stats")

    assert response.json()["top_rated_name"] is None
