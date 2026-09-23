"""Price DAO: reads/writes daily OHLC-style rows in the prices table."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable


def upsert_daily_prices(
    conn: sqlite3.Connection,
    ticker_id: int,
    rows: Iterable[tuple[str, float, int | None]],
) -> int:
    """Insert daily (date, close, volume) rows, rewriting any that exist.

    Relies on the UNIQUE(ticker_id, date) constraint. A conflict does NOT
    silently skip the existing row: adjusted closes are re-scaled by Yahoo at
    every dividend/split (``auto_adjust=True``), so a re-fetch must overwrite
    the stored value with the current adjustment basis or the series mixes
    bases. Returns the number of rows that were genuinely NEW dates (existing
    rows rewritten on conflict are not counted).
    """
    rows = list(rows)
    existing = {
        row["date"]
        for row in conn.execute(
            "SELECT date FROM prices WHERE ticker_id = ?", (ticker_id,)
        )
    }
    inserted = sum(1 for date, _, _ in rows if date not in existing)
    conn.executemany(
        """
        INSERT INTO prices (ticker_id, date, close, volume)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(ticker_id, date) DO UPDATE SET
            close = excluded.close,
            volume = excluded.volume
        """,
        [(ticker_id, date, close, volume) for date, close, volume in rows],
    )
    return inserted


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