import pytest
from unittest.mock import patch


@pytest.fixture
def fresh_app(tmp_path, monkeypatch):
    monkeypatch.setattr("database.DB_PATH", str(tmp_path / "test.db"))
    from database import init_db
    init_db()
    import sys
    for mod in [
        "main",
        "services.providers.summarizer",
        "services.providers.code_reviewer",
        "services.providers.sentiment",
        "services.providers.code_writer",
        "services.providers.llm",
    ]:
        sys.modules.pop(mod, None)
    from main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_summarizer_returns_summary(fresh_app):
    with patch("httpx.get") as mock_get, \
         patch("services.providers.summarizer.claude_chat",
               return_value="This is a 3-sentence summary."):
        mock_get.return_value.text = "<html><body>Hello world content</body></html>"
        response = fresh_app.post(
            "/api/providers/summarize",
            json={"input": "https://example.com"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "This is a 3-sentence summary."


def test_summarizer_accepts_raw_text(fresh_app):
    with patch("services.providers.summarizer.claude_chat",
               return_value="Three sentence summary of the body."):
        response = fresh_app.post(
            "/api/providers/summarize",
            json={"input": "Just some raw text we want summarized."},
        )
    assert response.status_code == 200
    assert "summary" in response.json()


def test_code_reviewer_returns_review(fresh_app):
    with patch("services.providers.code_reviewer.claude_chat",
               return_value='{"bugs":[],"suggestions":["Use type hints"],"score":8}'):
        response = fresh_app.post("/api/providers/code-review", json={
            "input": {"code": "def foo(): pass", "language": "python"}
        })
    assert response.status_code == 200
    data = response.json()
    assert "bugs" in data or "review" in data


def test_sentiment_returns_analysis(fresh_app):
    with patch("services.providers.sentiment.claude_chat",
               return_value='{"sentiment":"positive","score":0.9,"confidence":0.95}'):
        response = fresh_app.post("/api/providers/sentiment", json={
            "input": "I love this product, it works great!"
        })
    assert response.status_code == 200
    data = response.json()
    assert "sentiment" in data or "analysis" in data


def test_code_writer_returns_code(fresh_app):
    with patch("services.providers.code_writer.claude_chat",
               return_value="def fib(n):\n    return n if n < 2 else fib(n-1)+fib(n-2)"):
        response = fresh_app.post("/api/providers/code-write", json={
            "input": {"prompt": "write a fibonacci function", "language": "python"}
        })
    assert response.status_code == 200
    body = response.json()
    assert "code" in body and "fib" in body["code"]
