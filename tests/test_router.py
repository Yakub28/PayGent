import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("database.DB_PATH", str(tmp_path / "test.db"))
    from database import init_db, get_db
    import uuid
    from datetime import datetime
    init_db()

    with get_db() as conn:
        conn.execute(
            "INSERT INTO services VALUES (?,?,?,?,?,?,?,?)",
            ("svc1", "Test", "desc", 25,
             "http://localhost:8000/api/providers/test",
             "wallet_abc", datetime.utcnow().isoformat(), 1)
        )

    import sys
    for mod in ["main", "services.router", "services.registry"]:
        sys.modules.pop(mod, None)

    with patch("services.router.get_marketplace_wallet") as mock_wallet:
        mock_invoice = MagicMock()
        mock_invoice.payment_hash = "abc123hash"
        mock_invoice.invoice = "lnbc250n1..."
        mock_wallet.return_value.create_invoice.return_value = mock_invoice
        from main import app
        yield TestClient(app)

def test_call_without_auth_returns_402(client):
    response = client.post("/api/services/svc1/call", json={"input": "hello"})
    assert response.status_code == 402
    www_auth = response.headers.get("WWW-Authenticate", "")
    assert "macaroon=" in www_auth
    assert "invoice=" in www_auth

def test_call_unknown_service_returns_404(client):
    response = client.post("/api/services/nonexistent/call", json={"input": "x"})
    assert response.status_code == 404

def test_call_with_valid_payment_returns_provider_response(tmp_path, monkeypatch):
    monkeypatch.setattr("database.DB_PATH", str(tmp_path / "test.db"))
    from database import init_db, get_db
    import uuid
    from datetime import datetime
    init_db()

    with get_db() as conn:
        conn.execute(
            "INSERT INTO services VALUES (?,?,?,?,?,?,?,?)",
            ("svc1", "Test", "desc", 100,
             "http://localhost:8000/api/providers/test",
             "wallet_abc", datetime.utcnow().isoformat(), 1)
        )

    import sys
    import services.router as router_module
    macaroon = "testmacaroon=="
    router_module.pending_payments[macaroon] = {
        "payment_hash": "paidhash123",
        "service_id": "svc1"
    }

    from unittest.mock import patch
    with patch("services.router.get_marketplace_wallet") as mock_wallet, \
         patch("services.router._verify_payment", return_value=True), \
         patch("services.router._call_provider", return_value={"result": "ok"}), \
         patch("services.router._pay_provider"):
        sys.modules.pop("main", None)
        from main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.post(
            "/api/services/svc1/call",
            json={"input": "hello"},
            headers={"Authorization": f"L402 {macaroon}:deadbeef"}
        )

    assert response.status_code == 200
    assert response.json() == {"result": "ok"}
