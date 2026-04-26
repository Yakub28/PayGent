import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, UTC

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


def test_score_and_update_writes_to_transaction(isolated_env):
    from database import get_db
    from services.scorer import score_and_update
    
    with get_db() as conn:
        conn.execute(
            "INSERT INTO services (id, name, description, price_sats, endpoint_url, provider_wallet, created_at, is_active) VALUES (?,?,?,?,?,?,?,?)",
            ("svc1", "Web Summarizer", "desc", 25, "http://localhost/summarize", "wallet1", datetime.now(UTC).isoformat(), 1),
        )
        conn.execute(
            "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, status, created_at) VALUES (?,?,?,?,?,?)",
            ("txn1", "svc1", "hash1", 25, "paid", datetime.now(UTC).isoformat()),
        )

    with patch("services.scorer.score_response", return_value=(90, "Excellent summary")):
        score_and_update("txn1", "web-summarizer", {"url": "https://example.com"}, {"summary": "..."})

    with get_db() as conn:
        txn = conn.execute("SELECT quality_score, score_reason FROM transactions WHERE id='txn1'").fetchone()
        assert txn["quality_score"] == 90
        assert txn["score_reason"] == "Excellent summary"


def test_score_and_update_promotes_to_silver_at_threshold(isolated_env):
    from database import get_db
    from services.scorer import score_and_update

    with get_db() as conn:
        conn.execute(
            "INSERT INTO services (id, name, description, price_sats, endpoint_url, provider_wallet, created_at, is_active) VALUES (?,?,?,?,?,?,?,?)",
            ("svc1", "Web Summarizer", "desc", 25, "http://localhost/summarize", "wallet1", datetime.now(UTC).isoformat(), 1),
        )
        # 9 previously scored transactions (avg 75 — meets silver score threshold)
        for i in range(9):
            conn.execute(
                "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, status, created_at, quality_score) VALUES (?,?,?,?,?,?,?)",
                (f"txn{i}", "svc1", f"hash{i}", 25, "paid", datetime.now(UTC).isoformat(), 75),
            )
        # 10th transaction (unscored) — scoring it crosses the 10-call threshold
        conn.execute(
            "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, status, created_at) VALUES (?,?,?,?,?,?)",
            ("txn9", "svc1", "hash9", 25, "paid", datetime.now(UTC).isoformat()),
        )

    with patch("services.scorer.score_response", return_value=(75, "Good quality")):
        score_and_update("txn9", "web-summarizer", {"url": "https://example.com"}, {"summary": "..."})

    with get_db() as conn:
        svc = conn.execute("SELECT tier, avg_quality_score FROM services WHERE id='svc1'").fetchone()
        assert svc["tier"] == "silver"
        assert abs(svc["avg_quality_score"] - 75.0) < 0.01


def test_score_and_update_clamps_price_on_tier_drop(isolated_env):
    from database import get_db
    from services.scorer import score_and_update

    with get_db() as conn:
        # Service at silver tier with price 300 (within silver ceiling of 400)
        conn.execute(
            "INSERT INTO services (id, name, description, price_sats, endpoint_url, provider_wallet, created_at, is_active, tier) VALUES (?,?,?,?,?,?,?,?,?)",
            ("svc1", "Web Summarizer", "desc", 300, "http://localhost/summarize", "wallet1", datetime.now(UTC).isoformat(), 1, "silver"),
        )
        # Only 5 scored transactions with very low scores -> drops to bronze
        for i in range(5):
            conn.execute(
                "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, status, created_at, quality_score) VALUES (?,?,?,?,?,?,?)",
                (f"txn{i}", "svc1", f"hash{i}", 300, "paid", datetime.now(UTC).isoformat(), 40),
            )
        conn.execute(
            "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, status, created_at) VALUES (?,?,?,?,?,?)",
            ("txn5", "svc1", "hash5", 300, "paid", datetime.now(UTC).isoformat()),
        )

    with patch("services.scorer.score_response", return_value=(40, "Poor quality")):
        score_and_update("txn5", "web-summarizer", {"url": "https://example.com"}, {"summary": "..."})

    with get_db() as conn:
        svc = conn.execute("SELECT tier, price_sats, price_adjusted FROM services WHERE id='svc1'").fetchone()
        assert svc["tier"] == "bronze"
        assert svc["price_sats"] == 150  # clamped to bronze ceiling
        assert svc["price_adjusted"] == 1
