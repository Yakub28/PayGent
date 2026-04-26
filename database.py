import sqlite3
from contextlib import contextmanager

DB_PATH = "paygent.db"

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                price_sats INTEGER NOT NULL,
                endpoint_url TEXT NOT NULL,
                provider_wallet TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                provider_agent_id TEXT,
                service_type TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                service_id TEXT NOT NULL,
                payment_hash TEXT NOT NULL,
                amount_sats INTEGER NOT NULL,
                fee_sats INTEGER,
                provider_sats INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                consumer_agent_id TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                model TEXT NOT NULL,
                system_prompt TEXT,
                service_type TEXT,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """)
        # Best-effort migrations for upgrades from earlier schemas.
        for stmt in [
            "ALTER TABLE services ADD COLUMN provider_agent_id TEXT",
            "ALTER TABLE services ADD COLUMN service_type TEXT",
            "ALTER TABLE transactions ADD COLUMN consumer_agent_id TEXT",
            "ALTER TABLE agents ADD COLUMN service_type TEXT",
        ]:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
