import os
import pytest
from database import init_db, get_db

def test_init_db_creates_tables():
    # init_db is called by isolated_env fixture
    with get_db() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = [t["name"] for t in tables]
    assert "services" in names
    assert "transactions" in names

def test_get_db_commits_on_exit():
    # Fresh isolated DB from fixture
    with get_db() as conn:
        conn.execute(
            "INSERT INTO services (id, name, description, price_sats, endpoint_url, provider_wallet, created_at, is_active) VALUES (?,?,?,?,?,?,?,?)",
            ("id1","name","desc",10,"http://x","wallet1","2026-01-01",1)
        )
    with get_db() as conn:
        row = conn.execute("SELECT id FROM services WHERE id=?", ("id1",)).fetchone()
    assert row is not None

def test_init_db_creates_agents_table():
    with get_db() as conn:
        names = [t["name"] for t in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
    assert "agents" in names
