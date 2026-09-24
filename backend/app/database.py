"""SQLite connection management and schema initialization.

Uses a single lightweight schema.sql applied on startup when the database
file is empty (or missing). All data access in later phases must go through
a DAO/repository layer so a future Postgres migration is a config change.
"""
import sqlite3
from pathlib import Path

from .config import settings

DB_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"


def _db_path(database_url: str) -> Path:
    # Support sqlite:///absolute/path and sqlite:///./relative/path only.
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError(f"Unsupported database URL (only local SQLite): {database_url}")
    raw = database_url[len(prefix):]
    return Path(raw)


def get_connection() -> sqlite3.Connection:
    db_path = _db_path(settings.database_url)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # A connection is used on a single request thread at a time, but FastAPI's
    # threaded yield-dependency teardown may call close() on a different worker
    # thread; check_same_thread=False lets the exit path tear down safely.
    # PRAGMAs are per-connection; the ones in schema.sql do NOT persist across
    # connections, so apply them here on every new connection.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Idempotent."""
    if not DB_SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found: {DB_SCHEMA_PATH}")

    with get_connection() as conn:
        conn.executescript(DB_SCHEMA_PATH.read_text(encoding="utf-8"))
        # Forward-compatible column migration for pre-existing databases that
        # lack the newest schema columns (SQLite has no ALTER TABLE ... ADD
        # COLUMN IF NOT EXISTS).
        ensure_column(conn, "simulation_runs", "stats_json", "TEXT")
        ensure_column(conn, "portfolios", "created_at", "TEXT")
        # Legacy portfolios predate the column; stamp them with the boot date
        # rather than leaving a NULL "created" shown in the UI.
        conn.execute(
            "UPDATE portfolios SET created_at = date('now') WHERE created_at IS NULL"
        )


def ensure_column(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    declaration: str,
) -> None:
    """Add ``column`` to ``table`` if it does not already exist.

    SQLite cannot express ``ADD COLUMN IF NOT EXISTS``, so check
    ``PRAGMA table_info`` first. Safe to call repeatedly (idempotent).
    """
    existing = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def check_db_connected() -> bool:
    """Return True if the DB file exists and is readable."""
    try:
        db_path = _db_path(settings.database_url)
        if not db_path.exists():
            return False
        with get_connection() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False