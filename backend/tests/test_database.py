"""Connection-factory tests: per-connection PRAGMAs are applied every time."""
import sqlite3

import pytest

from app.config import settings
from app.database import ensure_column, get_connection, init_db


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


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_ensure_column_adds_missing_column_and_is_idempotent(tmp_path):
    db_path = tmp_path / "migrate.db"
    original_url = settings.database_url
    settings.database_url = f"sqlite:///{db_path.as_posix()}"
    try:
        conn = sqlite3.connect(settings.database_url[len("sqlite:///"):])
        conn.execute(
            "CREATE TABLE simulation_runs ("
            "id INTEGER PRIMARY KEY, portfolio_id INTEGER NOT NULL, "
            "params_json TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        conn.commit()
        conn.close()

        conn = get_connection()
        assert "stats_json" not in _columns(conn, "simulation_runs")
        ensure_column(conn, "simulation_runs", "stats_json", "TEXT")
        conn.commit()
        assert "stats_json" in _columns(conn, "simulation_runs")
        # Second call must be a no-op, not an error.
        ensure_column(conn, "simulation_runs", "stats_json", "TEXT")
        conn.commit()
        assert "stats_json" in _columns(conn, "simulation_runs")
        conn.close()
    finally:
        settings.database_url = original_url


def test_init_db_migrates_preexisting_table_without_stats_column(tmp_path):
    db_path = tmp_path / "existing.db"
    original_url = settings.database_url
    settings.database_url = f"sqlite:///{db_path.as_posix()}"
    try:
        conn = sqlite3.connect(settings.database_url[len("sqlite:///"):])
        conn.execute(
            "CREATE TABLE simulation_runs ("
            "id INTEGER PRIMARY KEY, portfolio_id INTEGER NOT NULL, "
            "params_json TEXT NOT NULL, created_at TEXT NOT NULL)"
        )
        conn.commit()
        conn.close()

        init_db()

        conn = get_connection()
        cols = _columns(conn, "simulation_runs")
        assert "id" in cols
        assert "stats_json" in cols
        conn.close()
    finally:
        settings.database_url = original_url