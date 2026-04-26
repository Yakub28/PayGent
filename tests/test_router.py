import pytest
import sys
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime, UTC

@pytest.fixture
def client(isolated_env):
    for mod in ["main", "services.router"]:
        sys.modules.pop(mod, None)
    
    with patch("services.router.get_marketplace_wallet") as mock_wallet:
        mock_invoice = MagicMock()
        mock_invoice.payment_hash = "abc123hash"
        mock_invoice.invoice = "lnbc250n1..."
        mock_wallet.return_value.create_invoice.return_value = mock_invoice
        from main import app
        yield TestClient(app)

def test_call_without_auth_returns_402(client):
    from database import get_db
    with get_db() as conn:
        conn.execute(
            "INSERT INTO services (id, name, description, price_sats, endpoint_url, provider_wallet, created_at, is_active) VALUES (?,?,?,?,?,?,?,?)",
            ("svc1", "Test", "desc", 25, "http://localhost:8000/api/providers/test", "wallet_abc", datetime.now(UTC).isoformat(), 1)
        )
    
    response = client.post("/api/services/svc1/call", json={"input": "hello"})
    assert response.status_code == 402
    www_auth = response.headers.get("WWW-Authenticate", "")
    assert "macaroon=" in www_auth
    assert "invoice=" in www_auth

def test_call_unknown_service_returns_404(client):
    response = client.post("/api/services/nonexistent/call", json={"input": "x"})
    assert response.status_code == 404

def test_call_with_valid_payment_returns_provider_response(client):
    from database import get_db
    with get_db() as conn:
        conn.execute(
            "INSERT INTO services (id, name, description, price_sats, endpoint_url, provider_wallet, created_at, is_active) VALUES (?,?,?,?,?,?,?,?)",
            ("svc1", "Test", "desc", 100, "http://localhost:8000/api/providers/test", "wallet_abc", datetime.now(UTC).isoformat(), 1)
        )

    import services.router as router_module
    macaroon = "testmacaroon=="
    router_module.pending_payments[macaroon] = {
        "payment_hash": "paidhash123",
        "service_id": "svc1",
        "txn_id": "txn-test-uuid",
    }

    with patch("services.router._verify_payment", return_value=True), \
         patch("services.router._call_provider", return_value={"result": "ok"}), \
         patch("services.router._pay_provider"), \
         patch("services.router.score_and_update"), \
         patch("services.router._settle_provider", return_value=(10, 90)):
        
        response = client.post(
            "/api/services/svc1/call",
            json={"input": "hello"},
            headers={"Authorization": f"L402 {macaroon}:deadbeef"}
        )

    assert response.status_code == 200
    assert response.json() == {"result": "ok"}
