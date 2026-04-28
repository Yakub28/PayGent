import sqlite3
import os
import logging
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

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
        res = self.conn.execute(sql, parameters)
        return LibsqlCursorAdapter(res)
    
    def close(self):
        self.conn.close()

class PostgresConnectionAdapter:
    """Adapts psycopg2 connection to match the API expected by the app."""
    def __init__(self, conn):
        self.conn = conn
    
    def execute(self, sql, parameters=()):
        cursor = self.conn.cursor()
        cursor.execute(sql, parameters)
        return cursor
    
    def close(self):
        self.conn.close()
    
    def commit(self):
        self.conn.commit()

def _migrate_db(conn):
    """Add new columns to existing databases. Silently skips if already present."""
    migrations = [
        "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS quality_score INTEGER",
        "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS score_reason TEXT",
        "ALTER TABLE services ADD COLUMN IF NOT EXISTS tier TEXT NOT NULL DEFAULT 'bronze'",
        "ALTER TABLE services ADD COLUMN IF NOT EXISTS avg_quality_score REAL",
        "ALTER TABLE services ADD COLUMN IF NOT EXISTS success_rate REAL NOT NULL DEFAULT 0.0",
        "ALTER TABLE services ADD COLUMN IF NOT EXISTS price_adjusted INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE services ADD COLUMN IF NOT EXISTS provider_id TEXT",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
            if hasattr(conn, 'commit'): conn.commit()
        except Exception as e:
            logger.debug("Migration skipped: %s", e)

def init_db():
    logger.info("Initializing database...")
    try:
        with get_db() as conn:
            # Test connection
            conn.execute("SELECT 1")
            # Tables creation...
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
            if hasattr(conn, 'commit'): conn.commit()
            _migrate_db(conn)
            logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error("Database initialization failed: %s", e)
        # Don't re-raise in startup to avoid crashing the whole process if possible,
        # but in many cases we need the DB.
        raise

@contextmanager
def get_db():
    # Priority 1: Supabase / Generic Postgres
    db_url = os.environ.get("DATABASE_URL")
    
    # Priority 2: Turso
    turso_url = os.environ.get("TURSO_DATABASE_URL")
    turso_token = os.environ.get("TURSO_AUTH_TOKEN")
    
    if db_url:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        # Handle connection pool issues or SSL if needed
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        try:
            yield PostgresConnectionAdapter(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    elif turso_url:
        import libsql_client
        conn = libsql_client.connect(turso_url, auth_token=turso_token)
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
