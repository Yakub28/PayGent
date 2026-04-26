import pytest
import time
import re
from fastapi.testclient import TestClient
from datetime import datetime, UTC
from unittest.mock import patch, MagicMock

@pytest.fixture
def app():
    # Force clean state for imports
    import sys
    modules_to_clear = [
        "main", "database", "services.mock_wallet", "services.wallet_manager",
        "services.agents", "services.registry", "services.router", "services.simulation"
    ]
    for mod in modules_to_clear:
        sys.modules.pop(mod, None)
    
    from main import app
    return app

def test_full_marketplace_lifecycle(app, tmp_path, monkeypatch):
    """
    Integration: Register Consumer & Provider -> Discover -> Pay L402 -> Call -> Verify Funds.
    """
    db_path = str(tmp_path / "lifecycle.db")
    lightning_path = str(tmp_path / "lightning_lifecycle.json")
    monkeypatch.setattr("database.DB_PATH", db_path)
    monkeypatch.setattr("services.mock_wallet.STATE_FILE", lightning_path)
    
    from database import init_db
    init_db()

    with TestClient(app) as client:
        # 1. Register Consumer with 1000 sats
        consumer_resp = client.post("/api/agents", json={
            "name": "Market Consumer",
            "role": "consumer",
            "initial_balance_sats": 1000
        })
        assert consumer_resp.status_code == 200
        consumer_id = consumer_resp.json()["id"]
        
        # 2. Register Provider (Sentiment Analyzer)
        provider_resp = client.post("/api/agents", json={
            "name": "Quality AI",
            "role": "provider",
            "service_type": "sentiment",
            "initial_balance_sats": 0,
            "service_price_sats": 50
        })
        assert provider_resp.status_code == 200
        provider_id = provider_resp.json()["id"]
        service_id = provider_resp.json()["service_id"]
        
        # 3. Discover Service
        list_resp = client.get("/api/services")
        services = list_resp.json()
        assert any(s["id"] == service_id for s in services)
        
        # 4. Call Service (Expect 402)
        payload = {"input": {"text": "I love PayGent"}, "consumer_agent_id": consumer_id}
        call1 = client.post(f"/api/services/{service_id}/call", json=payload)
        assert call1.status_code == 402
        www_auth = call1.headers.get("WWW-Authenticate")
        
        # Extract macaroon and invoice
        macaroon = re.search(r'macaroon="([^"]+)"', www_auth).group(1)
        invoice = re.search(r'invoice="([^"]+)"', www_auth).group(1)
        
        # 5. Pay the invoice using the consumer's wallet (via internal logic)
        from services.wallet_manager import get_or_create_agent_wallet
        consumer_wallet = get_or_create_agent_wallet(consumer_id)
        pay_result = consumer_wallet.pay_invoice(invoice)
        assert pay_result is not None
        
        # 6. Retry call with L402 Authorization
        with patch("services.router._call_provider", return_value={"sentiment": "positive", "score": 0.99}):
            with patch("services.router.score_and_update") as mock_score:
                call2 = client.post(
                    f"/api/services/{service_id}/call",
                    json=payload,
                    headers={"Authorization": f"L402 {macaroon}:00000000000000000000000000000000"}
                )
                assert call2.status_code == 200
        
        # 7. Verify balances
        consumer_data = client.get("/api/agents").json()
        consumer_record = next(a for a in consumer_data if a["id"] == consumer_id)
        assert consumer_record["balance_sats"] == 950
        
        provider_record = next(a for a in consumer_data if a["id"] == provider_id)
        assert provider_record["balance_sats"] == 45 
        
        stats = client.get("/api/stats").json()
        # Seeded services might have made calls if simulation ran, so we check >= 50
        assert stats["total_volume_sats"] >= 50

def test_simulation_workflow(app, tmp_path, monkeypatch):
    """
    Integration: Start Simulation -> Run some steps -> Stop.
    """
    db_path = str(tmp_path / "sim.db")
    lightning_path = str(tmp_path / "lightning_sim.json")
    monkeypatch.setattr("database.DB_PATH", db_path)
    monkeypatch.setattr("services.mock_wallet.STATE_FILE", lightning_path)
    
    from database import init_db
    init_db()

    with TestClient(app) as client:
        # Need at least one consumer and one provider for simulation to work
        client.post("/api/agents", json={"name": "C1", "role": "consumer", "initial_balance_sats": 1000})
        client.post("/api/agents", json={"name": "P1", "role": "provider", "service_type": "code_writer"})
        
        # Start simulation
        start_resp = client.post("/api/simulation/start", json={
            "rate_per_sec": 10,
            "use_llm": False,
            "max_iterations": 2
        })
        assert start_resp.status_code == 200
        
        # Wait for simulation to finish
        max_wait = 5
        start_time = time.time()
        while time.time() - start_time < max_wait:
            status = client.get("/api/simulation/status").json()
            if status["iterations"] >= 1:
                break
            time.sleep(0.5)
        
        status = client.get("/api/simulation/status").json()
        assert status["iterations"] >= 1
        
        # Stop
        client.post("/api/simulation/stop")

def test_multiprocess_persistence_simulation(tmp_path, monkeypatch):
    """
    Integration: Ensure that TWO different registry instances sharing the same file see the same state.
    """
    lightning_path = str(tmp_path / "shared_wallet.json")
    
    # We must import fresh to avoid previous test state
    import sys
    sys.modules.pop("services.mock_wallet", None)
    from services.mock_wallet import _FileRegistry, MockWallet
    
    reg1 = _FileRegistry(lightning_path)
    reg2 = _FileRegistry(lightning_path)
    
    # Process 1 creates a wallet and an invoice
    with patch("services.mock_wallet.REGISTRY", reg1):
        w1 = MockWallet("wallet1", initial_sats=100)
        inv = w1.create_invoice(3600, 50, "Shared")
        
    # Process 2 sees the wallet and pays the invoice
    with patch("services.mock_wallet.REGISTRY", reg2):
        w2 = MockWallet("wallet2", initial_sats=200)
        # Verify it can find the invoice created by reg1
        found_inv = reg2.find_invoice_by_bolt11(inv.invoice)
        assert found_inv is not None
        
        # Pay it
        w2.pay_invoice(inv.invoice)
        assert w2.balance_sats == 150
        
    # Process 1 sees the updated balance
    with patch("services.mock_wallet.REGISTRY", reg1):
        assert w1.balance_sats == 150 
