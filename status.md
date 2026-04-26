# PayGent Project Status — April 26, 2026

## Current State: Complete (Mock Payments Active)

All features built and tested. 29/29 tests passing. TypeScript compiles clean. Demo runs end-to-end.

Real Lightning settlement is temporarily replaced with a file-based mock wallet while Lexe network access is resolved. The full L402 flow works end-to-end — only the payment rail is mocked. Swapping in real Lexe requires changing one function in `services/wallet_manager.py`.

## What Was Built

### Backend (FastAPI + SQLite + Mock Lightning)

- **Service Registry** — providers register endpoints with a price; consumers discover services without exposing internal URLs
- **L402 Payment Router** — full Lightning paywall: issues invoices, verifies settlement, proxies to provider, records 10% fee split
- **Mock Wallet** — file-based (`mock_payments.json`) payment simulation; same interface as real Lexe SDK; drop-in replaceable
- **3 AI Provider Services** — Web Summarizer (25 sat), Code Reviewer (100 sat), Sentiment Analyzer (50 sat) — all powered by Claude Haiku
- **Reputation Scoring** — every paid call is scored 0–100 by Claude Haiku via a service-specific rubric, running as a `BackgroundTask` (zero latency impact); score + one-sentence reason stored per transaction
- **Tier System** — Bronze / Silver / Gold tiers computed from rolling avg quality score (last 20 calls) and total scored call count; recomputed after every transaction
- **Dynamic Pricing** — tier sets a price ceiling (Bronze 150 sat, Silver 400 sat, Gold unlimited); price auto-clamped on tier drop; providers can raise price via `PATCH /api/services/{id}/price`
- **Stats API** — total volume, fees earned, call count, live wallet balance, top-rated service

### Frontend (Next.js + TypeScript + Tailwind)

- **Stats Bar** — live volume, fees, calls, marketplace wallet balance, top-rated service
- **Service Catalog** — tier badge (Bronze/Silver/Gold), avg quality score, call count
- **Transaction Feed** — quality score per row, "scoring…" placeholder until scored, score reason as secondary line
- **3-second auto-polling** — dashboard updates without refresh

### Consumer Agent

- Discovers services via REST
- Auto-handles L402: detects 402, parses invoice, pays via mock wallet, retries with auth header
- Runs 3 demo tasks end-to-end

## Tech Stack

| Component | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, SQLite |
| Payments | Mock wallet (file-based) → Lexe SDK (drop-in swap) |
| AI | Anthropic Claude Haiku (providers + reputation scorer) |
| Frontend | Next.js 16, TypeScript, Tailwind CSS v4 |
| Tests | pytest, 29 tests, all passing |

## File Counts

- 15 Python source files
- 6 test files (29 tests)
- 5 TypeScript/TSX files

## Switching to Real Lightning

When Lexe credentials are available:

1. Replace `_load_wallet` in `services/wallet_manager.py`:

```python
from lexe import Credentials, LexeWallet, WalletConfig, ClientCredentials

def _load_wallet(creds_str: str) -> LexeWallet:
    config = WalletConfig.mainnet()  # or testnet3()
    client_creds = ClientCredentials.from_string(creds_str)
    creds = Credentials.from_client_credentials(client_creds)
    wallet = LexeWallet.load_or_fresh(config, creds)
    try:
        wallet.provision(creds)
    except Exception:
        pass
    return wallet
```

2. Set real credentials in `.env`:
```
LEXE_CLIENT_CREDENTIALS=your_marketplace_credentials
CONSUMER_LEXE_CREDENTIALS=your_consumer_credentials
```

3. Delete `mock_payments.json` if present.

Nothing else changes.

## Running the Demo

**Terminal 1 — Backend:**
```bash
source venv/bin/activate
python main.py
```

**Terminal 2 — Dashboard:**
```bash
cd frontend && npm run dev
```

**Terminal 3 — Consumer Agent:**
```bash
python agents/consumer_agent.py
```

## Remaining Improvements (Post-Hackathon)

- Replace `@app.on_event("startup")` with FastAPI lifespan handler (deprecation warning)
- Replace `datetime.utcnow()` with `datetime.now(UTC)` throughout
- Real provider wallet payouts (currently no-op, recorded in DB)
- Refund logic for failed provider calls
- Rate limiting and macaroon attenuation
- Multi-node testing across independent Lexe instances
- Authentication on the price PATCH endpoint
