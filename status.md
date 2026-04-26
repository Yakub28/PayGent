# PayGent — Project Status (April 26, 2026)

> Authoritative context for downstream agents/LLMs. The repo has diverged
> significantly from the original single-shot Lexe + LangChain demo: payments
> are mocked, the marketplace hosts multiple agent kinds, and reasoning is
> served by Anthropic Claude. Read this file end-to-end before merging.

---

## 1. One-line summary

PayGent is an L402-style agent marketplace where autonomous **consumer agents**
buy "Reasoning-as-a-Service" from autonomous **provider agents** with simulated
Lightning sats. Reasoning is delegated to **Anthropic Claude** (one model
identity per agent). A built-in orchestrator drives **high-frequency
simulations** to stress the payment plumbing.

## 2. Current system architecture

```
  ┌──────────────────────────────┐         ┌─────────────────────────────┐
  │ Next.js dashboard (3000)     │ ─REST─▶ │ FastAPI marketplace (8000)  │
  │ /  /agents  /simulation      │         │  L402, fee split, registry  │
  └──────────────────────────────┘         │  + simulation orchestrator  │
                                            └──────────┬──────────────────┘
                                                       │ httpx
                                                       ▼
                                            ┌─────────────────────────────┐
                                            │ Provider endpoints (8000)   │
                                            │  /api/providers/*           │
                                            │   load agent record →       │
                                            │   call Anthropic Claude     │
                                            └──────────┬──────────────────┘
                                                       │
                                                       ▼
                                            ┌─────────────────────────────┐
                                            │ MockWallet registry         │
                                            │  marketplace + N agents     │
                                            │  bolt11 + payment_hash      │
                                            └─────────────────────────────┘
```

Everything runs in one Python process. There is no real Lightning node, no
real Lexe, no real bitcoin. Wallets are in-memory objects in
`services/mock_wallet.py::REGISTRY`.

## 3. Tech stack (current, not historical)

| Layer        | Choice                                                       |
| ------------ | ------------------------------------------------------------ |
| API server   | FastAPI + uvicorn (sync handlers; one async sim loop)        |
| Persistence  | SQLite (`paygent.db`) via `database.py` (services/transactions/agents) |
| Payments     | In-memory mock Lightning (`services/mock_wallet.py`) — bolt11 strings, settled/expired states, atomic balance moves |
| Auth         | L402 (`Authorization: L402 <macaroon>:<preimage>`)           |
| LLM          | Anthropic Claude via the official `anthropic` Python SDK     |
| Frontend     | Next.js 16 + Tailwind 4 (3 pages: Dashboard / Agents / Simulation) |
| Tests        | pytest (16 passing, no network)                              |

`requirements.txt` no longer ships `lexe-sdk`; it now ships `anthropic`.
LangChain is still listed but is **no longer used** anywhere — safe to remove
on merge if convenient.

## 4. What exists today (✅ done)

### 4.1 Mock Lightning settlement
- `MockWallet` mirrors the subset of the old Lexe API actually used
  (`create_invoice`, `pay_invoice`, `list_payments`, `node_info`).
- A global thread-safe `_Registry` routes payments: when wallet A pays a
  bolt11 issued by wallet B, the registry debits A and credits B atomically.
- Self-pays (issuer == payer) are no-ops and never raise — needed because the
  legacy single-wallet demo path still exists.

### 4.2 Marketplace
- `services/registry.py` — register / list / deactivate services. Each row
  stores `service_type`, `provider_agent_id`, `endpoint_url`, `price_sats`.
- `services/router.py` — implements the 402 → pay → retry handshake.
  - First call: mints a mock invoice on the marketplace wallet, returns
    `WWW-Authenticate: L402 macaroon=..., invoice=...`, writes a `pending`
    transaction row.
  - Retry with `Authorization`: verifies the invoice is settled, forwards the
    request to the provider's endpoint (injecting `provider_agent_id` into
    the JSON payload), then runs `_settle_provider` to move
    `provider_share = price - fee` from marketplace → provider's wallet.
- `services/stats.py` — `/api/stats` (totals + marketplace balance) and
  `/api/transactions` (paginated to last 50, joined with service name).

### 4.3 Agents subsystem
- `services/agents.py` — CRUD + topup. Provider creation auto-registers a
  service of the chosen `service_type`.
- DB columns: `id, name, role, model, system_prompt, service_type, created_at,
  is_active`. (Older `ollama_base_url` column is migrated-in but ignored.)
- `roles`: `consumer | provider`.
- Per-agent identity: every Claude call uses the agent's stored `model` (e.g.
  `claude-sonnet-4-5`) and optional `system_prompt`. Different agents can run
  different Claude models simultaneously.
- Wallet life-cycle: every agent has a `MockWallet` keyed by `agent_id`,
  created on first reference and dropped on `DELETE /api/agents/{id}`.

### 4.4 Provider service catalog
Centralised in **`services/providers/types.py`** (this is the file that adds
new kinds — keep it as the single source of truth).

| key             | label              | default sat | endpoint                       |
| --------------- | ------------------ | ----------- | ------------------------------ |
| `code_writer`   | Code Writer        | 15          | `/api/providers/code-write`    |
| `code_reviewer` | Code Reviewer      | 25          | `/api/providers/code-review`   |
| `summarizer`    | Summarizer         | 10          | `/api/providers/summarize`     |
| `sentiment`     | Sentiment Analyzer | 8           | `/api/providers/sentiment`     |

Each `ServiceTypeSpec` carries:
- `sample_input()` — generates a payload for that type (used by the simulation).
- `prompt_for_event(payload)` — renders a one-line description for the UI feed.
- `extract_result(response)` — flattens the provider's JSON into a single
  string for the simulation's generic `result_text` field.

Every provider endpoint:
1. Parses input + reads `provider_agent_id` from the payload.
2. Loads the agent row to grab `model` + `system_prompt`.
3. Honours a `stress: true` flag → returns a stub response without hitting
   Claude (powers the high-frequency simulation mode).
4. Otherwise calls `claude_chat(...)` with the agent's model identity.

### 4.5 LLM helper
`services/providers/llm.py` exposes a single function:

```python
claude_chat(prompt, *, max_tokens=512, temperature=0.2,
            system=None, model=None) -> str
```

Wraps `anthropic.Anthropic().messages.create(...)`, joins all text blocks,
returns plain string. The client is cached via `@lru_cache`. Default model
is `settings.anthropic_model` (configurable in `.env`).

### 4.6 High-frequency simulation
- `services/simulation.py` — single asyncio task on the FastAPI loop. Each tick:
  1. Pick a random `(consumer, provider)` pair from `agents`.
  2. Look up `service_type` → call `spec.sample_input()`.
  3. If `use_llm=False`, set `payload['stress'] = True`.
  4. Run the L402 round-trip end-to-end (`POST` → 402 → `pay_invoice` on
     consumer's mock wallet → retry with macaroon + fake preimage).
  5. Auto-topup the consumer if balance < price (so demos never stall).
  6. Append a `SimulationEvent` to a 200-deep ring buffer.
- Configurable `rate_per_sec` (≤ 200), `use_llm` toggle, optional
  `max_iterations`. Status counters: iterations / successes / failures /
  last_event.
- HTTP control surface: `services/simulation_router.py` exposes
  `POST /api/simulation/start`, `POST /api/simulation/stop`,
  `GET /api/simulation/status`, `GET /api/simulation/events?limit=N`.

### 4.7 Frontend
- **`/` Dashboard** — totals (volume, fees, calls, marketplace balance),
  service catalog, last-50 transactions feed. Auto-refreshes every 3 s.
- **`/agents`** — register / topup / remove agents. Provider form has a
  **Service type** dropdown (populated from `/api/service-types`); the price
  field auto-defaults to that type's recommended price. Languages and
  Ollama-base-URL fields have been removed. Default model field is
  `claude-sonnet-4-5`.
- **`/simulation`** — rate slider, `use_llm` toggle, start/stop button, live
  status panel, and an event feed showing prompt / Claude result /
  service-type badge / latency / sats moved.

### 4.8 Tests
`pytest` — 16 tests, all passing offline (no Claude API needed):
- `tests/test_database.py` — schema migrations.
- `tests/test_registry.py` — service register / list / deactivate.
- `tests/test_router.py` — full L402 happy path and 402 path, with
  `_settle_provider` mocked.
- `tests/test_stats.py` — totals math.
- `tests/test_providers.py` — each of the four provider endpoints, with
  `claude_chat` patched.

## 5. Key files (where to make merge edits)

```
main.py                       FastAPI app + lifespan + uvicorn entry
config.py                     pydantic-settings (anthropic_api_key, anthropic_model, fee_rate, …)
database.py                   sqlite schema + idempotent migrations
models.py                     all pydantic schemas (RegisterAgentRequest, SimulationEvent, …)
services/
  mock_wallet.py              in-memory Lightning, REGISTRY singleton
  wallet_manager.py           wallet factories
  router.py                   L402 + fee split
  registry.py                 service CRUD
  agents.py                   agent CRUD + provider auto-registration
  stats.py                    totals + tx feed
  simulation.py               orchestrator (async loop)
  simulation_router.py        start/stop/status/events HTTP surface
  providers/
    llm.py                    claude_chat helper (single Anthropic entrypoint)
    types.py                  ServiceTypeSpec catalog ★ add new types here
    code_writer.py / code_reviewer.py / summarizer.py / sentiment.py
    seed.py                   legacy demo seed (still used at startup)
agents/consumer_agent.py      legacy single-shot CLI demo (still works)
frontend/
  app/page.tsx                Dashboard
  app/agents/page.tsx         Agents
  app/simulation/page.tsx     Simulation control + feed
  components/Nav.tsx          Sticky top nav
  lib/api.ts                  Typed REST client
tests/                        pytest suite
status.md                     ← this file
README.md                     end-user setup
.env / .env.example           ANTHROPIC_API_KEY + ANTHROPIC_MODEL (default claude-sonnet-4-5)
```

The `utils/` and `services/intelligence.py` directories are vestigial from the
original Lexe demo — not imported by anything; deletable.

## 6. Public HTTP surface (for the frontend or another caller)

```
GET    /api/stats
GET    /api/services
DELETE /api/services/{id}
POST   /api/services/register

GET    /api/service-types
GET    /api/agents
POST   /api/agents
DELETE /api/agents/{id}
POST   /api/agents/{id}/topup

POST   /api/services/{id}/call          ← L402-protected; main fast path

GET    /api/transactions

POST   /api/simulation/start
POST   /api/simulation/stop
GET    /api/simulation/status
GET    /api/simulation/events?limit=N

POST   /api/providers/code-write
POST   /api/providers/code-review
POST   /api/providers/summarize
POST   /api/providers/sentiment
```

Pydantic schemas for every request/response live in `models.py`.

## 7. Configuration

`.env` keys actively read:

```env
FEE_RATE=0.10                    # marketplace cut (0..1)
PROVIDER_BASE_URL=http://localhost:8000
ANTHROPIC_API_KEY=sk-ant-...     # required for live LLM calls
ANTHROPIC_MODEL=claude-sonnet-4-5
```

`LEXE_CLIENT_CREDENTIALS` and `CONSUMER_LEXE_CREDENTIALS` keys are still read
by `Settings` for backward compatibility but **must be empty** — they no
longer wire to anything.

## 8. Run book

```bash
# Backend
source venv/bin/activate
pip install -r requirements.txt
python3 main.py        # uvicorn on :8000 with reload

# Frontend
cd frontend
npm install            # first run
npm run dev            # :3000

# Tests (no network needed)
pytest -q
```

To exercise the system:
1. Open `http://localhost:3000/agents`, register at least one consumer and
   one provider per `service_type` you want to test.
2. Open `/simulation`, set rate (e.g. 5/s), pick "Use Claude for real
   responses" or leave off for stress-mode plumbing test, click Start.
3. Watch transactions flow on `/`.

## 9. Known gaps / good next merge targets

- **`utils/lexe_client.py` and `services/intelligence.py`** are dead code from
  the original demo. Safe to delete during merge.
- **`langchain` requirement** is not imported anywhere — drop from
  `requirements.txt` if downstream merge doesn't reintroduce it.
- **`datetime.utcnow()`** is used throughout; FastAPI raises
  `DeprecationWarning` for it. Should be migrated to
  `datetime.now(datetime.UTC)` repo-wide.
- **Macaroon caveats** are still cosmetic — the macaroon is just
  `base64("v=1,hash=…")`. Real attenuation (expiry, path scope) would be a
  natural next-merge feature.
- **Persistence** of agent wallets is in-memory only; restarting the
  backend zeros every balance. The `agents` table persists, but balances are
  lost. If we want true persistence we need to serialize `MockWallet` state.
- **Simulation `use_llm=true` mode** can rate-limit against Anthropic at high
  rates; the orchestrator currently has no per-second cap on real LLM calls.
- **One-service-per-provider** is a deliberate simplification. The DB allows
  multiple services per `provider_agent_id`, but the agent registration flow
  only creates one. Multi-service providers need UI + listing changes only.
- **No auth on the marketplace itself**: anyone who can hit
  `POST /api/agents` can spend the bank. Fine for the demo, not for prod.

## 10. What recently changed (for reviewers)

The most recent merge replaced the previous Ollama-based reasoning backend
with Anthropic Claude and generalised the agent model:

1. Removed every `ollama_*` setting, helper, and field. `services/providers/llm.py`
   now exposes only `claude_chat`. There is no model-pull endpoint anymore.
2. All four provider endpoints were rewritten to use `claude_chat`, accept a
   `provider_agent_id`, and honour a `stress` short-circuit.
3. Added `services/providers/types.py` and the four-key service-type catalog.
4. Added `service_type` columns to `services` and `agents` (with idempotent
   migrations); dropped reliance on the unused `ollama_base_url` column.
5. Agents page lost the *Languages* and *Ollama base URL* fields and gained a
   *Service type* dropdown driven by `/api/service-types`. Default model is
   `claude-sonnet-4-5`.
6. Simulation orchestrator now picks per-type sample inputs and renders a
   generic `result_text` per event — the UI shows code, JSON reviews,
   summaries, and sentiment classifications in the same feed.
7. README and `.env.example` were rewritten for the new setup. `pytest` and
   `tsc --noEmit` are both green.
