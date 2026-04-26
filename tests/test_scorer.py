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


def test_score_response_accepts_string_input_for_web_summarizer():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='{"score": 70, "reason": "Decent summary"}')]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("services.scorer.anthropic.Anthropic", return_value=mock_client):
        from services.scorer import score_response
        score, reason = score_response(
            "web-summarizer",
            "https://example.com",  # string, not dict
            {"summary": "A summary."},
        )

    assert score == 70


def test_score_response_fallback_on_api_error():
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API unavailable")

    with patch("services.scorer.anthropic.Anthropic", return_value=mock_client):
        from services.scorer import score_response
        score, reason = score_response(
            "web-summarizer",
            {"url": "https://example.com"},
            {"summary": "..."},
        )

    assert score == 50
    assert reason == "scorer error"


def test_score_response_handles_markdown_wrapped_json():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='```json\n{"score": 77, "reason": "Good output"}\n```')]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("services.scorer.anthropic.Anthropic", return_value=mock_client):
        from services.scorer import score_response
        score, reason = score_response(
            "sentiment-analyzer",
            {"text": "great product"},
            {"verdict": "positive", "confidence": 0.9},
        )

    assert score == 77
    assert reason == "Good output"


def test_score_response_fallback_on_invalid_json():
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="not valid json at all")]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("services.scorer.anthropic.Anthropic", return_value=mock_client):
        from services.scorer import score_response
        score, reason = score_response(
            "code-reviewer",
            {"code": "x = 1", "language": "python"},
            {"issues": []},
        )

    assert score == 50
    assert reason == "scorer error"


def test_score_and_update_writes_to_transaction(tmp_path, monkeypatch):
    monkeypatch.setattr("database.DB_PATH", str(tmp_path / "test.db"))
    from database import init_db, get_db
    init_db()

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
        from services.scorer import score_and_update
        score_and_update("txn1", "web-summarizer", {"url": "https://example.com"}, {"summary": "..."})

    with get_db() as conn:
        txn = conn.execute("SELECT quality_score, score_reason FROM transactions WHERE id='txn1'").fetchone()
        assert txn["quality_score"] == 90
        assert txn["score_reason"] == "Excellent summary"


def test_score_and_update_promotes_to_silver_at_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr("database.DB_PATH", str(tmp_path / "test.db"))
    from database import init_db, get_db
    init_db()

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
        from services.scorer import score_and_update
        score_and_update("txn9", "web-summarizer", {"url": "https://example.com"}, {"summary": "..."})

    with get_db() as conn:
        svc = conn.execute("SELECT tier, avg_quality_score FROM services WHERE id='svc1'").fetchone()
        assert svc["tier"] == "silver"
        assert abs(svc["avg_quality_score"] - 75.0) < 0.01


def test_score_and_update_stays_bronze_below_call_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr("database.DB_PATH", str(tmp_path / "test.db"))
    from database import init_db, get_db
    init_db()

    with get_db() as conn:
        conn.execute(
            "INSERT INTO services (id, name, description, price_sats, endpoint_url, provider_wallet, created_at, is_active) VALUES (?,?,?,?,?,?,?,?)",
            ("svc1", "Web Summarizer", "desc", 25, "http://localhost/summarize", "wallet1", datetime.now(UTC).isoformat(), 1),
        )
        # Only 8 previously scored transactions — below the 10-call silver minimum
        for i in range(8):
            conn.execute(
                "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, status, created_at, quality_score) VALUES (?,?,?,?,?,?,?)",
                (f"txn{i}", "svc1", f"hash{i}", 25, "paid", datetime.now(UTC).isoformat(), 75),
            )
        conn.execute(
            "INSERT INTO transactions (id, service_id, payment_hash, amount_sats, status, created_at) VALUES (?,?,?,?,?,?)",
            ("txn8", "svc1", "hash8", 25, "paid", datetime.now(UTC).isoformat()),
        )

    with patch("services.scorer.score_response", return_value=(75, "Good")):
        from services.scorer import score_and_update
        score_and_update("txn8", "web-summarizer", {"url": "https://example.com"}, {"summary": "..."})

    with get_db() as conn:
        svc = conn.execute("SELECT tier FROM services WHERE id='svc1'").fetchone()
        assert svc["tier"] == "bronze"  # 9 scored calls — one below silver threshold of 10


def test_score_and_update_clamps_price_on_tier_drop(tmp_path, monkeypatch):
    monkeypatch.setattr("database.DB_PATH", str(tmp_path / "test.db"))
    from database import init_db, get_db
    init_db()

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
        from services.scorer import score_and_update
        score_and_update("txn5", "web-summarizer", {"url": "https://example.com"}, {"summary": "..."})

    with get_db() as conn:
        svc = conn.execute("SELECT tier, price_sats, price_adjusted FROM services WHERE id='svc1'").fetchone()
        assert svc["tier"] == "bronze"
        assert svc["price_sats"] == 150  # clamped to bronze ceiling
        assert svc["price_adjusted"] == 1
