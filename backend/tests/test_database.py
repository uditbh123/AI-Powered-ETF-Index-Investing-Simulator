"""Connection-factory tests: per-connection PRAGMAs are applied every time."""
from app.database import get_connection


def test_connection_factory_enforces_foreign_keys():
    conn = get_connection()
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_connection_factory_uses_wal_and_busy_timeout():
    conn = get_connection()
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        conn.close()