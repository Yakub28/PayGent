# PayGent Marketplace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Lightning-powered agent marketplace where service providers register HTTP endpoints and consumer agents pay via L402 to call them, with the marketplace taking a 10% routing fee.

**Architecture:** FastAPI backend with SQLite registry, Lexe multi-wallet management, and L402 payment routing. Three provider services (summarizer, code reviewer, sentiment) run as internal FastAPI handlers called by the router. Next.js dashboard polls backend for live stats. Consumer agent uses a separate Lexe wallet to auto-handle 402 responses.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, Lexe SDK, Anthropic SDK, httpx, Next.js 14, Tailwind CSS, pytest

**Team Distribution:**
- **[A] Person A:** Tasks 1–7, 12–14 (backend infrastructure + payment router)
- **[B] Person B:** Tasks 8–11 in parallel with A's Tasks 1–7, then Tasks 15–19 (frontend)

---

## File Structure

```
config.py                           NEW  — env vars (pydantic-settings)
database.py                         NEW  — SQLite init + get_db() context manager
models.py                           NEW  — Pydantic request/response schemas
main.py                             MOD  — register all routers, call init_db() + seed()
requirements.txt                    MOD  — add httpx, anthropic, pydantic-settings, pytest

services/
  wallet_manager.py                 NEW  — Lexe wallet singleton (marketplace wallet)
  registry.py                       NEW  — POST /api/services/register, GET /api/services
  router.py                         NEW  — POST /api/services/{id}/call (L402 + fee + proxy)
  stats.py                          NEW  — GET /api/stats, GET /api/transactions
  providers/
    __init__.py                     NEW
    summarizer.py                   NEW  — GET /api/providers/summarize (Claude API)
    code_reviewer.py                NEW  — GET /api/providers/code-review (Claude API)
    sentiment.py                    NEW  — GET /api/providers/sentiment (Claude API)
    seed.py                         NEW  — register 3 services into DB on startup

agents/
  consumer_agent.py                 REWRITE — standalone L402 auto-pay loop (own Lexe wallet)

tests/
  test_registry.py                  NEW
  test_router.py                    NEW
  test_stats.py                     NEW

frontend/                           NEW  — npx create-next-app
  app/
    layout.tsx
    page.tsx
    globals.css
  components/
    StatsBar.tsx
    ServiceCatalog.tsx
    TransactionFeed.tsx
  lib/
    api.ts
```

---

## Task 1 [A]: Project Setup & Configuration

**Files:**
- Modify: `requirements.txt`
- Create: `config.py`
- Create: `.env.example`

- [ ] **Step 1: Update requirements.txt**

```
fastapi
uvicorn
lexe-sdk
requests
httpx
pydantic
pydantic-settings
langchain
python-dotenv
anthropic
pytest
pytest-asyncio
```

- [ ] **Step 2: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install without errors.

- [ ] **Step 3: Create config.py**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    lexe_client_credentials: str
    consumer_lexe_credentials: str
    anthropic_api_key: str
    fee_rate: float = 0.10
    provider_base_url: str = "http://localhost:8000"

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 4: Create .env.example**

```
LEXE_CLIENT_CREDENTIALS=your_marketplace_lexe_credentials_here
CONSUMER_LEXE_CREDENTIALS=your_consumer_lexe_credentials_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
FEE_RATE=0.10
PROVIDER_BASE_URL=http://localhost:8000
```

- [ ] **Step 5: Verify config loads**

```bash
python -c "from config import settings; print('FEE_RATE:', settings.fee_rate)"
```

Expected: `FEE_RATE: 0.1`

- [ ] **Step 6: Commit**

```bash
git add requirements.txt config.py .env.example
git commit -m "feat: add config and updated dependencies"
```

---

## Task 2 [A]: Database Setup

**Files:**
- Create: `database.py`
- Create: `tests/test_database.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_database.py
import os
import pytest
from database import init_db, get_db

@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr("database.DB_PATH", str(tmp_path / "test.db"))

def test_init_db_creates_tables():
    init_db()
    with get_db() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = [t["name"] for t in tables]
    assert "services" in names
    assert "transactions" in names

def test_get_db_commits_on_exit():
    init_db()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO services VALUES (?,?,?,?,?,?,?,?)",
            ("id1","name","desc",10,"http://x","wallet1","2026-01-01",1)
        )
    with get_db() as conn:
        row = conn.execute("SELECT id FROM services WHERE id=?", ("id1",)).fetchone()
    assert row is not None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_database.py -v
```

Expected: `ModuleNotFoundError: No module named 'database'`

- [ ] **Step 3: Create database.py**

```python
import sqlite3
from contextlib import contextmanager

DB_PATH = "paygent.db"

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                price_sats INTEGER NOT NULL,
                endpoint_url TEXT NOT NULL,
                provider_wallet TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                service_id TEXT NOT NULL,
                payment_hash TEXT NOT NULL,
                amount_sats INTEGER NOT NULL,
                fee_sats INTEGER,
                provider_sats INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
        """)

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_database.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add database.py tests/test_database.py
git commit -m "feat: add SQLite database setup with services and transactions tables"
```

---

## Task 3 [A]: Pydantic Models

**Files:**
- Create: `models.py`

- [ ] **Step 1: Create models.py**

```python
from pydantic import BaseModel
from typing import Optional, Any

class RegisterServiceRequest(BaseModel):
    name: str
    description: str
    price_sats: int
    endpoint_url: str

class RegisterServiceResponse(BaseModel):
    service_id: str
    provider_wallet: str

class ServiceListItem(BaseModel):
    id: str
    name: str
    description: str
    price_sats: int

class CallServiceRequest(BaseModel):
    input: Any

class TransactionRecord(BaseModel):
    id: str
    service_id: str
    service_name: Optional[str]
    payment_hash: str
    amount_sats: int
    fee_sats: Optional[int]
    provider_sats: Optional[int]
    status: str
    created_at: str

class StatsResponse(BaseModel):
    total_volume_sats: int
    total_fees_sats: int
    total_calls: int
    marketplace_balance_sats: int
```

- [ ] **Step 2: Verify models import**

```bash
python -c "from models import RegisterServiceRequest, StatsResponse; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add models.py
git commit -m "feat: add pydantic models for API schemas"
```

---

## Task 4 [A]: Wallet Manager

**Files:**
- Create: `services/wallet_manager.py`

> **Note:** This module wraps Lexe. It cannot be unit-tested without real credentials. Test it manually by running `python services/wallet_manager.py` with your `.env` configured.

- [ ] **Step 1: Create services/wallet_manager.py**

```python
from lexe import Credentials, LexeWallet, WalletConfig, ClientCredentials
from config import settings

_wallet_cache: dict[str, LexeWallet] = {}

def _load_wallet(creds_str: str) -> LexeWallet:
    config = WalletConfig.mainnet()
    client_creds = ClientCredentials.from_string(creds_str)
    creds = Credentials.from_client_credentials(client_creds)
    wallet = LexeWallet.load_or_fresh(config, creds)
    try:
        wallet.provision(creds)
    except Exception:
        pass
    return wallet

def get_marketplace_wallet() -> LexeWallet:
    if "marketplace" not in _wallet_cache:
        _wallet_cache["marketplace"] = _load_wallet(settings.lexe_client_credentials)
    return _wallet_cache["marketplace"]

def get_consumer_wallet() -> LexeWallet:
    if "consumer" not in _wallet_cache:
        _wallet_cache["consumer"] = _load_wallet(settings.consumer_lexe_credentials)
    return _wallet_cache["consumer"]

if __name__ == "__main__":
    wallet = get_marketplace_wallet()
    info = wallet.node_info()
    print(f"Marketplace wallet: {info.node_pk}")
    print(f"Balance: {info.balance_sats} sats")
```

- [ ] **Step 2: Manual smoke test**

```bash
python services/wallet_manager.py
```

Expected: prints node pubkey and balance (requires valid `.env`).

- [ ] **Step 3: Commit**

```bash
git add services/wallet_manager.py
git commit -m "feat: add Lexe wallet manager singleton"
```

---

## Task 5 [A]: Registry API

**Files:**
- Create: `services/registry.py`
- Create: `tests/test_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_registry.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("database.DB_PATH", str(tmp_path / "test.db"))
    from database import init_db
    init_db()
    with patch("services.registry.get_marketplace_wallet") as mock_wallet:
        mock_info = MagicMock()
        mock_info.node_pk = "abc123"
        mock_wallet.return_value.node_info.return_value = mock_info
        from main import app
        return TestClient(app)

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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_registry.py -v
```

Expected: `ImportError` or similar — registry not implemented yet.

- [ ] **Step 3: Create services/registry.py**

```python
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from database import get_db
from models import RegisterServiceRequest, RegisterServiceResponse, ServiceListItem
from services.wallet_manager import get_marketplace_wallet

router = APIRouter()

@router.post("/services/register", response_model=RegisterServiceResponse)
def register_service(req: RegisterServiceRequest):
    wallet = get_marketplace_wallet()
    info = wallet.node_info()
    service_id = str(uuid.uuid4())
    provider_wallet = f"provider_{service_id[:8]}_{info.node_pk[:8]}"

    with get_db() as conn:
        conn.execute(
            "INSERT INTO services VALUES (?,?,?,?,?,?,?,?)",
            (service_id, req.name, req.description, req.price_sats,
             req.endpoint_url, provider_wallet, datetime.utcnow().isoformat(), 1)
        )
    return RegisterServiceResponse(service_id=service_id, provider_wallet=provider_wallet)

@router.get("/services", response_model=list[ServiceListItem])
def list_services():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, description, price_sats FROM services WHERE is_active=1"
        ).fetchall()
    return [ServiceListItem(**dict(r)) for r in rows]

@router.delete("/services/{service_id}")
def deactivate_service(service_id: str):
    with get_db() as conn:
        conn.execute("UPDATE services SET is_active=0 WHERE id=?", (service_id,))
    return {"status": "deactivated"}
```

- [ ] **Step 4: Wire registry router into main.py temporarily**

```python
# main.py — replace entire file
from fastapi import FastAPI
from database import init_db
from services.registry import router as registry_router
import uvicorn

app = FastAPI(title="PayGent Marketplace")
app.include_router(registry_router, prefix="/api")

@app.on_event("startup")
def startup():
    init_db()

@app.get("/")
def root():
    return {"message": "PayGent Marketplace"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_registry.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add services/registry.py tests/test_registry.py main.py
git commit -m "feat: add service registry (register, list, deactivate)"
```

---

## Task 6 [A]: L402 Invoice Generation (first half of router)

**Files:**
- Create: `services/router.py`
- Create: `tests/test_router.py` (partial)

- [ ] **Step 1: Write failing test for 402 response**

```python
# tests/test_router.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("database.DB_PATH", str(tmp_path / "test.db"))
    from database import init_db
    init_db()

    # Seed a service
    from database import get_db
    import uuid
    from datetime import datetime
    with get_db() as conn:
        conn.execute(
            "INSERT INTO services VALUES (?,?,?,?,?,?,?,?)",
            ("svc1", "Test", "desc", 25,
             "http://localhost:8000/api/providers/test",
             "wallet_abc", datetime.utcnow().isoformat(), 1)
        )

    with patch("services.router.get_marketplace_wallet") as mock_wallet:
        mock_invoice = MagicMock()
        mock_invoice.payment_hash = "abc123hash"
        mock_invoice.invoice = "lnbc250n1..."
        mock_wallet.return_value.create_invoice.return_value = mock_invoice
        from main import app
        return TestClient(app)

def test_call_without_auth_returns_402(client):
    response = client.post("/api/services/svc1/call", json={"input": "hello"})
    assert response.status_code == 402
    www_auth = response.headers.get("WWW-Authenticate", "")
    assert "macaroon=" in www_auth
    assert "invoice=" in www_auth

def test_call_unknown_service_returns_404(client):
    response = client.post("/api/services/nonexistent/call", json={"input": "x"})
    assert response.status_code == 404
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_router.py::test_call_without_auth_returns_402 -v
```

Expected: `ImportError` — router not created yet.

- [ ] **Step 3: Create services/router.py (invoice generation only)**

```python
import base64
import uuid
import httpx
from datetime import datetime
from fastapi import APIRouter, Header, HTTPException, Request
from database import get_db
from models import CallServiceRequest, TransactionRecord
from services.wallet_manager import get_marketplace_wallet
from config import settings

router = APIRouter()

# macaroon -> { payment_hash, service_id }
pending_payments: dict[str, dict] = {}

def _generate_macaroon(payment_hash: str) -> str:
    return base64.b64encode(f"v=1,hash={payment_hash}".encode()).decode()

def _payment_required(macaroon: str, invoice: str):
    raise HTTPException(
        status_code=402,
        detail="Payment Required",
        headers={"WWW-Authenticate": f'L402 macaroon="{macaroon}", invoice="{invoice}"'}
    )

@router.post("/services/{service_id}/call")
async def call_service(
    service_id: str,
    req: CallServiceRequest,
    authorization: str = Header(None)
):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM services WHERE id=? AND is_active=1", (service_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Service not found")

    service = dict(row)

    if not authorization:
        wallet = get_marketplace_wallet()
        invoice_obj = wallet.create_invoice(
            expiration_secs=3600,
            amount_sats=service["price_sats"],
            description=f"PayGent: {service['name']}"
        )
        macaroon = _generate_macaroon(invoice_obj.payment_hash)
        pending_payments[macaroon] = {
            "payment_hash": invoice_obj.payment_hash,
            "service_id": service_id
        }
        txn_id = str(uuid.uuid4())
        with get_db() as conn:
            conn.execute(
                "INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?)",
                (txn_id, service_id, invoice_obj.payment_hash,
                 service["price_sats"], None, None, "pending",
                 datetime.utcnow().isoformat())
            )
        _payment_required(macaroon, invoice_obj.invoice)

    # Auth provided — handled in Task 7
    raise HTTPException(status_code=401, detail="Payment verification not yet implemented")
```

- [ ] **Step 4: Add router to main.py**

```python
from fastapi import FastAPI
from database import init_db
from services.registry import router as registry_router
from services.router import router as call_router
import uvicorn

app = FastAPI(title="PayGent Marketplace")
app.include_router(registry_router, prefix="/api")
app.include_router(call_router, prefix="/api")

@app.on_event("startup")
def startup():
    init_db()

@app.get("/")
def root():
    return {"message": "PayGent Marketplace"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_router.py::test_call_without_auth_returns_402 tests/test_router.py::test_call_unknown_service_returns_404 -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add services/router.py tests/test_router.py main.py
git commit -m "feat: add L402 invoice generation for /call endpoint"
```

---

## Task 7 [A]: Payment Verification + Provider Proxy (second half of router)

**Files:**
- Modify: `services/router.py`
- Modify: `tests/test_router.py`

- [ ] **Step 1: Add failing test for successful payment flow**

Append to `tests/test_router.py`:

```python
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

    import services.router as router_module
    macaroon = "testmacaroon=="
    router_module.pending_payments[macaroon] = {
        "payment_hash": "paidhash123",
        "service_id": "svc1"
    }

    with patch("services.router.get_marketplace_wallet") as mock_wallet, \
         patch("services.router._verify_payment", return_value=True), \
         patch("services.router._call_provider", return_value={"result": "ok"}), \
         patch("services.router._pay_provider"):
        from main import app
        client = TestClient(app)
        response = client.post(
            "/api/services/svc1/call",
            json={"input": "hello"},
            headers={"Authorization": f"L402 {macaroon}:deadbeef"}
        )

    assert response.status_code == 200
    assert response.json() == {"result": "ok"}
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_router.py::test_call_with_valid_payment_returns_provider_response -v
```

Expected: FAIL — `_verify_payment` not defined yet.

- [ ] **Step 3: Complete services/router.py with verification + proxy**

Replace the entire file:

```python
import base64
import uuid
import httpx
from datetime import datetime
from fastapi import APIRouter, Header, HTTPException
from lexe import PaymentFilter
from database import get_db
from models import CallServiceRequest
from services.wallet_manager import get_marketplace_wallet
from config import settings

router = APIRouter()
pending_payments: dict[str, dict] = {}

def _generate_macaroon(payment_hash: str) -> str:
    return base64.b64encode(f"v=1,hash={payment_hash}".encode()).decode()

def _payment_required(macaroon: str, invoice: str):
    raise HTTPException(
        status_code=402,
        detail="Payment Required",
        headers={"WWW-Authenticate": f'L402 macaroon="{macaroon}", invoice="{invoice}"'}
    )

def _verify_payment(payment_hash: str) -> bool:
    wallet = get_marketplace_wallet()
    payments = wallet.list_payments(PaymentFilter())
    return any(
        getattr(p, "payment_hash", None) == payment_hash
        and getattr(p, "status", None) in ("succeeded", "settled", "completed")
        for p in payments
    )

async def _call_provider(endpoint_url: str, input_data) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(endpoint_url, json={"input": input_data})
        response.raise_for_status()
        return response.json()

def _pay_provider(provider_wallet: str, provider_sats: int):
    # In v1 all providers are internal (same wallet).
    # This is a no-op recorded for accounting only.
    # In production: wallet.pay_to_address(provider_wallet, provider_sats)
    pass

@router.post("/services/{service_id}/call")
async def call_service(
    service_id: str,
    req: CallServiceRequest,
    authorization: str = Header(None)
):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM services WHERE id=? AND is_active=1", (service_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Service not found")

    service = dict(row)

    if not authorization:
        wallet = get_marketplace_wallet()
        invoice_obj = wallet.create_invoice(
            expiration_secs=3600,
            amount_sats=service["price_sats"],
            description=f"PayGent: {service['name']}"
        )
        macaroon = _generate_macaroon(invoice_obj.payment_hash)
        pending_payments[macaroon] = {
            "payment_hash": invoice_obj.payment_hash,
            "service_id": service_id
        }
        txn_id = str(uuid.uuid4())
        with get_db() as conn:
            conn.execute(
                "INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?)",
                (txn_id, service_id, invoice_obj.payment_hash,
                 service["price_sats"], None, None, "pending",
                 datetime.utcnow().isoformat())
            )
        _payment_required(macaroon, invoice_obj.invoice)

    # Auth provided
    try:
        _, auth_data = authorization.split(" ", 1)
        macaroon, preimage = auth_data.split(":", 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Malformed Authorization header")

    entry = pending_payments.get(macaroon)
    if not entry:
        raise HTTPException(status_code=401, detail="Unknown macaroon")

    payment_hash = entry["payment_hash"]

    if not _verify_payment(payment_hash):
        with get_db() as conn:
            invoice_row = conn.execute(
                "SELECT * FROM transactions WHERE payment_hash=?", (payment_hash,)
            ).fetchone()
        invoice_str = ""
        _payment_required(macaroon, invoice_str)

    # Payment confirmed — call provider
    try:
        result = await _call_provider(service["endpoint_url"], req.input)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {str(e)}")

    # Record fee split
    fee_sats = int(service["price_sats"] * settings.fee_rate)
    provider_sats = service["price_sats"] - fee_sats

    with get_db() as conn:
        conn.execute(
            """UPDATE transactions SET status='paid', fee_sats=?, provider_sats=?
               WHERE payment_hash=?""",
            (fee_sats, provider_sats, payment_hash)
        )

    _pay_provider(service["provider_wallet"], provider_sats)
    del pending_payments[macaroon]

    return result
```

- [ ] **Step 4: Run all router tests**

```bash
pytest tests/test_router.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add services/router.py tests/test_router.py
git commit -m "feat: complete L402 payment verification and provider proxy in router"
```

---

## Task 8 [B]: Web Summarizer Provider

**Files:**
- Create: `services/providers/summarizer.py`
- Create: `services/providers/__init__.py`

- [ ] **Step 1: Create services/providers/__init__.py**

```python
```
(empty file)

- [ ] **Step 2: Write failing test**

```python
# tests/test_providers.py
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

@pytest.fixture
def client():
    from main import app
    return TestClient(app)

def test_summarizer_returns_summary(client):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="This is a 3-sentence summary.")]

    with patch("services.providers.summarizer.httpx.get") as mock_get, \
         patch("services.providers.summarizer.anthropic_client.messages.create",
               return_value=mock_response):
        mock_get.return_value.text = "<html><body>Hello world content</body></html>"
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        response = client.post("/api/providers/summarize", json={"input": "https://example.com"})

    assert response.status_code == 200
    assert "summary" in response.json()
```

- [ ] **Step 3: Run to verify failure**

```bash
pytest tests/test_providers.py::test_summarizer_returns_summary -v
```

Expected: FAIL — endpoint doesn't exist.

- [ ] **Step 4: Create services/providers/summarizer.py**

```python
import httpx
import anthropic
from fastapi import APIRouter, HTTPException
from models import CallServiceRequest
from config import settings

router = APIRouter()
anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

@router.post("/providers/summarize")
def summarize(req: CallServiceRequest):
    url = req.input
    if not isinstance(url, str) or not url.startswith("http"):
        raise HTTPException(status_code=400, detail="input must be a URL string")

    try:
        page = httpx.get(url, timeout=10.0, follow_redirects=True)
        page_text = page.text[:8000]
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not fetch URL: {e}")

    message = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": f"Summarize the following webpage content in exactly 3 sentences:\n\n{page_text}"
        }]
    )
    return {"summary": message.content[0].text}
```

- [ ] **Step 5: Register router in main.py**

Add to main.py imports and registration:

```python
from services.providers.summarizer import router as summarizer_router
# ...
app.include_router(summarizer_router, prefix="/api")
```

- [ ] **Step 6: Run test**

```bash
pytest tests/test_providers.py::test_summarizer_returns_summary -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add services/providers/__init__.py services/providers/summarizer.py tests/test_providers.py main.py
git commit -m "feat: add web summarizer provider (Claude API)"
```

---

## Task 9 [B]: Code Reviewer Provider

**Files:**
- Create: `services/providers/code_reviewer.py`
- Modify: `tests/test_providers.py`

- [ ] **Step 1: Append failing test**

```python
def test_code_reviewer_returns_review(client):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"bugs":[],"suggestions":["Use type hints"],"score":8}')]

    with patch("services.providers.code_reviewer.anthropic_client.messages.create",
               return_value=mock_response):
        response = client.post("/api/providers/code-review", json={
            "input": {"code": "def foo(): pass", "language": "python"}
        })

    assert response.status_code == 200
    data = response.json()
    assert "bugs" in data or "review" in data
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_providers.py::test_code_reviewer_returns_review -v
```

Expected: FAIL — endpoint not found.

- [ ] **Step 3: Create services/providers/code_reviewer.py**

```python
import json
import anthropic
from fastapi import APIRouter, HTTPException
from models import CallServiceRequest
from config import settings

router = APIRouter()
anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

@router.post("/providers/code-review")
def code_review(req: CallServiceRequest):
    if not isinstance(req.input, dict):
        raise HTTPException(status_code=400, detail="input must be {code, language}")
    code = req.input.get("code", "")
    language = req.input.get("language", "unknown")

    message = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                f"Review this {language} code. Reply with JSON only:\n"
                f'{{"bugs": [...], "suggestions": [...], "score": 1-10}}\n\n'
                f"Code:\n{code}"
            )
        }]
    )
    raw = message.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"review": raw}
```

- [ ] **Step 4: Add to main.py**

```python
from services.providers.code_reviewer import router as code_reviewer_router
# ...
app.include_router(code_reviewer_router, prefix="/api")
```

- [ ] **Step 5: Run test**

```bash
pytest tests/test_providers.py::test_code_reviewer_returns_review -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/providers/code_reviewer.py tests/test_providers.py main.py
git commit -m "feat: add code reviewer provider (Claude API)"
```

---

## Task 10 [B]: Sentiment Analyzer Provider

**Files:**
- Create: `services/providers/sentiment.py`
- Modify: `tests/test_providers.py`

- [ ] **Step 1: Append failing test**

```python
def test_sentiment_returns_analysis(client):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"sentiment":"positive","score":0.9,"confidence":0.95}')]

    with patch("services.providers.sentiment.anthropic_client.messages.create",
               return_value=mock_response):
        response = client.post("/api/providers/sentiment", json={
            "input": "I love this product, it works great!"
        })

    assert response.status_code == 200
    data = response.json()
    assert "sentiment" in data or "analysis" in data
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_providers.py::test_sentiment_returns_analysis -v
```

Expected: FAIL — endpoint not found.

- [ ] **Step 3: Create services/providers/sentiment.py**

```python
import json
import anthropic
from fastapi import APIRouter, HTTPException
from models import CallServiceRequest
from config import settings

router = APIRouter()
anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

@router.post("/providers/sentiment")
def sentiment(req: CallServiceRequest):
    if not isinstance(req.input, str):
        raise HTTPException(status_code=400, detail="input must be a string")

    message = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=128,
        messages=[{
            "role": "user",
            "content": (
                "Analyze the sentiment of the following text. Reply with JSON only:\n"
                '{"sentiment": "positive|negative|neutral", "score": 0.0-1.0, "confidence": 0.0-1.0}\n\n'
                f"Text: {req.input}"
            )
        }]
    )
    raw = message.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"analysis": raw}
```

- [ ] **Step 4: Add to main.py**

```python
from services.providers.sentiment import router as sentiment_router
# ...
app.include_router(sentiment_router, prefix="/api")
```

- [ ] **Step 5: Run all provider tests**

```bash
pytest tests/test_providers.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add services/providers/sentiment.py tests/test_providers.py main.py
git commit -m "feat: add sentiment analyzer provider (Claude API)"
```

---

## Task 11 [B]: Service Seeding on Startup

**Files:**
- Create: `services/providers/seed.py`
- Modify: `main.py`

- [ ] **Step 1: Create services/providers/seed.py**

```python
from database import get_db
from config import settings

SERVICES = [
    {
        "name": "Web Summarizer",
        "description": "Fetches a URL and returns a 3-sentence summary. Input: URL string.",
        "price_sats": 25,
        "endpoint_url": f"{settings.provider_base_url}/api/providers/summarize",
    },
    {
        "name": "Code Reviewer",
        "description": "Reviews code for bugs and quality. Input: {code, language}.",
        "price_sats": 100,
        "endpoint_url": f"{settings.provider_base_url}/api/providers/code-review",
    },
    {
        "name": "Sentiment Analyzer",
        "description": "Analyzes text sentiment. Returns positive/negative/neutral + score. Input: string.",
        "price_sats": 50,
        "endpoint_url": f"{settings.provider_base_url}/api/providers/sentiment",
    },
]

def seed_services():
    from services.registry import register_service
    from models import RegisterServiceRequest

    with get_db() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM services WHERE is_active=1").fetchone()[0]

    if existing >= len(SERVICES):
        print(f"Services already seeded ({existing} active). Skipping.")
        return

    print("Seeding marketplace services...")
    for svc in SERVICES:
        req = RegisterServiceRequest(**svc)
        result = register_service(req)
        print(f"  Registered '{svc['name']}' → {result.service_id}")
```

- [ ] **Step 2: Add seed call to main.py startup**

```python
from services.providers.seed import seed_services

@app.on_event("startup")
def startup():
    init_db()
    seed_services()
```

- [ ] **Step 3: Start the server and verify seeding**

```bash
python main.py
```

Expected output includes:
```
Seeding marketplace services...
  Registered 'Web Summarizer' → <uuid>
  Registered 'Code Reviewer' → <uuid>
  Registered 'Sentiment Analyzer' → <uuid>
```

- [ ] **Step 4: Verify via API**

```bash
curl http://localhost:8000/api/services
```

Expected: JSON array with 3 services, no `endpoint_url` field.

- [ ] **Step 5: Commit**

```bash
git add services/providers/seed.py main.py
git commit -m "feat: seed 3 marketplace services on startup"
```

---

## Task 12 [A]: Stats API

**Files:**
- Create: `services/stats.py`
- Create: `tests/test_stats.py`
- Modify: `main.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_stats.py
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
            "INSERT INTO services VALUES (?,?,?,?,?,?,?,?)",
            ("svc1","Test","desc",100,"http://x","wallet",datetime.utcnow().isoformat(),1)
        )
        conn.execute(
            "INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?)",
            ("tx1","svc1","hash1",100,10,90,"paid",datetime.utcnow().isoformat())
        )
        conn.execute(
            "INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?)",
            ("tx2","svc1","hash2",100,10,90,"paid",datetime.utcnow().isoformat())
        )

    with patch("services.stats.get_marketplace_wallet") as mock_wallet:
        mock_info = MagicMock()
        mock_info.balance_sats = 500
        mock_wallet.return_value.node_info.return_value = mock_info
        from main import app
        return TestClient(app)

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
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_stats.py -v
```

Expected: FAIL — stats module missing.

- [ ] **Step 3: Create services/stats.py**

```python
from fastapi import APIRouter
from database import get_db
from models import StatsResponse, TransactionRecord
from services.wallet_manager import get_marketplace_wallet

router = APIRouter()

@router.get("/stats", response_model=StatsResponse)
def get_stats():
    wallet = get_marketplace_wallet()
    balance = wallet.node_info().balance_sats

    with get_db() as conn:
        row = conn.execute(
            """SELECT
                COALESCE(SUM(amount_sats), 0) as volume,
                COALESCE(SUM(fee_sats), 0) as fees,
                COUNT(*) as calls
               FROM transactions WHERE status='paid'"""
        ).fetchone()

    return StatsResponse(
        total_volume_sats=row["volume"],
        total_fees_sats=row["fees"],
        total_calls=row["calls"],
        marketplace_balance_sats=balance,
    )

@router.get("/transactions", response_model=list[TransactionRecord])
def get_transactions():
    with get_db() as conn:
        rows = conn.execute(
            """SELECT t.*, s.name as service_name
               FROM transactions t
               LEFT JOIN services s ON t.service_id = s.id
               ORDER BY t.created_at DESC
               LIMIT 50"""
        ).fetchall()
    return [TransactionRecord(**dict(r)) for r in rows]
```

- [ ] **Step 4: Add to main.py**

```python
from services.stats import router as stats_router
# ...
app.include_router(stats_router, prefix="/api")
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_stats.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add services/stats.py tests/test_stats.py main.py
git commit -m "feat: add stats and transactions API endpoints"
```

---

## Task 13 [A]: Consumer Agent Rewrite

**Files:**
- Rewrite: `agents/consumer_agent.py`

- [ ] **Step 1: Rewrite agents/consumer_agent.py**

```python
import os
import sys
import re
import time
import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.wallet_manager import get_consumer_wallet

BASE_URL = os.getenv("PROVIDER_BASE_URL", "http://localhost:8000")

class L402Client:
    def __init__(self):
        self.wallet = get_consumer_wallet()
        self.tokens: dict[str, dict] = {}

    def call(self, service_id: str, input_data) -> dict:
        url = f"{BASE_URL}/api/services/{service_id}/call"
        payload = {"input": input_data}
        headers = {}

        if service_id in self.tokens:
            t = self.tokens[service_id]
            headers["Authorization"] = f"L402 {t['macaroon']}:{t['preimage']}"

        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 402:
            print(f"  → 402 Payment Required")
            www_auth = response.headers.get("WWW-Authenticate", "")
            macaroon_match = re.search(r'macaroon="([^"]+)"', www_auth)
            invoice_match = re.search(r'invoice="([^"]+)"', www_auth)

            if not macaroon_match or not invoice_match:
                raise Exception("Could not parse WWW-Authenticate header")

            macaroon = macaroon_match.group(1)
            invoice = invoice_match.group(1)

            print(f"  → Paying invoice {invoice[:30]}...")
            try:
                result = self.wallet.pay_invoice(invoice)
                print(f"  → Payment sent (index: {result.index})")
            except Exception as e:
                if "cannot pay ourselves" in str(e).lower():
                    print(f"  → Same-wallet detected (demo mode). Proceeding.")
                else:
                    raise

            time.sleep(2)

            self.tokens[service_id] = {"macaroon": macaroon, "preimage": "00" * 32}
            return self.call(service_id, input_data)

        response.raise_for_status()
        return response.json()


def discover_services() -> list[dict]:
    response = requests.get(f"{BASE_URL}/api/services")
    response.raise_for_status()
    return response.json()


def run_demo():
    print("=" * 60)
    print("PayGent Consumer Agent — Demo Run")
    print("=" * 60)

    client = L402Client()

    services = discover_services()
    print(f"\nDiscovered {len(services)} services:")
    for s in services:
        print(f"  [{s['id'][:8]}] {s['name']} — {s['price_sats']} sats")

    tasks = [
        (services[0]["id"], "https://example.com"),
        (services[1]["id"], {"code": "def add(a,b): return a+b", "language": "python"}),
        (services[2]["id"], "Lightning payments are making agent economies possible!"),
    ]

    for service_id, input_data in tasks:
        service_name = next(s["name"] for s in services if s["id"] == service_id)
        print(f"\n--- Calling: {service_name} ---")
        try:
            result = client.call(service_id, input_data)
            print(f"  Result: {result}")
        except Exception as e:
            print(f"  Error: {e}")
        time.sleep(1)

    print("\n" + "=" * 60)
    print("Demo complete. Check the dashboard for transaction history.")
    print("=" * 60)


if __name__ == "__main__":
    run_demo()
```

- [ ] **Step 2: Run smoke test against live server**

In terminal 1:
```bash
python main.py
```

In terminal 2:
```bash
python agents/consumer_agent.py
```

Expected: agent discovers 3 services, attempts payment for each, receives results.

- [ ] **Step 3: Commit**

```bash
git add agents/consumer_agent.py
git commit -m "feat: rewrite consumer agent with full L402 auto-pay and service discovery"
```

---

## Task 14 [A]: Final main.py Assembly

**Files:**
- Rewrite: `main.py`

- [ ] **Step 1: Write the final main.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from database import init_db
from services.registry import router as registry_router
from services.router import router as call_router
from services.stats import router as stats_router
from services.providers.summarizer import router as summarizer_router
from services.providers.code_reviewer import router as code_reviewer_router
from services.providers.sentiment import router as sentiment_router
from services.providers.seed import seed_services

app = FastAPI(title="PayGent Marketplace")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(registry_router, prefix="/api")
app.include_router(call_router, prefix="/api")
app.include_router(stats_router, prefix="/api")
app.include_router(summarizer_router, prefix="/api")
app.include_router(code_reviewer_router, prefix="/api")
app.include_router(sentiment_router, prefix="/api")

@app.on_event("startup")
def startup():
    init_db()
    seed_services()

@app.get("/")
def root():
    return {"message": "PayGent Marketplace — Lightning-powered agent services"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
```

- [ ] **Step 2: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Start server and verify all routes**

```bash
python main.py
curl http://localhost:8000/api/services
curl http://localhost:8000/api/stats
```

Expected: services list + stats JSON.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: assemble final main.py with CORS and all routers"
```

---

## Task 15 [B]: Next.js Project Setup

**Files:**
- Create: `frontend/` (via CLI)

- [ ] **Step 1: Scaffold Next.js app**

```bash
cd /path/to/PayGent
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --no-src-dir --import-alias "@/*"
cd frontend
```

- [ ] **Step 2: Create lib/api.ts**

```typescript
// frontend/lib/api.ts
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Service {
  id: string;
  name: string;
  description: string;
  price_sats: number;
}

export interface Transaction {
  id: string;
  service_id: string;
  service_name: string | null;
  payment_hash: string;
  amount_sats: number;
  fee_sats: number | null;
  provider_sats: number | null;
  status: string;
  created_at: string;
}

export interface Stats {
  total_volume_sats: number;
  total_fees_sats: number;
  total_calls: number;
  marketplace_balance_sats: number;
}

export async function fetchStats(): Promise<Stats> {
  const res = await fetch(`${BASE}/api/stats`, { cache: "no-store" });
  return res.json();
}

export async function fetchServices(): Promise<Service[]> {
  const res = await fetch(`${BASE}/api/services`, { cache: "no-store" });
  return res.json();
}

export async function fetchTransactions(): Promise<Transaction[]> {
  const res = await fetch(`${BASE}/api/transactions`, { cache: "no-store" });
  return res.json();
}
```

- [ ] **Step 3: Verify dev server starts**

```bash
npm run dev
```

Expected: Next.js running on http://localhost:3000.

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold Next.js frontend with API client"
```

---

## Task 16 [B]: StatsBar Component

**Files:**
- Create: `frontend/components/StatsBar.tsx`

- [ ] **Step 1: Create StatsBar.tsx**

```tsx
// frontend/components/StatsBar.tsx
import { Stats } from "@/lib/api";

interface Props { stats: Stats }

export default function StatsBar({ stats }: Props) {
  return (
    <div className="grid grid-cols-4 gap-4 mb-8">
      {[
        { label: "Total Volume", value: `${stats.total_volume_sats.toLocaleString()} sat` },
        { label: "Fees Earned", value: `${stats.total_fees_sats.toLocaleString()} sat` },
        { label: "Total Calls", value: stats.total_calls.toString() },
        { label: "Wallet Balance", value: `${stats.marketplace_balance_sats.toLocaleString()} sat` },
      ].map(({ label, value }) => (
        <div key={label} className="bg-gray-900 border border-purple-700 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-purple-400">{value}</div>
          <div className="text-sm text-gray-400 mt-1">{label}</div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/StatsBar.tsx
git commit -m "feat: add StatsBar dashboard component"
```

---

## Task 17 [B]: ServiceCatalog Component

**Files:**
- Create: `frontend/components/ServiceCatalog.tsx`

- [ ] **Step 1: Create ServiceCatalog.tsx**

```tsx
// frontend/components/ServiceCatalog.tsx
import { Service } from "@/lib/api";

interface Props { services: Service[] }

const ICONS: Record<string, string> = {
  "Web Summarizer": "🔍",
  "Code Reviewer": "🧠",
  "Sentiment Analyzer": "📊",
};

export default function ServiceCatalog({ services }: Props) {
  return (
    <div className="mb-8">
      <h2 className="text-lg font-semibold text-gray-300 mb-3">Available Services</h2>
      <div className="space-y-3">
        {services.map((s) => (
          <div
            key={s.id}
            className="flex items-center justify-between bg-gray-900 border border-gray-700 rounded-xl p-4 hover:border-purple-600 transition-colors"
          >
            <div className="flex items-center gap-3">
              <span className="text-2xl">{ICONS[s.name] ?? "⚡"}</span>
              <div>
                <div className="font-medium text-white">{s.name}</div>
                <div className="text-sm text-gray-400">{s.description}</div>
              </div>
            </div>
            <div className="text-purple-400 font-mono font-bold whitespace-nowrap ml-4">
              {s.price_sats} sat
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/ServiceCatalog.tsx
git commit -m "feat: add ServiceCatalog component"
```

---

## Task 18 [B]: TransactionFeed Component + Main Page

**Files:**
- Create: `frontend/components/TransactionFeed.tsx`
- Rewrite: `frontend/app/page.tsx`

- [ ] **Step 1: Create TransactionFeed.tsx**

```tsx
// frontend/components/TransactionFeed.tsx
import { Transaction } from "@/lib/api";

interface Props { transactions: Transaction[] }

function timeAgo(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso + "Z").getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

export default function TransactionFeed({ transactions }: Props) {
  return (
    <div>
      <h2 className="text-lg font-semibold text-gray-300 mb-3">Live Payment Feed</h2>
      <div className="bg-gray-900 border border-gray-700 rounded-xl overflow-hidden">
        {transactions.length === 0 && (
          <div className="text-center text-gray-500 py-8">
            No transactions yet. Run the consumer agent to see payments flow.
          </div>
        )}
        {transactions.map((t) => (
          <div
            key={t.id}
            className="flex items-center justify-between px-4 py-3 border-b border-gray-800 last:border-0"
          >
            <div className="flex items-center gap-3">
              <span className={t.status === "paid" ? "text-green-400" : "text-yellow-400"}>
                {t.status === "paid" ? "✓" : "⏳"}
              </span>
              <span className="text-white font-medium">
                {t.service_name ?? t.service_id.slice(0, 8)}
              </span>
            </div>
            <div className="flex items-center gap-6 text-sm">
              <span className="text-gray-300">{t.amount_sats} sat</span>
              <span className="text-purple-400">
                fee: {t.fee_sats ?? "—"} sat
              </span>
              <span className="text-gray-500">{timeAgo(t.created_at)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Rewrite app/page.tsx with polling**

```tsx
// frontend/app/page.tsx
"use client";
import { useEffect, useState } from "react";
import { fetchStats, fetchServices, fetchTransactions, Stats, Service, Transaction } from "@/lib/api";
import StatsBar from "@/components/StatsBar";
import ServiceCatalog from "@/components/ServiceCatalog";
import TransactionFeed from "@/components/TransactionFeed";

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [services, setServices] = useState<Service[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);

  async function refresh() {
    const [s, svc, txns] = await Promise.all([
      fetchStats(),
      fetchServices(),
      fetchTransactions(),
    ]);
    setStats(s);
    setServices(svc);
    setTransactions(txns);
  }

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <main className="min-h-screen bg-gray-950 text-white p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-white">PayGent Marketplace</h1>
            <p className="text-gray-400 mt-1">Lightning-powered agent services</p>
          </div>
          <div className="text-xs text-gray-600">auto-refreshes every 3s</div>
        </div>

        {stats && <StatsBar stats={stats} />}
        <ServiceCatalog services={services} />
        <TransactionFeed transactions={transactions} />
      </div>
    </main>
  );
}
```

- [ ] **Step 3: Update app/globals.css to set dark background**

Ensure `globals.css` contains:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  background-color: #030712;
}
```

- [ ] **Step 4: Start frontend dev server and verify**

```bash
cd frontend && npm run dev
```

Open http://localhost:3000 — verify stats, services, and feed render. Start consumer agent in another terminal to see live updates.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/TransactionFeed.tsx frontend/app/page.tsx frontend/app/globals.css
git commit -m "feat: add transaction feed and main dashboard page with 3s polling"
```

---

## Task 19: End-to-End Integration Demo

**This task is for both team members together.**

- [ ] **Step 1: Start the FastAPI backend**

```bash
cd PayGent
source venv/bin/activate
python main.py
```

Verify output: services seeded, wallet connected.

- [ ] **Step 2: Start the Next.js dashboard**

```bash
cd frontend
npm run dev
```

Open http://localhost:3000. Verify 3 services visible, stats show 0.

- [ ] **Step 3: Run the consumer agent**

```bash
cd PayGent
python agents/consumer_agent.py
```

Watch the dashboard auto-update: transaction feed populates, volume + fees increment.

- [ ] **Step 4: Run full backend test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete PayGent marketplace — Lightning agent economy demo"
```

---

## Phase Summary & Time Budget

| Phase | Tasks | Owner | Est. Time |
|---|---|---|---|
| Backend foundation | 1–5 | A | 3h |
| Payment router | 6–7 | A | 2h |
| Provider services | 8–11 | B (parallel with A) | 3h |
| Stats + consumer agent | 12–13 | A | 2h |
| Final wiring | 14 | A | 30m |
| Frontend | 15–18 | B | 4h |
| Integration | 19 | Both | 1h |
| **Total** | | | **~12h critical path** |

Remaining ~12h: polish, real two-wallet testing, edge case hardening, demo rehearsal.
