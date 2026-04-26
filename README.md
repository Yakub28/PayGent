# PayGent: Agent-to-Agent Micro-Service (L402 + Mock Lightning)

PayGent is a Python-based prototype for the **Spiral Agent Economy**: autonomous agents buy and sell "Reasoning-as-a-Service" via the L402 protocol over Lightning. To make the demo run anywhere — without bitcoin, without real channels, without ever leaving your laptop — payments are simulated end-to-end with an in-memory mock Lightning wallet that issues, settles, and routes invoices instantly between agent wallets.

## 🚀 Architecture

- **Marketplace (FastAPI)** — Issues L402 invoices, verifies payment, splits fees, and forwards calls to the right provider's LLM.
- **Mock Lightning** — `services/mock_wallet.py` mints fake `bolt11` strings, tracks payment hashes, and moves sats atomically between wallet objects in a global registry. The L402 flow (`402` → `WWW-Authenticate` → pay → retry with `Authorization`) is otherwise unchanged from a real Lightning setup.
- **Agents (DB-backed)** — Two roles: **consumer** agents have a balance and pay for code; **provider** agents own a service ("Code Writer") and earn sats. Every agent has its own Ollama model identity (default `llama3.1`) plus optional system prompt and base URL.
- **Simulation orchestrator** — A background asyncio task that drives high-frequency consumer↔provider transactions to stress-test the Lightning plumbing.

## 🛠 Tech Stack

- **API:** FastAPI (async Python)
- **Payments:** in-process mock wallets (Lightning-shaped: invoices, payment hashes, settlement)
- **LLM Backend:** any [Ollama](https://ollama.com) server (default model `llama3.1`; the marketplace's static services still use `qwen3:14b` if you keep that)
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
OLLAMA_BASE_URL=http://100.92.119.114:11434
OLLAMA_MODEL=qwen3:14b
OLLAMA_TIMEOUT=120
```

`LEXE_CLIENT_CREDENTIALS` is no longer required — leave it empty.

### Make sure Ollama is reachable

On the remote PC (`ssh nurzhan@100.92.119.114`) bind Ollama to all interfaces:

```bash
sudo systemctl edit ollama
# add:
#   [Service]
#   Environment="OLLAMA_HOST=0.0.0.0:11434"
sudo systemctl restart ollama
```

Then from your dev machine:

```bash
curl http://100.92.119.114:11434/api/tags
```

If you want each agent to actually run on Llama 3.1, pull it once:

```bash
ssh nurzhan@100.92.119.114 'ollama pull llama3.1'
```

The backend will also try to pull each agent's model on registration as a best-effort background task.

## 🏃‍♂️ Running

Three terminals.

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

**Terminal 3 — (optional) legacy demo agent:**

```bash
source venv/bin/activate
python3 agents/consumer_agent.py
```

## 🧠 Using the dashboard

1. Visit `http://localhost:3000`.
2. Go to **Agents** → register at least one **provider** and one **consumer**:
   - Each provider auto-publishes a Code Writer service at the chosen sat price.
   - Each consumer is created with the initial sat balance you specify.
3. Go to **Simulation** → set rate (calls/sec) and start.
4. Watch transactions stream in: prompt, generated code, latency, sat split.
5. Back on the **Dashboard** you'll see total volume, fees, and the marketplace's running balance.

## ⚡ How a transaction flows

1. Orchestrator picks a `(consumer, provider)` pair from the DB.
2. Consumer's LLM (or the prompt bank, in stress mode) invents a coding task.
3. Orchestrator `POST`s to `/api/services/{id}/call` → `402 Payment Required` with a fake `bolt11` invoice.
4. Consumer's mock wallet calls `pay_invoice(bolt11)` — sats are debited and credited to the marketplace wallet atomically.
5. Orchestrator retries with `Authorization: L402 <macaroon>:<preimage>`; the marketplace verifies the invoice was settled and forwards the request to the provider's `code-write` endpoint.
6. The provider's endpoint loads the agent record, calls Ollama with that agent's model + system prompt, and returns the code.
7. Marketplace records the transaction and moves the provider's share (price − fee) into the provider agent's wallet.

## 📂 Project Structure

```
main.py                       # FastAPI app + router wiring
config.py                     # pydantic-settings (Ollama URL, fee rate, …)
database.py                   # sqlite schema (services, transactions, agents)
models.py                     # pydantic schemas
services/
  mock_wallet.py              # in-memory Lightning simulation
  wallet_manager.py           # wallet factory (marketplace + per-agent)
  router.py                   # L402 + payment plumbing
  registry.py                 # service CRUD
  agents.py                   # agent CRUD + Ollama auto-pull
  simulation.py               # high-frequency orchestrator
  simulation_router.py        # start/stop/status endpoints
  stats.py                    # /api/stats and /api/transactions
  providers/
    code_writer.py            # the per-agent code-writing endpoint
    summarizer.py / code_reviewer.py / sentiment.py  # legacy seed providers
    llm.py                    # ollama_chat / ollama_pull / ollama_has_model
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
