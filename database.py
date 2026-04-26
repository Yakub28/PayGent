import sqlite3
import os
from contextlib import contextmanager

def get_db_path():
    """Returns the current database path, allowing for dynamic overrides."""
    return os.environ.get("PAYGENT_DB_PATH", "paygent.db")

# Global DB_PATH for compatibility with existing tests
DB_PATH = get_db_path()

def _migrate_db(conn):
    """Add new columns to existing databases. Silently skips if already present."""
    migrations = [
        "ALTER TABLE transactions ADD COLUMN quality_score INTEGER",
        "ALTER TABLE transactions ADD COLUMN score_reason TEXT",
        "ALTER TABLE services ADD COLUMN tier TEXT NOT NULL DEFAULT 'bronze'",
        "ALTER TABLE services ADD COLUMN avg_quality_score REAL",
        "ALTER TABLE services ADD COLUMN success_rate REAL NOT NULL DEFAULT 0.0",
        "ALTER TABLE services ADD COLUMN price_adjusted INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE services ADD COLUMN provider_id TEXT",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                raise

def init_db():
    # Ensure the global DB_PATH is up to date with the environment
    global DB_PATH
    DB_PATH = get_db_path()
    
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
                tier TEXT NOT NULL DEFAULT 'bronze',
                avg_quality_score REAL,
                success_rate REAL NOT NULL DEFAULT 0.0,
                price_adjusted INTEGER NOT NULL DEFAULT 0,
                provider_agent_id TEXT,
                service_type TEXT,
                provider_id TEXT
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
                quality_score INTEGER,
                score_reason TEXT,
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS providers (
                id           TEXT PRIMARY KEY,
                company_name TEXT NOT NULL,
                api_key      TEXT NOT NULL UNIQUE,
                created_at   TEXT NOT NULL
            )
        """)
        _migrate_db(conn)
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
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
