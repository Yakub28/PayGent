# Reputation Scoring & Dynamic Pricing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After every paid service call, Claude Haiku scores the response quality (0–100); scores aggregate into Bronze/Silver/Gold tiers that set price ceilings; all data surfaces on the dashboard.

**Architecture:** BackgroundTask in `router.py` fires `score_and_update()` from `services/scorer.py` after the consumer receives their result (zero added latency). Tier is recomputed on every scored transaction. New PATCH endpoint lets providers raise their price up to their tier ceiling.

**Tech Stack:** FastAPI BackgroundTasks, Anthropic Claude Haiku (claude-haiku-4-5-20251001), SQLite ALTER TABLE migration, Next.js + Tailwind CSS.

**Spec:** `docs/superpowers/specs/2026-04-26-reputation-pricing-design.md`

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `database.py` | Add `_migrate_db()`, update CREATE TABLE to include new columns |
| Modify | `config.py` | Add 6 tier threshold constants |
| Modify | `models.py` | Extend `ServiceListItem`, `TransactionRecord`, `StatsResponse`; add `UpdatePriceRequest`, `UpdatePriceResponse` |
| **Create** | `services/scorer.py` | `_normalize_input()`, `score_response()`, `score_and_update()` |
| Modify | `services/router.py` | Add `BackgroundTasks`, store `txn_id` in `pending_payments`, fire `score_and_update` |
| Modify | `services/registry.py` | Named-column INSERT, updated `list_services` query (new fields + call_count), new PATCH price endpoint |
| Modify | `services/stats.py` | Add `top_rated_name` / `top_rated_tier` to `/api/stats` |
| Modify | `frontend/lib/api.ts` | Update `Service`, `Transaction`, `Stats` interfaces |
| Modify | `frontend/components/ServiceCatalog.tsx` | Tier badge, avg score, call count |
| Modify | `frontend/components/TransactionFeed.tsx` | Quality score + reason per row |
| Modify | `frontend/components/StatsBar.tsx` | Top Rated card (5th card) |
| **Create** | `tests/test_scorer.py` | Tests for `score_response` and `score_and_update` |
| Modify | `tests/test_registry.py` | Add PATCH price tests |
| Modify | `tests/test_stats.py` | Update fixture (named-column INSERT), add `top_rated` assertion |
| Modify | `tests/test_router.py` | Update fixture (named-column INSERT) |

---

## Task 1: Database Migration

**Files:**
- Modify: `database.py`
- Test: inline (checked via `test_database.py` pattern)

- [ ] **Step 1: Write the failing test**

Create `tests/test_migration.py`:

```python
import pytest

def test_migration_adds_new_columns(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("database.DB_PATH", db_path)
    import sqlite3
    from database import get_db

    # Create old-schema DB manually at the patched path (simulates existing install)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE services (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
            price_sats INTEGER NOT NULL, endpoint_url TEXT NOT NULL,
            provider_wallet TEXT NOT NULL, created_at TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE transactions (
            id TEXT PRIMARY KEY, service_id TEXT NOT NULL,
            payment_hash TEXT NOT NULL, amount_sats INTEGER NOT NULL,
            fee_sats INTEGER, provider_sats INTEGER,
            status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

    from database import init_db
    init_db()

    with get_db() as c:
        cols_svc = {r[1] for r in c.execute("PRAGMA table_info(services)")}
        cols_txn = {r[1] for r in c.execute("PRAGMA table_info(transactions)")}

    assert {"tier", "avg_quality_score", "success_rate", "price_adjusted"}.issubset(cols_svc)
    assert {"quality_score", "score_reason"}.issubset(cols_txn)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_migration.py -v
```

Expected: FAIL — `init_db` doesn't add the new columns yet.

- [ ] **Step 3: Implement migration in `database.py`**

Replace the entire `database.py` with:

```python
import sqlite3
from contextlib import contextmanager

DB_PATH = "paygent.db"

def _migrate_db(conn):
    """Add new columns to existing databases. Silently skips if already present."""
    migrations = [
        "ALTER TABLE transactions ADD COLUMN quality_score INTEGER",
        "ALTER TABLE transactions ADD COLUMN score_reason TEXT",
        "ALTER TABLE services ADD COLUMN tier TEXT NOT NULL DEFAULT 'bronze'",
        "ALTER TABLE services ADD COLUMN avg_quality_score REAL",
        "ALTER TABLE services ADD COLUMN success_rate REAL NOT NULL DEFAULT 0.0",
        "ALTER TABLE services ADD COLUMN price_adjusted INTEGER NOT NULL DEFAULT 0",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass  # column already exists

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
                is_active INTEGER NOT NULL DEFAULT 1,
                tier TEXT NOT NULL DEFAULT 'bronze',
                avg_quality_score REAL,
                success_rate REAL NOT NULL DEFAULT 0.0,
                price_adjusted INTEGER NOT NULL DEFAULT 0
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
                created_at TEXT NOT NULL,
                quality_score INTEGER,
                score_reason TEXT
            )
        """)
        _migrate_db(conn)

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

- [ ] **Step 4: Update positional INSERTs in test fixtures**

The existing tests use `INSERT INTO services VALUES (?,?,?,?,?,?,?,?)` with 8 positional args — this will break once `services` has 12 columns. Update every test fixture that inserts directly into `services` or `transactions`.

In `tests/test_stats.py`, replace the fixture INSERTs:

```python
# Replace both positional INSERTs in the client fixture:
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
```

In `tests/test_router.py`, replace the services INSERT in both fixtures:

```python
# First fixture (inside client):
conn.execute(
    "INSERT INTO services (id, name, description, price_sats, endpoint_url, provider_wallet, created_at, is_active) VALUES (?,?,?,?,?,?,?,?)",
    ("svc1", "Test", "desc", 25,
     "http://localhost:8000/api/providers/test",
     "wallet_abc", datetime.utcnow().isoformat(), 1)
)

# Second fixture (test_call_with_valid_payment_returns_provider_response):
conn.execute(
    "INSERT INTO services (id, name, description, price_sats, endpoint_url, provider_wallet, created_at, is_active) VALUES (?,?,?,?,?,?,?,?)",
    ("svc1", "Test", "desc", 100,
     "http://localhost:8000/api/providers/test",
     "wallet_abc", datetime.utcnow().isoformat(), 1)
)
```

- [ ] **Step 5: Run all existing tests to verify they still pass**

```bash
pytest tests/ -v
```

Expected: all 13 tests PASS (plus the new migration test = 14 total).

- [ ] **Step 6: Commit**

```bash
git add database.py tests/test_migration.py tests/test_stats.py tests/test_router.py
git commit -m "feat: db migration adds reputation and pricing columns"
```

---

## Task 2: Config Constants + Model Extensions

**Files:**
- Modify: `config.py`
- Modify: `models.py`

No TDD for these — Pydantic validates at import time, constants are used by later tasks.

- [ ] **Step 1: Add tier constants to `config.py`**

Replace the entire `config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    lexe_client_credentials: str = ""
    consumer_lexe_credentials: str = ""
    anthropic_api_key: str = ""
    fee_rate: float = 0.10
    provider_base_url: str = "http://localhost:8000"

    # Tier thresholds
    bronze_ceiling: int = 150
    silver_ceiling: int = 400
    silver_min_score: float = 70.0
    silver_min_calls: int = 10
    gold_min_score: float = 85.0
    gold_min_calls: int = 25

settings = Settings()
```

- [ ] **Step 2: Extend models in `models.py`**

Replace the entire `models.py`:

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
    tier: str = "bronze"
    avg_quality_score: Optional[float] = None
    success_rate: float = 0.0
    call_count: int = 0
    price_adjusted: bool = False

class CallServiceRequest(BaseModel):
    input: Any

class TransactionRecord(BaseModel):
    id: str
    service_id: str
    service_name: Optional[str] = None
    payment_hash: str
    amount_sats: int
    fee_sats: Optional[int] = None
    provider_sats: Optional[int] = None
    status: str
    created_at: str
    quality_score: Optional[int] = None
    score_reason: Optional[str] = None

class StatsResponse(BaseModel):
    total_volume_sats: int
    total_fees_sats: int
    total_calls: int
    marketplace_balance_sats: int
    top_rated_name: Optional[str] = None
    top_rated_tier: Optional[str] = None

class UpdatePriceRequest(BaseModel):
    price_sats: int

class UpdatePriceResponse(BaseModel):
    service_id: str
    price_sats: int
    tier: str
    tier_ceiling: Optional[int] = None
```

- [ ] **Step 3: Run existing tests to verify no regressions**

```bash
pytest tests/ -v
```

Expected: 14 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add config.py models.py
git commit -m "feat: add tier constants and extend models for reputation fields"
```

---

## Task 3: Scorer Module (TDD)

**Files:**
- Create: `services/scorer.py`
- Create: `tests/test_scorer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_scorer.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


def test_score_response_returns_score_and_reason():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='{"score": 82, "reason": "Clear 3-sentence summary"}')]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("services.scorer.anthropic.Anthropic", return_value=mock_client):
        from services.scorer import score_response
        score, reason = score_response(
            "web-summarizer",
            {"url": "https://example.com"},
            {"summary": "First sentence. Second sentence. Third sentence."},
        )

    assert score == 82
    assert reason == "Clear 3-sentence summary"


def test_score_response_accepts_string_input_for_web_summarizer():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='{"score": 70, "reason": "Decent summary"}')]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("services.scorer.anthropic.Anthropic", return_value=mock_client):
        from services.scorer import score_response
        score, reason = score_response(
            "web-summarizer",
            "https://example.com",  # string, not dict
            {"summary": "A summary."},
        )

    assert score == 70


def test_score_response_fallback_on_api_error():
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API unavailable")

    with patch("services.scorer.anthropic.Anthropic", return_value=mock_client):
        from services.scorer import score_response
        score, reason = score_response(
            "web-summarizer",
            {"url": "https://example.com"},
            {"summary": "..."},
        )

    assert score == 50
    assert reason == "scorer error"


def test_score_response_fallback_on_invalid_json():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="not valid json at all")]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("services.scorer.anthropic.Anthropic", return_value=mock_client):
        from services.scorer import score_response
        score, reason = score_response(
            "code-reviewer",
            {"code": "x = 1", "language": "python"},
            {"issues": []},
        )

    assert score == 50
    assert reason == "scorer error"


def test_score_and_update_writes_to_transaction(tmp_path, monkeypatch):
    monkeypatch.setattr("database.DB_PATH", str(tmp_path / "test.db"))
    from database import init_db, get_db
    init_db()

    with get_db() as conn:
        conn.execute(
            "INSERT INTO services (id, name, description, price_sats, endpoint_url, provider_wallet, created_at, is_active) VALUES (?,?,?,?,?,?,?,?)",
            ("svc1", "Web Summarizer", "desc", 25, "http://localhost/summarize", "wallet1", datetime.utcnow().isoformat(), 1),
        )
        conn.execute(
            "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, status, created_at) VALUES (?,?,?,?,?,?)",
            ("txn1", "svc1", "hash1", 25, "paid", datetime.utcnow().isoformat()),
        )

    with patch("services.scorer.score_response", return_value=(90, "Excellent summary")):
        from services.scorer import score_and_update
        score_and_update("txn1", "web-summarizer", {"url": "https://example.com"}, {"summary": "..."})

    with get_db() as conn:
        txn = conn.execute("SELECT quality_score, score_reason FROM transactions WHERE id='txn1'").fetchone()
        assert txn["quality_score"] == 90
        assert txn["score_reason"] == "Excellent summary"


def test_score_and_update_promotes_to_silver_at_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr("database.DB_PATH", str(tmp_path / "test.db"))
    from database import init_db, get_db
    init_db()

    with get_db() as conn:
        conn.execute(
            "INSERT INTO services (id, name, description, price_sats, endpoint_url, provider_wallet, created_at, is_active) VALUES (?,?,?,?,?,?,?,?)",
            ("svc1", "Web Summarizer", "desc", 25, "http://localhost/summarize", "wallet1", datetime.utcnow().isoformat(), 1),
        )
        # 9 previously scored transactions (avg 75 — meets silver score threshold)
        for i in range(9):
            conn.execute(
                "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, status, created_at, quality_score) VALUES (?,?,?,?,?,?,?)",
                (f"txn{i}", "svc1", f"hash{i}", 25, "paid", datetime.utcnow().isoformat(), 75),
            )
        # 10th transaction (unscored) — scoring it crosses the 10-call threshold
        conn.execute(
            "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, status, created_at) VALUES (?,?,?,?,?,?)",
            ("txn9", "svc1", "hash9", 25, "paid", datetime.utcnow().isoformat()),
        )

    with patch("services.scorer.score_response", return_value=(75, "Good quality")):
        from services.scorer import score_and_update
        score_and_update("txn9", "web-summarizer", {"url": "https://example.com"}, {"summary": "..."})

    with get_db() as conn:
        svc = conn.execute("SELECT tier, avg_quality_score FROM services WHERE id='svc1'").fetchone()
        assert svc["tier"] == "silver"
        assert abs(svc["avg_quality_score"] - 75.0) < 0.01


def test_score_and_update_clamps_price_on_tier_drop(tmp_path, monkeypatch):
    monkeypatch.setattr("database.DB_PATH", str(tmp_path / "test.db"))
    from database import init_db, get_db
    init_db()

    with get_db() as conn:
        # Service at silver tier with price 300 (within silver ceiling of 400)
        conn.execute(
            "INSERT INTO services (id, name, description, price_sats, endpoint_url, provider_wallet, created_at, is_active, tier) VALUES (?,?,?,?,?,?,?,?,?)",
            ("svc1", "Web Summarizer", "desc", 300, "http://localhost/summarize", "wallet1", datetime.utcnow().isoformat(), 1, "silver"),
        )
        # Only 5 scored transactions with very low scores -> drops to bronze
        for i in range(5):
            conn.execute(
                "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, status, created_at, quality_score) VALUES (?,?,?,?,?,?,?)",
                (f"txn{i}", "svc1", f"hash{i}", 300, "paid", datetime.utcnow().isoformat(), 40),
            )
        conn.execute(
            "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, status, created_at) VALUES (?,?,?,?,?,?)",
            ("txn5", "svc1", "hash5", 300, "paid", datetime.utcnow().isoformat()),
        )

    with patch("services.scorer.score_response", return_value=(40, "Poor quality")):
        from services.scorer import score_and_update
        score_and_update("txn5", "web-summarizer", {"url": "https://example.com"}, {"summary": "..."})

    with get_db() as conn:
        svc = conn.execute("SELECT tier, price_sats, price_adjusted FROM services WHERE id='svc1'").fetchone()
        assert svc["tier"] == "bronze"
        assert svc["price_sats"] == 150  # clamped to bronze ceiling
        assert svc["price_adjusted"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_scorer.py -v
```

Expected: ImportError or ModuleNotFoundError — `services/scorer.py` doesn't exist yet.

- [ ] **Step 3: Create `services/scorer.py`**

```python
import json
import anthropic
from database import get_db
from config import settings

RUBRICS = {
    "web-summarizer": (
        "You are evaluating a web page summary. Score it 0-100 on: "
        "(1) Is it exactly 3 sentences? "
        "(2) Is it coherent and reads as a plausible summary of a web page? "
        "(3) Is it free of obvious hallucination markers? "
        "The input URL was: {url}. The summary output was: {output}"
    ),
    "code-reviewer": (
        "You are evaluating a code review response. Score it 0-100 on: "
        "(1) Did it identify real issues in the code? "
        "(2) Are suggestions specific and actionable? "
        "(3) Is a numeric quality score present in the output? "
        "The input language was: {language}. The review output was: {output}"
    ),
    "sentiment-analyzer": (
        "You are evaluating a sentiment analysis response. Score it 0-100 on: "
        "(1) Is the verdict (positive/negative/neutral) plausible for the input text? "
        "(2) Is the confidence value a number between 0 and 1? "
        "(3) Is reasoning present in the output? "
        "The input text was: {text}. The analysis output was: {output}"
    ),
}

_INPUT_KEY = {
    "web-summarizer": "url",
    "sentiment-analyzer": "text",
}


def _normalize_input(service_name: str, input_data) -> dict:
    """Ensure input_data is a dict with the right key for the rubric template."""
    if isinstance(input_data, dict):
        return input_data
    key = _INPUT_KEY.get(service_name, "input")
    return {key: str(input_data)}


def score_response(service_name: str, input_data, output_data: dict) -> tuple[int, str]:
    """Score a provider response 0–100. Returns (score, one-sentence reason)."""
    normalized = _normalize_input(service_name, input_data)
    template = RUBRICS.get(
        service_name,
        "Evaluate this AI service response quality 0-100. Input: {input}. Output: {output}",
    )
    try:
        prompt_body = template.format(**normalized, output=json.dumps(output_data))
    except KeyError:
        prompt_body = (
            f"Evaluate this AI service response quality 0-100. "
            f"Input: {normalized}. Output: {output_data}"
        )

    prompt = (
        f"{prompt_body}\n\n"
        'Return JSON only, no other text: {"score": <integer 0-100>, "reason": "<one sentence>"}'
    )

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        result = json.loads(message.content[0].text)
        return int(result["score"]), str(result["reason"])
    except Exception:
        return 50, "scorer error"


def score_and_update(
    transaction_id: str,
    service_name: str,
    input_data,
    output_data: dict,
) -> None:
    """Background task: score a response and recompute provider reputation."""
    score, reason = score_response(service_name, input_data, output_data)

    with get_db() as conn:
        conn.execute(
            "UPDATE transactions SET quality_score=?, score_reason=? WHERE id=?",
            (score, reason, transaction_id),
        )

        row = conn.execute(
            "SELECT service_id FROM transactions WHERE id=?", (transaction_id,)
        ).fetchone()
        if not row:
            return
        service_id = row["service_id"]

        scores = conn.execute(
            """SELECT quality_score FROM transactions
               WHERE service_id=? AND quality_score IS NOT NULL
               ORDER BY created_at DESC LIMIT 20""",
            (service_id,),
        ).fetchall()
        scored_count = len(scores)
        avg_score = sum(r["quality_score"] for r in scores) / scored_count if scored_count else None

        total = conn.execute(
            "SELECT COUNT(*) as n FROM transactions WHERE service_id=?", (service_id,)
        ).fetchone()["n"]
        paid = conn.execute(
            "SELECT COUNT(*) as n FROM transactions WHERE service_id=? AND status='paid'",
            (service_id,),
        ).fetchone()["n"]
        success_rate = paid / total if total > 0 else 0.0

        if (
            avg_score is not None
            and avg_score >= settings.gold_min_score
            and scored_count >= settings.gold_min_calls
        ):
            new_tier = "gold"
        elif (
            avg_score is not None
            and avg_score >= settings.silver_min_score
            and scored_count >= settings.silver_min_calls
        ):
            new_tier = "silver"
        else:
            new_tier = "bronze"

        ceilings = {
            "bronze": settings.bronze_ceiling,
            "silver": settings.silver_ceiling,
            "gold": None,
        }
        ceiling = ceilings[new_tier]

        svc = conn.execute(
            "SELECT price_sats FROM services WHERE id=?", (service_id,)
        ).fetchone()
        current_price = svc["price_sats"]
        price_adjusted = False
        new_price = current_price
        if ceiling is not None and current_price > ceiling:
            new_price = ceiling
            price_adjusted = True

        conn.execute(
            """UPDATE services
               SET avg_quality_score=?, success_rate=?, tier=?,
                   price_sats=?, price_adjusted=?
               WHERE id=?""",
            (avg_score, success_rate, new_tier, new_price, price_adjusted, service_id),
        )
```

- [ ] **Step 4: Run scorer tests**

```bash
pytest tests/test_scorer.py -v
```

Expected: 7 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add services/scorer.py tests/test_scorer.py
git commit -m "feat: add scorer module with score_response and score_and_update"
```

---

## Task 4: Wire BackgroundTask in Router

**Files:**
- Modify: `services/router.py`

- [ ] **Step 1: Update `services/router.py`**

Replace the entire file:

```python
import base64
import uuid
import httpx
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from lexe import PaymentFilter
from database import get_db
from models import CallServiceRequest
from services.wallet_manager import get_marketplace_wallet
from services.scorer import score_and_update
from config import settings

router = APIRouter()
pending_payments: dict[str, dict] = {}


def _generate_macaroon(payment_hash: str) -> str:
    return base64.b64encode(f"v=1,hash={payment_hash}".encode()).decode()


def _payment_required(macaroon: str, invoice: str):
    raise HTTPException(
        status_code=402,
        detail="Payment Required",
        headers={"WWW-Authenticate": f'L402 macaroon="{macaroon}", invoice="{invoice}"'},
    )


def _verify_payment(payment_hash: str) -> bool:
    wallet = get_marketplace_wallet()
    payments = wallet.list_payments(PaymentFilter.ALL)
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
    pass


@router.post("/services/{service_id}/call")
async def call_service(
    service_id: str,
    req: CallServiceRequest,
    background_tasks: BackgroundTasks,
    authorization: str = Header(None),
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
            description=f"PayGent: {service['name']}",
        )
        macaroon = _generate_macaroon(invoice_obj.payment_hash)
        txn_id = str(uuid.uuid4())
        pending_payments[macaroon] = {
            "payment_hash": invoice_obj.payment_hash,
            "service_id": service_id,
            "txn_id": txn_id,
        }
        with get_db() as conn:
            conn.execute(
                "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, fee_sats, provider_sats, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    txn_id, service_id, invoice_obj.payment_hash,
                    service["price_sats"], None, None, "pending",
                    datetime.utcnow().isoformat(),
                ),
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
        _payment_required(macaroon, "")

    # Payment confirmed — call provider
    try:
        result = await _call_provider(service["endpoint_url"], req.input)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {str(e)}")

    # Record fee split
    fee_sats = int(service["price_sats"] * settings.fee_rate)
    provider_sats = service["price_sats"] - fee_sats

    txn_id = entry.get("txn_id")
    with get_db() as conn:
        conn.execute(
            """UPDATE transactions SET status='paid', fee_sats=?, provider_sats=?
               WHERE payment_hash=?""",
            (fee_sats, provider_sats, payment_hash),
        )

    _pay_provider(service["provider_wallet"], provider_sats)
    del pending_payments[macaroon]

    # Fire quality scorer as a background task (does not affect response latency)
    if txn_id:
        service_slug = service["name"].lower().replace(" ", "-")
        background_tasks.add_task(score_and_update, txn_id, service_slug, req.input, result)

    return result
```

- [ ] **Step 2: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests PASS. The background task is triggered in `test_call_with_valid_payment_returns_provider_response` but `score_and_update` is not patched — it will attempt to run with the mocked DB. Add a patch for it in that test to prevent real Claude API calls:

In `tests/test_router.py`, add to the existing `test_call_with_valid_payment_returns_provider_response`:

```python
# Add this import at the top of test_router.py:
# from unittest.mock import patch, MagicMock  (already imported)

# In the test body, add score_and_update to the patch list:
with patch("services.router.get_marketplace_wallet") as mock_wallet, \
     patch("services.router._verify_payment", return_value=True), \
     patch("services.router._call_provider", return_value={"result": "ok"}), \
     patch("services.router._pay_provider"), \
     patch("services.router.score_and_update"):   # <-- add this line
    sys.modules.pop("main", None)
    from main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    response = client.post(
        "/api/services/svc1/call",
        json={"input": "hello"},
        headers={"Authorization": f"L402 {macaroon}:deadbeef"}
    )
```

Run again:

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add services/router.py tests/test_router.py
git commit -m "feat: fire background quality scorer after each paid service call"
```

---

## Task 5: Registry — Updated List + PATCH Price Endpoint

**Files:**
- Modify: `services/registry.py`
- Modify: `tests/test_registry.py`

- [ ] **Step 1: Write failing tests for PATCH endpoint**

Add to `tests/test_registry.py`:

```python
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
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
pytest tests/test_registry.py::test_update_price_within_ceiling_succeeds tests/test_registry.py::test_update_price_exceeds_bronze_ceiling_returns_400 tests/test_registry.py::test_update_price_unknown_service_returns_404 tests/test_registry.py::test_list_services_includes_tier_and_call_count -v
```

Expected: FAIL — endpoints/fields don't exist yet.

- [ ] **Step 3: Update `services/registry.py`**

Replace the entire file:

```python
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from database import get_db
from models import (
    RegisterServiceRequest, RegisterServiceResponse,
    ServiceListItem, UpdatePriceRequest, UpdatePriceResponse,
)
from services.wallet_manager import get_marketplace_wallet
from config import settings

router = APIRouter()

_TIER_CEILINGS = {
    "bronze": lambda: settings.bronze_ceiling,
    "silver": lambda: settings.silver_ceiling,
    "gold": lambda: None,
}


@router.post("/services/register", response_model=RegisterServiceResponse)
def register_service(req: RegisterServiceRequest):
    wallet = get_marketplace_wallet()
    info = wallet.node_info()
    service_id = str(uuid.uuid4())
    provider_wallet = f"provider_{service_id[:8]}_{info.node_pk[:8]}"

    with get_db() as conn:
        conn.execute(
            "INSERT INTO services (id, name, description, price_sats, endpoint_url, provider_wallet, created_at, is_active) VALUES (?,?,?,?,?,?,?,?)",
            (
                service_id, req.name, req.description, req.price_sats,
                req.endpoint_url, provider_wallet,
                datetime.utcnow().isoformat(), 1,
            ),
        )
    return RegisterServiceResponse(service_id=service_id, provider_wallet=provider_wallet)


@router.get("/services", response_model=list[ServiceListItem])
def list_services():
    with get_db() as conn:
        rows = conn.execute(
            """SELECT s.id, s.name, s.description, s.price_sats,
                      s.tier, s.avg_quality_score, s.success_rate, s.price_adjusted,
                      COUNT(t.id) as call_count
               FROM services s
               LEFT JOIN transactions t ON t.service_id = s.id AND t.status = 'paid'
               WHERE s.is_active = 1
               GROUP BY s.id"""
        ).fetchall()
    return [ServiceListItem(**dict(r)) for r in rows]


@router.delete("/services/{service_id}")
def deactivate_service(service_id: str):
    with get_db() as conn:
        conn.execute("UPDATE services SET is_active=0 WHERE id=?", (service_id,))
    return {"status": "deactivated"}


@router.patch("/services/{service_id}/price", response_model=UpdatePriceResponse)
def update_service_price(service_id: str, req: UpdatePriceRequest):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, tier, is_active FROM services WHERE id=?", (service_id,)
        ).fetchone()

    if not row or not row["is_active"]:
        raise HTTPException(status_code=404, detail="Service not found")

    tier = row["tier"]
    ceiling = _TIER_CEILINGS[tier]()

    if ceiling is not None and req.price_sats > ceiling:
        raise HTTPException(
            status_code=400,
            detail=f"{tier.capitalize()} tier ceiling is {ceiling} sat",
        )

    with get_db() as conn:
        conn.execute(
            "UPDATE services SET price_sats=?, price_adjusted=0 WHERE id=?",
            (req.price_sats, service_id),
        )

    return UpdatePriceResponse(
        service_id=service_id,
        price_sats=req.price_sats,
        tier=tier,
        tier_ceiling=ceiling,
    )
```

- [ ] **Step 4: Register the PATCH route in `main.py`**

The PATCH endpoint is on the same `router` object in `registry.py` — it will be registered automatically with no change needed to `main.py` since `registry.router` is already included. Verify by running the tests.

- [ ] **Step 5: Run all tests**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add services/registry.py tests/test_registry.py
git commit -m "feat: add PATCH price endpoint and include reputation fields in service list"
```

---

## Task 6: Stats — Top Rated Card

**Files:**
- Modify: `services/stats.py`
- Modify: `tests/test_stats.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_stats.py`:

```python
def test_stats_includes_top_rated_when_enough_calls(tmp_path, monkeypatch):
    monkeypatch.setattr("database.DB_PATH", str(tmp_path / "test.db"))
    from database import init_db, get_db
    from datetime import datetime
    init_db()

    with get_db() as conn:
        conn.execute(
            "INSERT INTO services (id, name, description, price_sats, endpoint_url, provider_wallet, created_at, is_active, avg_quality_score) VALUES (?,?,?,?,?,?,?,?,?)",
            ("svc1", "Web Summarizer", "desc", 25, "http://x", "wallet", datetime.utcnow().isoformat(), 1, 88.0)
        )
        # 3 scored transactions (meets minimum)
        for i in range(3):
            conn.execute(
                "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, status, created_at, quality_score) VALUES (?,?,?,?,?,?,?)",
                (f"tx{i}", "svc1", f"hash{i}", 25, "paid", datetime.utcnow().isoformat(), 88)
            )

    import sys
    sys.modules.pop("main", None)

    from unittest.mock import patch, MagicMock
    with patch("services.stats.get_marketplace_wallet") as mock_wallet:
        mock_info = MagicMock()
        mock_info.balance_sats = 100
        mock_wallet.return_value.node_info.return_value = mock_info
        from main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.get("/api/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["top_rated_name"] == "Web Summarizer"
    assert data["top_rated_tier"] == "bronze"


def test_stats_top_rated_is_none_without_enough_calls(tmp_path, monkeypatch):
    monkeypatch.setattr("database.DB_PATH", str(tmp_path / "test.db"))
    from database import init_db, get_db
    from datetime import datetime
    init_db()

    with get_db() as conn:
        conn.execute(
            "INSERT INTO services (id, name, description, price_sats, endpoint_url, provider_wallet, created_at, is_active, avg_quality_score) VALUES (?,?,?,?,?,?,?,?,?)",
            ("svc1", "Web Summarizer", "desc", 25, "http://x", "wallet", datetime.utcnow().isoformat(), 1, 90.0)
        )
        # Only 2 scored transactions — below the 3-call minimum
        for i in range(2):
            conn.execute(
                "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, status, created_at, quality_score) VALUES (?,?,?,?,?,?,?)",
                (f"tx{i}", "svc1", f"hash{i}", 25, "paid", datetime.utcnow().isoformat(), 90)
            )

    import sys
    sys.modules.pop("main", None)

    from unittest.mock import patch, MagicMock
    with patch("services.stats.get_marketplace_wallet") as mock_wallet:
        mock_info = MagicMock()
        mock_info.balance_sats = 0
        mock_wallet.return_value.node_info.return_value = mock_info
        from main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.get("/api/stats")

    assert response.json()["top_rated_name"] is None
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
pytest tests/test_stats.py::test_stats_includes_top_rated_when_enough_calls tests/test_stats.py::test_stats_top_rated_is_none_without_enough_calls -v
```

Expected: FAIL — `top_rated_name` field missing from response.

- [ ] **Step 3: Update `services/stats.py`**

Replace the entire file:

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

        top = conn.execute(
            """SELECT s.name, s.tier
               FROM services s
               WHERE s.is_active = 1
                 AND s.avg_quality_score IS NOT NULL
                 AND (
                     SELECT COUNT(*) FROM transactions
                     WHERE service_id = s.id AND quality_score IS NOT NULL
                 ) >= 3
               ORDER BY s.avg_quality_score DESC
               LIMIT 1"""
        ).fetchone()

    return StatsResponse(
        total_volume_sats=row["volume"],
        total_fees_sats=row["fees"],
        total_calls=row["calls"],
        marketplace_balance_sats=balance,
        top_rated_name=top["name"] if top else None,
        top_rated_tier=top["tier"] if top else None,
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

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/stats.py tests/test_stats.py
git commit -m "feat: add top_rated_name and top_rated_tier to stats endpoint"
```

---

## Task 7: Frontend Types

**Files:**
- Modify: `frontend/lib/api.ts`

No TDD — TypeScript compiler is the test. Run `npm run build` after to verify.

> **Note:** This project uses a version of Next.js that may differ from common documentation. Check `frontend/node_modules/next/dist/docs/` if unfamiliar behavior is observed.

- [ ] **Step 1: Update `frontend/lib/api.ts`**

Replace the entire file:

```typescript
// frontend/lib/api.ts
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Service {
  id: string;
  name: string;
  description: string;
  price_sats: number;
  tier: string;
  avg_quality_score: number | null;
  success_rate: number;
  call_count: number;
  price_adjusted: boolean;
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
  quality_score: number | null;
  score_reason: string | null;
}

export interface Stats {
  total_volume_sats: number;
  total_fees_sats: number;
  total_calls: number;
  marketplace_balance_sats: number;
  top_rated_name: string | null;
  top_rated_tier: string | null;
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

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npm run build
```

Expected: build succeeds (there will be TypeScript errors in the components until Tasks 8–10 are done — run this again after Task 10).

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat: extend API types with tier, quality score, and top_rated fields"
```

---

## Task 8: ServiceCatalog — Tier Badge + Scores

**Files:**
- Modify: `frontend/components/ServiceCatalog.tsx`

> **Note:** Check `frontend/node_modules/next/dist/docs/` if any Next.js-specific behavior is unclear.

- [ ] **Step 1: Update `frontend/components/ServiceCatalog.tsx`**

Replace the entire file:

```tsx
// frontend/components/ServiceCatalog.tsx
import { Service } from "@/lib/api";

interface Props { services: Service[] }

const ICONS: Record<string, string> = {
  "Web Summarizer": "🔍",
  "Code Reviewer": "🧠",
  "Sentiment Analyzer": "📊",
};

const TIER_STYLES: Record<string, string> = {
  bronze: "bg-amber-900 text-amber-300 border border-amber-700",
  silver: "bg-blue-900 text-blue-300 border border-blue-700",
  gold: "bg-yellow-900 text-yellow-300 border border-yellow-700",
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
                <div className="flex items-center gap-2">
                  <span className="font-medium text-white">{s.name}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${TIER_STYLES[s.tier] ?? TIER_STYLES.bronze}`}>
                    {s.tier.charAt(0).toUpperCase() + s.tier.slice(1)}
                  </span>
                </div>
                <div className="text-sm text-gray-400">{s.description}</div>
                <div className="flex items-center gap-3 mt-1">
                  {s.avg_quality_score !== null && s.call_count >= 3 && (
                    <span className="text-xs text-gray-500">
                      Avg: {Math.round(s.avg_quality_score)}
                    </span>
                  )}
                  {s.call_count > 0 && (
                    <span className="text-xs text-gray-600">{s.call_count} calls</span>
                  )}
                </div>
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
git commit -m "feat: add tier badge, avg score, and call count to service catalog"
```

---

## Task 9: TransactionFeed — Quality Score

**Files:**
- Modify: `frontend/components/TransactionFeed.tsx`

- [ ] **Step 1: Update `frontend/components/TransactionFeed.tsx`**

Replace the entire file:

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
            className="px-4 py-3 border-b border-gray-800 last:border-0"
          >
            <div className="flex items-center justify-between">
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
                <span className="text-purple-400">fee: {t.fee_sats ?? "—"} sat</span>
                {t.status === "paid" && (
                  t.quality_score !== null ? (
                    <span className="text-green-400 font-mono">{t.quality_score}/100</span>
                  ) : (
                    <span className="text-gray-600 text-xs">scoring…</span>
                  )
                )}
                <span className="text-gray-500">{timeAgo(t.created_at)}</span>
              </div>
            </div>
            {t.score_reason && (
              <div className="text-xs text-gray-500 mt-1 ml-6">{t.score_reason}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/TransactionFeed.tsx
git commit -m "feat: show quality score and reason in transaction feed"
```

---

## Task 10: StatsBar — Top Rated Card

**Files:**
- Modify: `frontend/components/StatsBar.tsx`

- [ ] **Step 1: Update `frontend/components/StatsBar.tsx`**

Replace the entire file:

```tsx
// frontend/components/StatsBar.tsx
import { Stats } from "@/lib/api";

interface Props { stats: Stats }

const TIER_TEXT: Record<string, string> = {
  bronze: "text-amber-400",
  silver: "text-blue-400",
  gold: "text-yellow-400",
};

export default function StatsBar({ stats }: Props) {
  const cards = [
    { label: "Total Volume", value: `${stats.total_volume_sats.toLocaleString()} sat` },
    { label: "Fees Earned", value: `${stats.total_fees_sats.toLocaleString()} sat` },
    { label: "Total Calls", value: stats.total_calls.toString() },
    { label: "Wallet Balance", value: `${stats.marketplace_balance_sats.toLocaleString()} sat` },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
      {cards.map(({ label, value }) => (
        <div key={label} className="bg-gray-900 border border-purple-700 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-purple-400">{value}</div>
          <div className="text-sm text-gray-400 mt-1">{label}</div>
        </div>
      ))}
      <div className="bg-gray-900 border border-purple-700 rounded-xl p-4 text-center">
        {stats.top_rated_name ? (
          <>
            <div className={`text-lg font-bold truncate ${TIER_TEXT[stats.top_rated_tier ?? "bronze"] ?? "text-purple-400"}`}>
              {stats.top_rated_name}
            </div>
            <div className="text-sm text-gray-400 mt-1">Top Rated</div>
          </>
        ) : (
          <>
            <div className="text-2xl font-bold text-gray-600">—</div>
            <div className="text-sm text-gray-400 mt-1">Top Rated</div>
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify full TypeScript build**

```bash
cd frontend && npm run build
```

Expected: clean build, no TypeScript errors.

- [ ] **Step 3: Run full Python test suite one final time**

```bash
cd .. && pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/StatsBar.tsx
git commit -m "feat: add Top Rated card to stats bar"
```

---

## Done

At this point:
- Every paid call fires a background quality scorer
- Scores aggregate into Bronze/Silver/Gold tiers with price ceilings
- Providers can raise their price via PATCH up to their tier ceiling
- Dashboard shows tier badge, avg score, call count, per-transaction score, and Top Rated
- All tests pass, TypeScript compiles clean
