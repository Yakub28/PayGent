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
- **Per-agent Claude** — Every agent record carries its own `model` (e.g. `claude-haiku-4-5`, `claude-sonnet-4-5`, `claude-opus-4`) and optional `system_prompt`.
- **Simulation orchestrator** — Background asyncio task that drives high-frequency consumer↔provider transactions to stress-test the Lightning plumbing.

## 🛠 Tech Stack

- **API:** FastAPI (async Python)
- **Payments:** in-process mock wallets (Lightning-shaped: invoices, payment hashes, settlement)
- **LLM Backend:** [Anthropic Claude](https://docs.anthropic.com) via the official `anthropic` Python SDK
- **Frontend:** Next.js 16 / Tailwind 4 — three pages: Dashboard, Agents, Simulation

## 📦 Setup

```bash
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
ANTHROPIC_MODEL=claude-sonnet-4-5
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
