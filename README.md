# PayGent — Lightning-Powered Agent Marketplace

PayGent is an agent-to-agent service marketplace built for the **Spiral × Hack-Nation "Earn in the Agent Economy"** challenge. Service providers register HTTP endpoints with a price. Consumer agents discover services, pay via the **Lightning Network** (L402 protocol), and receive results. The marketplace routes all payments, takes a 10% routing fee, and automatically scores every response with Claude Haiku to build provider reputation.

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

**Payment flow:** Consumer calls service → receives `402 Payment Required` + Lightning invoice → pays via Lexe wallet → retries with L402 auth header → marketplace verifies payment, calls provider, deducts 10% fee, returns result → background scorer rates the response 0–100 and updates provider tier.

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

| Service | Price | Tier ceiling | Input | Output |
|---|---|---|---|---|
| Web Summarizer | 25 sat | Bronze (150 sat) | URL string | 3-sentence summary |
| Code Reviewer | 100 sat | Bronze (150 sat) | `{code, language}` | bugs, suggestions, score |
| Sentiment Analyzer | 50 sat | Bronze (150 sat) | text string | positive/negative/score |

Services start at Bronze. After 10 scored calls averaging ≥ 70 they unlock Silver (400 sat ceiling); after 25 calls averaging ≥ 85 they reach Gold (no ceiling).

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
# PayGent: Agent-to-Agent Micro-Service (L402 + Mock Lightning + Claude)

PayGent is a Python prototype for the **Spiral Agent Economy**: autonomous agents buy and sell "Reasoning-as-a-Service" via the L402 protocol over Lightning. Payments are simulated end-to-end with an in-memory mock Lightning wallet that issues, settles, and routes invoices instantly between agent wallets — no bitcoin, no channels, no external infra. Reasoning is delegated to Anthropic's Claude API; each agent picks its own model.

## 🚀 Architecture

- **Marketplace (FastAPI)** — Issues L402 invoices, verifies payment, splits fees, and forwards calls to the right provider's Claude.
- **Mock Lightning** — `services/mock_wallet.py` mints fake `bolt11` strings, tracks payment hashes, and moves sats atomically between wallet objects in a global registry. The L402 flow (`402` → `WWW-Authenticate` → pay → retry) is otherwise identical to a real Lightning setup.
- **Agents (DB-backed)** — Two roles:
  - **consumer** — has a sat balance and pays for services.
  - **provider** — owns one auto-registered service of a chosen `service_type` and earns sats.
- **Service types** — Multiple kinds of provider agent ship out of the box:
  - `code_writer` — writes a code snippet from a natural-language prompt.
  - `code_reviewer` — reviews code for bugs and quality (returns JSON).
  - `summarizer` — summarizes raw text or a URL in 3 sentences.
  - `sentiment` — classifies text as positive/negative/neutral.
- **Per-agent Claude** — Every agent record carries its own `model` (e.g. `claude-haiku-4-5`, `claude-haiku-4-5`, `claude-opus-4`) and optional `system_prompt`.
- **Simulation orchestrator** — Background asyncio task that drives high-frequency consumer↔provider transactions to stress-test the Lightning plumbing.

## 🛠 Tech Stack

- **API:** FastAPI (async Python)
- **Payments:** in-process mock wallets (Lightning-shaped: invoices, payment hashes, settlement)
- **LLM Backend:** [Anthropic Claude](https://docs.anthropic.com) via the official `anthropic` Python SDK
- **Frontend:** Next.js 16 / Tailwind 4 — three pages: Dashboard, Agents, Simulation

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
chmod +x setup_paygent.sh
./setup_paygent.sh
source venv/bin/activate
pip install -r requirements.txt
```

`.env`:

```env
FEE_RATE=0.10
PROVIDER_BASE_URL=http://localhost:8000
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-haiku-4-5
```

`LEXE_CLIENT_CREDENTIALS` is no longer required — leave it empty.

## 🏃‍♂️ Running

Two terminals.

**Terminal 1 — backend:**

```bash
source venv/bin/activate
python3 main.py
```

**Terminal 2 — frontend:**

```bash
cd frontend
npm install      # first time only
npm run dev
# open http://localhost:3000
```

The agent discovers services, pays for each via Lightning, and prints results. Watch the dashboard update live.

## API Endpoints

```
POST   /api/services/register        Register a new service
GET    /api/services                 List active services (tier, score, call count included)
DELETE /api/services/{id}            Deactivate a service
PATCH  /api/services/{id}/price      Update price (enforces tier ceiling)

POST   /api/services/{id}/call       Call a service (L402 payment gate)

GET    /api/stats                    Marketplace stats (volume, fees, calls, balance, top rated)
GET    /api/transactions             Last 50 transactions (quality_score, score_reason included)

POST   /api/providers/summarize      Web Summarizer (internal)
POST   /api/providers/code-review    Code Reviewer (internal)
POST   /api/providers/sentiment      Sentiment Analyzer (internal)
```

## Running Tests

```bash
pytest tests/ -v
```

All 29 tests pass. Tests mock Lexe and Anthropic — no real credentials needed.

## Project Structure

```
config.py                    Environment config (pydantic-settings)
database.py                  SQLite init + get_db() context manager
models.py                    Pydantic request/response schemas
main.py                      FastAPI app entry point

services/
  registry.py                Service register/list/deactivate/price endpoints
  router.py                  L402 payment gate + provider proxy + scorer dispatch
  scorer.py                  Background quality scorer (Claude Haiku rubrics, tier recompute)
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
    StatsBar.tsx             Volume / fees / calls / balance / top-rated cards
    ServiceCatalog.tsx       Service listing with tier badges, avg score, call count
    TransactionFeed.tsx      Live payment feed with quality scores and score reasons
  app/
    page.tsx                 Main dashboard (3s polling)

docs/
  superpowers/specs/         Design specification
  superpowers/plans/         Implementation plan
```

## Why Lightning

Traditional payment systems weren't built for machine-speed, high-frequency, cross-border micropayments. The Lightning Network settles transactions instantly for fractions of a cent — no accounts, no gatekeepers, no friction. PayGent demonstrates what agent commerce looks like when money moves at the speed of API calls.
## 🧠 Using the dashboard

1. Visit `http://localhost:3000`.
2. Go to **Agents** → register at least one **consumer** and one **provider**:
   - Pick the provider's **Service type** from the dropdown (Code Writer / Code Reviewer / Summarizer / Sentiment Analyzer).
   - Each provider auto-publishes that service to the marketplace at the chosen sat price.
   - Each consumer is created with the initial sat balance you specify.
3. Go to **Simulation** → set rate (calls/sec) and start.
4. Watch transactions stream in: prompt, Claude response, latency, sat split.
5. The **Dashboard** shows total volume, fees, marketplace balance, and the catalog.

## ⚡ How a transaction flows

1. Orchestrator picks a `(consumer, provider)` pair from the DB.
2. Looks up the provider's `service_type` and builds an appropriate sample input (code prompt, snippet to review, paragraph to summarize, sentence to classify).
3. `POST`s to `/api/services/{id}/call` → `402 Payment Required` with a fake `bolt11` invoice.
4. Consumer's mock wallet calls `pay_invoice(bolt11)` — sats are debited and credited to the marketplace wallet atomically.
5. Orchestrator retries with `Authorization: L402 <macaroon>:<preimage>`; the marketplace verifies the invoice was settled and forwards the request to the provider's endpoint.
6. The provider's endpoint loads the agent record, calls Claude with that agent's model + system prompt, and returns the result.
7. Marketplace records the transaction and moves the provider's share (price − fee) into the provider agent's wallet.

## 📂 Project Structure

```
main.py                       # FastAPI app + router wiring
config.py                     # pydantic-settings (Anthropic key/model, fee rate, …)
database.py                   # sqlite schema (services, transactions, agents)
models.py                     # pydantic schemas
services/
  mock_wallet.py              # in-memory Lightning simulation
  wallet_manager.py           # wallet factory (marketplace + per-agent)
  router.py                   # L402 + payment plumbing
  registry.py                 # service CRUD
  agents.py                   # agent CRUD
  simulation.py               # high-frequency orchestrator
  simulation_router.py        # start/stop/status endpoints
  stats.py                    # /api/stats and /api/transactions
  providers/
    llm.py                    # claude_chat helper (Anthropic Messages API)
    types.py                  # service-type catalog (key, label, sample input, …)
    code_writer.py / code_reviewer.py / summarizer.py / sentiment.py
agents/consumer_agent.py      # legacy single-shot demo (still works)
frontend/                     # Next.js dashboard
  app/page.tsx                # Dashboard
  app/agents/page.tsx         # Agent registration & balances
  app/simulation/page.tsx     # Simulation control + live event feed
```

## 🧪 Tests

```bash
source venv/bin/activate
pytest
```
