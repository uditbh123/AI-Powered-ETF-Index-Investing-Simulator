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
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Idempotent."""
    if not DB_SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found: {DB_SCHEMA_PATH}")

    with get_connection() as conn:
        conn.executescript(DB_SCHEMA_PATH.read_text(encoding="utf-8"))


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