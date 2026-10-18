"""Macro indicator DAO: reads/writes the macro_indicators table.

Matches the schema from ``schema.sql``:

    macro_indicators(id, country, indicator, label, value, unit,
                     period, source, fetched_at)

The table holds a *snapshot*, not a time series: the UNIQUE key is
``(country, indicator, source)`` and ``upsert_indicators`` refreshes the latest
reading in place. Access goes through this layer so the API/scripts never touch
raw SQL.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from typing import Any

# Rows per upsert batch. Seven bound parameters per row keeps a chunk well under
# SQLite's legacy 999-variable limit.
_UPSERT_CHUNK_ROWS = 140

_SELECT_COLUMNS = (
    "SELECT id, country, indicator, label, value, unit, period, source, "
    "fetched_at FROM macro_indicators"
)

_UPSERT = (
    "INSERT INTO macro_indicators "
    "(country, indicator, label, value, unit, period, source) "
    "VALUES (?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT (country, indicator, source) DO UPDATE SET "
    "label = excluded.label, value = excluded.value, unit = excluded.unit, "
    "period = excluded.period, fetched_at = CURRENT_TIMESTAMP"
)


def upsert_indicators(
    conn: sqlite3.Connection,
    rows: Iterable[
        tuple[str, str, str | None, float | None, str | None, str | None, str]
    ],
) -> int:
    """Insert or refresh indicators. Returns the number of rows written.

    Args are ``(country, indicator, label, value, unit, period, source)``
    tuples. Re-running with the same key updates the stored value and stamps a
    fresh ``fetched_at`` rather than inserting a duplicate, so ingestion is
    idempotent.
    """
    pending = [tuple(row) for row in rows]
    if not pending:
        return 0
    for start in range(0, len(pending), _UPSERT_CHUNK_ROWS):
        conn.executemany(_UPSERT, pending[start : start + _UPSERT_CHUNK_ROWS])
    return len(pending)


def list_indicators(
    conn: sqlite3.Connection,
    *,
    indicator: str | None = None,
    country: str | None = None,
    source: str | None = None,
) -> list[sqlite3.Row]:
    """Return stored indicators, optionally filtered, ordered for display."""
    query = f"{_SELECT_COLUMNS} WHERE 1 = 1"
    params: list[Any] = []
    if indicator is not None:
        query += " AND indicator = ?"
        params.append(indicator)
    if country is not None:
        query += " AND country = ?"
        params.append(country)
    if source is not None:
        query += " AND source = ?"
        params.append(source)
    query += " ORDER BY indicator, country"
    return conn.execute(query, params).fetchall()


def count_indicators(
    conn: sqlite3.Connection,
    *,
    indicator: str | None = None,
) -> int:
    query = "SELECT COUNT(*) FROM macro_indicators WHERE 1 = 1"
    params: list[Any] = []
    if indicator is not None:
        query += " AND indicator = ?"
        params.append(indicator)
    return conn.execute(query, params).fetchone()[0]


def latest_fetch_time(conn: sqlite3.Connection) -> str | None:
    """Most recent ``fetched_at`` across the table, or None when empty."""
    row = conn.execute("SELECT MAX(fetched_at) FROM macro_indicators").fetchone()
    return row[0] if row else None


__all__ = [
    "upsert_indicators",
    "list_indicators",
    "count_indicators",
    "latest_fetch_time",
]
