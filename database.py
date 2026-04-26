import sqlite3
from contextlib import contextmanager

DB_PATH = "paygent.db"

def _migrate_db(conn):
    """Add new columns to existing databases. Silently skips if already present."""
    migrations = [
        "ALTER TABLE transactions ADD COLUMN quality_score INTEGER",
        "ALTER TABLE transactions ADD COLUMN score_reason TEXT",
        "ALTER TABLE services ADD COLUMN tier TEXT NOT NULL DEFAULT 'bronze'",
        "ALTER TABLE services ADD COLUMN avg_quality_score REAL",
        "ALTER TABLE services ADD COLUMN success_rate REAL NOT NULL DEFAULT 0.0",
        "ALTER TABLE services ADD COLUMN price_adjusted INTEGER NOT NULL DEFAULT 0",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass  # column already exists

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
                tier TEXT NOT NULL DEFAULT 'bronze',
                avg_quality_score REAL,
                success_rate REAL NOT NULL DEFAULT 0.0,
                price_adjusted INTEGER NOT NULL DEFAULT 0
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
                score_reason TEXT
            )
        """)
        _migrate_db(conn)

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
