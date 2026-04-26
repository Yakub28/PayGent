import os
import uuid
import pytest
import sys

# Set TESTING=1 immediately
os.environ["TESTING"] = "1"

@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """
    Ensure every single test runs with its own private database and mock lightning file.
    This prevents cross-test contamination and UNIQUE constraint errors.
    """
    uid = uuid.uuid4().hex
    db_path = str(tmp_path / f"test_{uid}.db")
    lightning_path = str(tmp_path / f"mock_{uid}.json")
    
    # Use environment variables that our code now respects dynamically
    monkeypatch.setenv("PAYGENT_DB_PATH", db_path)
    monkeypatch.setattr("services.mock_wallet.STATE_FILE", lightning_path)
    
    # We still need to clear modules because some might have cached DB_PATH at import time 
    # (like mock_wallet registry initialization)
    modules_to_clear = [
        "database", "services.mock_wallet", "services.wallet_manager",
        "services.agents", "services.registry", "services.router", "services.stats", "main"
    ]
    for mod in modules_to_clear:
        sys.modules.pop(mod, None)
    
    from database import init_db
    init_db()
    
    yield db_path

@pytest.fixture
def mock_settings_credentials(monkeypatch):
    """Prevent pydantic-settings from requiring real credentials during tests."""
    monkeypatch.setenv("LEXE_CLIENT_CREDENTIALS", "test_creds")
    monkeypatch.setenv("CONSUMER_LEXE_CREDENTIALS", "test_consumer_creds")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
