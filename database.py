import sqlite3
import os
from contextlib import contextmanager

def get_db_path():
    """Returns the current database path, allowing for dynamic overrides."""
    if os.environ.get("VERCEL"):
        return "/tmp/paygent.db"
    return os.environ.get("PAYGENT_DB_PATH", "paygent.db")

# Global DB_PATH for compatibility with existing tests
DB_PATH = get_db_path()

class LibsqlCursorAdapter:
    """Adapts libsql ResultSet to behave slightly more like a sqlite3 cursor/row."""
    def __init__(self, result_set):
        self.rows = result_set
        self.index = 0
    
    def fetchone(self):
        if self.index < len(self.rows):
            row = self.rows[self.index]
            self.index += 1
            return row
        return None
    
    def fetchall(self):
        return self.rows

class LibsqlConnectionAdapter:
    """Adapts libsql SyncConnection to match sqlite3 connection API."""
    def __init__(self, conn):
        self.conn = conn
    
    def execute(self, sql, parameters=()):
        # Handle ? to %s conversion if needed, but Turso supports ?
        res = self.conn.execute(sql, parameters)
        return LibsqlCursorAdapter(res)
    
    def close(self):
        self.conn.close()

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
        except Exception as e:
            msg = str(e).lower()
            if "duplicate" not in msg and "already exists" not in msg:
                pass

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

@contextmanager
def get_db():
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    
    if url:
        import libsql_client
        conn = libsql_client.connect(url, auth_token=token)
        try:
            yield LibsqlConnectionAdapter(conn)
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
