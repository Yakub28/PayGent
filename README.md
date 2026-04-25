# PayGent — Lightning-Powered Agent Marketplace

PayGent is an agent-to-agent service marketplace built for the **Spiral × Hack-Nation "Earn in the Agent Economy"** challenge. Service providers register HTTP endpoints with a price. Consumer agents discover services, pay via the **Lightning Network** (L402 protocol), and receive results. The marketplace routes all payments and takes a 10% routing fee.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              Next.js Dashboard (port 3000)          │
│       service catalog · payment feed · stats        │
└─────────────────────────┬───────────────────────────┘
                          │ REST (CORS enabled)
┌─────────────────────────▼───────────────────────────┐
│              FastAPI Backend (port 8000)            │
│                                                     │
│  Registry · Router (L402) · Stats · Providers      │
│  Wallet Manager (Lexe SDK)  ·  SQLite DB           │
└──────────────┬──────────────────────┬───────────────┘
               │ discover             │ pay + call
        ┌──────▼──────┐       ┌───────▼──────┐
        │  Consumer   │       │   Service    │
        │  Agent      │       │   Provider   │
        │  (Lexe      │       │   (internal  │
        │   wallet)   │       │    handler)  │
        └─────────────┘       └──────────────┘
```

**Payment flow:** Consumer calls service → receives `402 Payment Required` + Lightning invoice → pays via Lexe wallet → retries with L402 auth header → marketplace verifies payment, calls provider, deducts 10% fee, returns result.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (Python, async) |
| Database | SQLite |
| Payments | Lexe SDK + Lightning Network (L402 protocol) |
| AI Services | Anthropic Claude API (Haiku) |
| Frontend | Next.js 16 + TypeScript + Tailwind CSS |
| Consumer Agent | Python + requests |

## Pre-loaded Services

| Service | Price | Input | Output |
|---|---|---|---|
| Web Summarizer | 25 sat | URL string | 3-sentence summary |
| Code Reviewer | 100 sat | `{code, language}` | bugs, suggestions, score |
| Sentiment Analyzer | 50 sat | text string | positive/negative/score |

## Setup

### 1. Clone and install backend dependencies

```bash
chmod +x setup_paygent.sh
./setup_paygent.sh
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in your credentials:

```env
LEXE_CLIENT_CREDENTIALS=your_marketplace_lexe_credentials
CONSUMER_LEXE_CREDENTIALS=your_consumer_lexe_credentials
ANTHROPIC_API_KEY=your_anthropic_api_key
FEE_RATE=0.10
PROVIDER_BASE_URL=http://localhost:8000
```

### 3. Install frontend dependencies

```bash
cd frontend && npm install && cd ..
```

## Running the Demo

### Terminal 1 — Backend

```bash
source venv/bin/activate
python main.py
```

The server starts on `http://localhost:8000`, initializes the SQLite DB, and seeds the 3 marketplace services automatically.

### Terminal 2 — Dashboard

```bash
cd frontend && npm run dev
```

Open `http://localhost:3000` — the dashboard auto-refreshes every 3 seconds.

### Terminal 3 — Consumer Agent

```bash
python agents/consumer_agent.py
```

The agent discovers services, pays for each via Lightning, and prints results. Watch the dashboard update live.

## API Endpoints

```
POST   /api/services/register        Register a new service
GET    /api/services                 List active services (endpoint_url hidden)
DELETE /api/services/{id}            Deactivate a service

POST   /api/services/{id}/call       Call a service (L402 payment gate)

GET    /api/stats                    Marketplace stats (volume, fees, calls, balance)
GET    /api/transactions             Last 50 transactions

POST   /api/providers/summarize      Web Summarizer (internal)
POST   /api/providers/code-review    Code Reviewer (internal)
POST   /api/providers/sentiment      Sentiment Analyzer (internal)
```

## Running Tests

```bash
pytest tests/ -v
```

All 13 tests pass. Tests mock Lexe and Anthropic — no real credentials needed.

## Project Structure

```
config.py                    Environment config (pydantic-settings)
database.py                  SQLite init + get_db() context manager
models.py                    Pydantic request/response schemas
main.py                      FastAPI app entry point

services/
  registry.py                Service register/list/deactivate endpoints
  router.py                  L402 payment gate + provider proxy
  stats.py                   Stats and transactions endpoints
  wallet_manager.py          Lexe wallet singleton (marketplace + consumer)
  providers/
    summarizer.py            Web Summarizer handler
    code_reviewer.py         Code Reviewer handler
    sentiment.py             Sentiment Analyzer handler
    seed.py                  Seeds 3 services on startup

agents/
  consumer_agent.py          Standalone L402 auto-pay demo script

frontend/
  lib/api.ts                 API client (fetchStats, fetchServices, fetchTransactions)
  components/
    StatsBar.tsx             Volume / fees / calls / balance cards
    ServiceCatalog.tsx       Service listing with icons and prices
    TransactionFeed.tsx      Live payment feed with timestamps
  app/
    page.tsx                 Main dashboard (3s polling)

docs/
  superpowers/specs/         Design specification
  superpowers/plans/         Implementation plan
```

## Why Lightning

Traditional payment systems weren't built for machine-speed, high-frequency, cross-border micropayments. The Lightning Network settles transactions instantly for fractions of a cent — no accounts, no gatekeepers, no friction. PayGent demonstrates what agent commerce looks like when money moves at the speed of API calls.
