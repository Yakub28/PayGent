import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture
def client():
    import sys
    for mod in ["main", "services.providers.summarizer", "services.providers.code_reviewer", "services.providers.sentiment"]:
        sys.modules.pop(mod, None)
    from main import app
    from fastapi.testclient import TestClient
    return TestClient(app)

def test_summarizer_returns_summary(client):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="This is a 3-sentence summary.")]

    with patch("httpx.get") as mock_get, \
         patch("services.providers.summarizer.anthropic_client.messages.create",
               return_value=mock_response):
        mock_get.return_value.text = "<html><body>Hello world content</body></html>"
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        response = client.post("/api/providers/summarize", json={"input": "https://example.com"})

    assert response.status_code == 200
    assert "summary" in response.json()

def test_code_reviewer_returns_review(client):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"bugs":[],"suggestions":["Use type hints"],"score":8}')]

    with patch("services.providers.code_reviewer.anthropic_client.messages.create",
               return_value=mock_response):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        response = client.post("/api/providers/code-review", json={
            "input": {"code": "def foo(): pass", "language": "python"}
        })

    assert response.status_code == 200
    data = response.json()
    assert "bugs" in data or "review" in data

def test_sentiment_returns_analysis(client):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"sentiment":"positive","score":0.9,"confidence":0.95}')]

    with patch("services.providers.sentiment.anthropic_client.messages.create",
               return_value=mock_response):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        response = client.post("/api/providers/sentiment", json={
            "input": "I love this product, it works great!"
        })

    assert response.status_code == 200
    data = response.json()
    assert "sentiment" in data or "analysis" in data
