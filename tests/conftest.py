import pytest

@pytest.fixture(autouse=True)
def mock_settings_credentials(monkeypatch):
    """Prevent pydantic-settings from requiring real credentials during tests."""
    monkeypatch.setenv("LEXE_CLIENT_CREDENTIALS", "test_creds")
    monkeypatch.setenv("CONSUMER_LEXE_CREDENTIALS", "test_consumer_creds")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://test-ollama.invalid:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:14b")
