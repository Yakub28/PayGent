# PayGent: Agent-to-Agent Micro-Service (L402 + Lexe)

PayGent is a Python-based prototype for the **Spiral Agent Economy**, demonstrating how autonomous agents can buy and sell "Reasoning-as-a-Service" using Bitcoin Lightning micro-payments via the L402 protocol and Lexe SDK.

## 🚀 Architecture
- **Provider (Seller):** A FastAPI service serving high-value intelligence. It enforces the **L402 protocol**, returning `402 Payment Required` with a Lightning Invoice.
- **Consumer (Buyer):** A LangChain-powered agent with a self-custodial **Lexe Wallet**. It autonomously handles 402 errors, pays invoices, and retries requests.

## 🛠 Tech Stack
- **API:** FastAPI (Async Python)
- **Payments:** Lexe Python SDK (`lexe-sdk`)
- **Intelligence Tooling:** LangChain Tools
- **Protocol:** L402 (Standard for paid API access)

## 📦 Setup

1. **Clone and Install Dependencies:**
   ```bash
   chmod +x setup_paygent.sh
   ./setup_paygent.sh
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure Environment:**
   Update the `.env` file with your Lexe Client Credentials:
   ```env
   LEXE_CLIENT_CREDENTIALS=your_base64_credentials_here
   ```

## 🏃‍♂️ Running the Demo

### Step 1: Start the Provider (Seller)
Launch the FastAPI server which acts as the intelligence provider.
```bash
python main.py
```

### Step 2: Run the Consumer Agent (Buyer)
In a new terminal (with `venv` activated), run the consumer agent:
```bash
python agents/consumer_agent.py
```

## 💡 Key Features & Iterations
- **Single-Wallet Demo Mode:** Handles the Lightning Network's "cannot pay self" restriction by verifying intent via macaroons, allowing for a complete demo using one Lexe node.
- **L402 Standard:** Implements the `WWW-Authenticate` and `Authorization` headers correctly for pay-per-use API access.
- **Autonomous Agency:** The agent uses its own budget to fulfill tasks, retrying requests only after successful payment handling.

## 📂 Project Structure
- `main.py`: Entry point for the FastAPI Provider.
- `services/intelligence.py`: L402 payment logic and verification.
- `agents/consumer_agent.py`: LangChain agent with L402 auto-payment client.
- `utils/lexe_client.py`: Shared Lexe wallet initialization logic.
