# PayGent Marketplace — Design Spec
**Date:** 2026-04-25
**Challenge:** Earn in the Agent Economy (Spiral × Hack-Nation)
**Approach:** Centralized Router (Approach A)

---

## Overview

PayGent is an agent-to-agent service marketplace. Service providers register HTTP endpoints with a price. Consumer agents discover services, pay via Lightning (L402 protocol), and receive the result. The marketplace routes all payments, takes a 10% fee, and pays the provider 90% on each successful call.

Payment rail: **Lightning Network via Lexe SDK** (Python, multi-wallet via Client Credentials).

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Next.js Dashboard                │
│         (service catalog, payment feed, balances)   │
└─────────────────────────┬───────────────────────────┘
                          │ REST
┌─────────────────────────▼───────────────────────────┐
│                  FastAPI Backend                    │
│                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │  Registry   │  │   Router     │  │  Wallet   │  │
│  │  (SQLite)   │  │  (L402 +     │  │  Manager  │  │
│  │             │  │   fee logic) │  │  (Lexe)   │  │
│  └─────────────┘  └──────────────┘  └───────────┘  │
└─────────────────────────────────────────────────────┘
          │                    │
          │ discover            │ pay + call
          │                    │
   ┌──────▼──────┐      ┌──────▼──────┐
   │  Consumer   │      │  Service    │
   │  Agent      │      │  Provider   │
   │  (Lexe      │      │  (FastAPI   │
   │   wallet)   │      │   handler)  │
   └─────────────┘      └─────────────┘
```

**Three backend modules:**
- **Registry** — SQLite, stores service metadata and provider wallet IDs
- **Router** — L402 flow, payment verification, provider call, fee split
- **Wallet Manager** — Lexe SDK wrapper, manages marketplace + provider wallets

---

## Data Models

### `services` table (SQLite)
| Field | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| name | string | Display name |
| description | string | What the service does |
| price_sats | integer | Cost to consumer |
| endpoint_url | string | Internal provider URL (never exposed) |
| provider_wallet | string | Lexe wallet ID for provider |
| created_at | timestamp | |
| is_active | boolean | Soft delete |

### `transactions` table (SQLite)
| Field | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| service_id | UUID | FK → services |
| payment_hash | string | Lightning payment hash |
| amount_sats | integer | Full price paid by consumer |
| fee_sats | integer | Marketplace cut (10%) |
| provider_sats | integer | Amount forwarded to provider |
| status | enum | `pending` / `paid` / `failed` |
| created_at | timestamp | |

### `pending_payments` (in-memory dict)
```python
{ macaroon: { payment_hash, service_id } }
```
Cleared after payment verified or on server restart.

---

## API Endpoints

### Provider
```
POST   /api/services/register
       body: { name, description, price_sats, endpoint_url }
       → creates service + Lexe wallet for provider
       → returns { service_id, provider_wallet_id }

DELETE /api/services/{service_id}
       → sets is_active = false
```

### Consumer
```
GET    /api/services
       → [{ id, name, description, price_sats }]
         (endpoint_url never included)

POST   /api/services/{service_id}/call
       body: { input: any }
       header: Authorization (optional, L402 token)
       → 402 + invoice if unpaid
       → 200 + provider response if paid
```

### Dashboard
```
GET    /api/stats
       → { total_volume_sats, total_fees_sats, total_calls, marketplace_balance }

GET    /api/transactions
       → last 50 transactions ordered by created_at desc
```

---

## Payment Flow

```
Step 1 — Consumer calls /api/services/{id}/call (no auth)
├── look up service in registry
├── marketplace_wallet.create_invoice(price_sats)
├── generate macaroon tied to payment_hash
├── store in pending_payments + transactions (status=pending)
└── return 402 + WWW-Authenticate: L402 macaroon="...", invoice="..."

Step 2 — Consumer pays invoice via their own Lexe wallet (client-side)

Step 3 — Consumer retries with Authorization: L402 {macaroon}:{preimage}
├── extract macaroon → look up payment_hash
├── marketplace_wallet.list_payments() → verify payment_hash is settled
├── mark transaction status=paid
├── POST { input } to provider endpoint_url (internal)
├── fee_sats = price_sats * FEE_RATE (default 0.10)
├── provider_sats = price_sats - fee_sats
├── marketplace_wallet.pay(provider_wallet_address, provider_sats)
├── update transaction (fee_sats, provider_sats)
└── return provider response to consumer

Step 4 — Provider failure after payment
├── transaction remains status=paid
├── return 502 to consumer with error detail
└── refund logic: out of scope for v1
```

---

## Pre-loaded Services

Three services registered at startup, implemented as FastAPI route handlers:

| Service | Price | Input | Action |
|---|---|---|---|
| Web Summarizer | 25 sat | `{ url }` | Fetch page → Claude API → 3-sentence summary |
| Code Reviewer | 100 sat | `{ code, language }` | Claude API → bugs, suggestions, quality score |
| Sentiment Analyzer | 50 sat | `{ text }` | Claude API → positive/negative/score/confidence |

All three call the Claude API internally. No separate server — they are route handlers within FastAPI.

---

## Dashboard (Next.js)

**Stack:** Next.js + Tailwind CSS. Polls `/api/stats` and `/api/transactions` every 3 seconds.

**Layout:**
- Stats bar: Total Volume / Fees Earned / Total Calls
- Service catalog: name, price, description (read-only display)
- Live payment feed: scrolling list of recent transactions with status, amounts, fees, timestamps

**No wallet logic in the frontend.** Dashboard is read-only. All payments are initiated by the consumer agent script.

---

## Configuration

Environment variables:
```
LEXE_CLIENT_CREDENTIALS=   # Lexe credentials for marketplace wallet
ANTHROPIC_API_KEY=         # For the three built-in services
FEE_RATE=0.10              # Marketplace routing fee (default 10%)
PROVIDER_BASE_URL=         # Internal base URL for provider handlers
```

---

## Out of Scope (v1)

- Refunds
- Provider authentication (any URL can be registered)
- Rate limiting per consumer
- Macaroon attenuation / caveats
- Streaming responses
- Multi-currency / fiat conversion
