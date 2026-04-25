import pytest

@pytest.fixture(autouse=True)
def mock_settings_credentials(monkeypatch):
    """Prevent pydantic-settings from requiring real credentials during tests."""
    monkeypatch.setenv("LEXE_CLIENT_CREDENTIALS", "test_creds")
    monkeypatch.setenv("CONSUMER_LEXE_CREDENTIALS", "test_consumer_creds")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_api_key")
