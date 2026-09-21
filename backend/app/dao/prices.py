"""Price DAO: reads/writes daily OHLC-style rows in the prices table."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable


def upsert_daily_prices(
    conn: sqlite3.Connection,
    ticker_id: int,
    rows: Iterable[tuple[str, float, int | None]],
) -> int:
    """Insert daily (date, close, volume) rows, skipping existing dates.

    Relies on the UNIQUE(ticker_id, date) constraint, so a daily re-pull only
    ever adds new trading days. Returns the number of rows actually inserted.
    """
    cur = conn.executemany(
        """
        INSERT OR IGNORE INTO prices (ticker_id, date, close, volume)
        VALUES (?, ?, ?, ?)
        """,
        [(ticker_id, date, close, volume) for date, close, volume in rows],
    )
    return cur.rowcount


def get_price_history(
    conn: sqlite3.Connection,
    ticker_id: int,
    start: str | None = None,
    end: str | None = None,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    """Return (date, close, volume) rows ordered by date, optionally filtered.

    When ``limit`` is set, the most recent ``limit`` rows are returned, still in
    ascending date order (useful for sparklines and latest-price lookups).
    """
    query = (
        "SELECT date, close, volume FROM prices "
        "WHERE ticker_id = ?"
    )
    params: list = [ticker_id]
    if start is not None:
        query += " AND date >= ?"
        params.append(start)
    if end is not None:
        query += " AND date <= ?"
        params.append(end)
    if limit is not None:
        query += " ORDER BY date DESC LIMIT ?"
        params.append(limit)
        return list(reversed(conn.execute(query, params).fetchall()))
    query += " ORDER BY date"
    return conn.execute(query, params).fetchall()


def count_prices(conn: sqlite3.Connection, ticker_id: int | None = None) -> int:
    if ticker_id is None:
        return conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    return conn.execute(
        "SELECT COUNT(*) FROM prices WHERE ticker_id = ?", (ticker_id,)
    ).fetchone()[0]


__all__ = ["upsert_daily_prices", "get_price_history", "count_prices"]