# PayGent Reputation & Dynamic Pricing — Design Spec
**Date:** 2026-04-26
**Feature:** Provider reputation scoring + tier-based dynamic pricing

---

## Overview

Every paid service call is automatically quality-scored by Claude Haiku after the consumer receives their result. Scores accumulate into a provider reputation, expressed as both a 0–100 average and a Bronze/Silver/Gold tier. Tier sets a price ceiling; providers can raise their price up to the ceiling as their reputation grows.

Trust is grounded in real paid transaction history — not self-reported ratings.

---

## Architecture

No new processes or schedulers. All scoring runs as a FastAPI `BackgroundTask` fired after each successful provider call. The existing 3-second dashboard polling picks up new scores automatically.

```
Consumer calls service
    → Router returns provider response to consumer (unchanged latency)
    → BackgroundTask fires: score_and_update(transaction_id, service_name, input, output)
        → scorer.py calls Claude Haiku with service-specific rubric
        → writes quality_score + score_reason to transactions
        → recomputes avg_quality_score, success_rate, tier on services
```

---

## Data Model Changes

### `transactions` table — 2 new columns

| Column | Type | Notes |
|---|---|---|
| `quality_score` | INTEGER NULL | 0–100; null until scorer runs |
| `score_reason` | TEXT NULL | One-sentence Claude explanation |

### `services` table — 4 new columns

| Column | Type | Notes |
|---|---|---|
| `tier` | TEXT | `bronze` / `silver` / `gold`; default `bronze` |
| `avg_quality_score` | REAL NULL | Rolling average of last 20 scored transactions for this service |
| `success_rate` | REAL | Paid calls / total calls; updated each transaction |
| `price_adjusted` | BOOLEAN | True if price was auto-clamped on tier drop; reset when provider manually updates price |

### Tier thresholds (constants in `config.py`)

| Tier | Min avg_quality | Min scored calls | Price ceiling |
|---|---|---|---|
| Bronze | — | — | 150 sat |
| Silver | 70 | 10 | 400 sat |
| Gold | 85 | 25 | unlimited |

Tier is recomputed after every scored transaction. Providers can drop tiers if quality falls.

---

## New Module: `services/scorer.py`

Single public function:

```python
def score_response(service_name: str, input: dict, output: dict) -> tuple[int, str]:
    """Returns (score 0-100, one-sentence reason)."""
```

Calls Claude Haiku with a service-specific rubric:

- **web-summarizer**: Is the summary exactly 3 sentences? Is it coherent and free of obvious hallucination markers? Does it read as a plausible summary of a web page? (Scorer only has the URL + output — accuracy against source is not checked.)
- **code-reviewer**: Did it identify real issues? Are suggestions actionable? Is a quality score present in the output?
- **sentiment-analyzer**: Is the verdict (positive/negative) plausible given the text? Is confidence a number 0–1? Is reasoning present?

Prompt ends with: *"Return JSON only: `{"score": <0-100>, "reason": "<one sentence>"}`"*

Falls back to `score=50, reason="scorer error"` on any exception so a failed scorer never blocks the transaction record.

---

## Changes to `services/router.py`

After returning the provider response to the consumer, add:

```python
background_tasks.add_task(score_and_update, transaction_id, service.name, payload.input, result)
```

`score_and_update` lives in `services/scorer.py` as a second public function:
1. Calls `scorer.score_response()`
2. Writes `quality_score` + `score_reason` to the transaction row
3. Recomputes `avg_quality_score` (last 20 scored transactions for this service)
4. Recomputes `success_rate` (paid / total calls)
5. Recomputes `tier` based on thresholds
6. If tier dropped and `price_sats > new_ceiling`: clamps `price_sats` to ceiling, sets `price_adjusted = true`

---

## New API Endpoint

```
PATCH /api/services/{service_id}/price
body: { price_sats: int }
→ 200 { service_id, price_sats, tier, tier_ceiling }
→ 400 if price_sats > tier ceiling
→ 404 if service not found or inactive
```

No authentication — consistent with existing register/deactivate endpoints (internal/demo context).

---

## Dashboard Changes

### Service Catalog cards
- Tier badge with color: Bronze (gray) / Silver (blue) / Gold (yellow)
- Avg quality score: `"Avg: 84"` (hidden if fewer than 3 scored calls)
- Call count: `"23 calls"`

### Transaction Feed rows
- Quality score once scored: `"82/100"`
- `"scoring..."` placeholder while `quality_score` is null
- Score reason as a secondary line below the transaction row

### Stats Bar
- New card: **Top Rated** — name + tier badge of the service with the highest `avg_quality_score` (minimum 3 scored calls to qualify)

No new pages. No new polling endpoints. Existing `/api/services` and `/api/transactions` responses carry the new fields.

---

## Out of Scope

- Authentication on the price PATCH endpoint
- Provider-initiated re-scoring requests
- Consumer ability to dispute a score
- Scores for failed transactions (only successful paid calls are scored)
- Streaming responses
