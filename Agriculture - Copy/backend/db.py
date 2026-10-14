import psycopg2
from psycopg2.extras import RealDictCursor
import sqlite3
import logging
from backend.config import DB_CONFIG, SQLITE_DB_PATH

logger = logging.getLogger(__name__)

class DatabaseManager:
    _mode = None  # "postgres" or "sqlite"

    @classmethod
    def get_connection(cls):
        """Try connecting to PostgreSQL first, fallback to SQLite if needed."""
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cls._mode = "postgres"
            return conn
        except Exception as e:
            logger.warning(f"PostgreSQL connection failed ({e}). Falling back to SQLite.")
            cls._mode = "sqlite"
            conn = sqlite3.connect(str(SQLITE_DB_PATH))
            conn.row_factory = sqlite3.Row
            return conn

    @classmethod
    def get_cursor(cls, conn):
        if cls._mode == "postgres":
            return conn.cursor(cursor_factory=RealDictCursor)
        return conn.cursor()

    @classmethod
    def is_postgres(cls):
        if cls._mode is None:
            # test
            try:
                conn = psycopg2.connect(**DB_CONFIG)
                conn.close()
                cls._mode = "postgres"
            except Exception:
                cls._mode = "sqlite"
        return cls._mode == "postgres"

def execute_query(query, params=None, fetch_all=True, commit=False):
    """Execute query with automatic dictionary cursor formatting."""
    conn = DatabaseManager.get_connection()
    try:
        cur = DatabaseManager.get_cursor(conn)
        # Adapt parameters if needed for sqlite (? vs %s)
        if not DatabaseManager.is_postgres():
            query = query.replace("%s", "?")
            query = query.replace("NOW()", "CURRENT_TIMESTAMP")
            query = query.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
            query = query.replace("JSONB", "TEXT")
        
        cur.execute(query, params or ())
        
        if commit:
            conn.commit()
            if "RETURNING" in query.upper() and DatabaseManager.is_postgres():
                return cur.fetchone()
            return True

        if fetch_all:
            rows = cur.fetchall()
            if not DatabaseManager.is_postgres():
                return [dict(row) for row in rows]
            return [dict(r) for r in rows]
        else:
            row = cur.fetchone()
            if row and not DatabaseManager.is_postgres():
                return dict(row)
            return dict(row) if row else None
    finally:
        cur.close()
        conn.close()
