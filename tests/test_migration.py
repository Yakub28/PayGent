import pytest

def test_migration_adds_new_columns(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("database.DB_PATH", db_path)
    import sqlite3
    from database import get_db

    # Create old-schema DB manually at the patched path (simulates existing install)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE services (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
            price_sats INTEGER NOT NULL, endpoint_url TEXT NOT NULL,
            provider_wallet TEXT NOT NULL, created_at TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE transactions (
            id TEXT PRIMARY KEY, service_id TEXT NOT NULL,
            payment_hash TEXT NOT NULL, amount_sats INTEGER NOT NULL,
            fee_sats INTEGER, provider_sats INTEGER,
            status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

    from database import init_db
    init_db()

    with get_db() as c:
        cols_svc = {r[1] for r in c.execute("PRAGMA table_info(services)")}
        cols_txn = {r[1] for r in c.execute("PRAGMA table_info(transactions)")}

    assert {"tier", "avg_quality_score", "success_rate", "price_adjusted"}.issubset(cols_svc)
    assert {"quality_score", "score_reason"}.issubset(cols_txn)
