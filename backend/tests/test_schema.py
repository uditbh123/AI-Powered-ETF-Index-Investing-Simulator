"""Schema integrity tests: schema.sql must execute cleanly and create indexes."""
import sqlite3

from app.database import DB_SCHEMA_PATH


def _exec_schema(db_path: str) -> sqlite3.Connection:
    """Run schema.sql via executescript() on a fresh DB and return the connection."""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(DB_SCHEMA_PATH.read_text(encoding="utf-8"))
        return conn
    except Exception:
        conn.close()
        raise


def _index_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
    }


def test_schema_executes_without_error(tmp_path):
    conn = _exec_schema(str(tmp_path / "schema.db"))
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert "news_sentiment" in tables
    finally:
        conn.close()


def test_news_ticker_published_index_exists(tmp_path):
    conn = _exec_schema(str(tmp_path / "schema.db"))
    try:
        assert "idx_news_ticker_published" in _index_names(conn)
    finally:
        conn.close()


def test_news_category_published_index_exists(tmp_path):
    conn = _exec_schema(str(tmp_path / "schema.db"))
    try:
        assert "idx_news_category_published" in _index_names(conn)
    finally:
        conn.close()