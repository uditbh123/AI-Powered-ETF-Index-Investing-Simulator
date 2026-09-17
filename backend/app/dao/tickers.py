"""Ticker DAO: reads/writes the tickers table.

All SQLite access lives in this layer so route handlers never touch raw SQL
and a future Postgres migration is a config change, not a rewrite.
"""
from __future__ import annotations

import sqlite3

from ..data.ticker_catalog import TickerInfo


def get_ticker(conn: sqlite3.Connection, symbol: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, symbol, name, sector FROM tickers WHERE symbol = ?", (symbol,)
    ).fetchone()


def create_ticker(
    conn: sqlite3.Connection,
    symbol: str,
    name: str | None = None,
    sector: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO tickers (symbol, name, sector) VALUES (?, ?, ?)",
        (symbol, name, sector),
    )
    return cur.lastrowid


def get_or_create_ticker(
    conn: sqlite3.Connection,
    symbol: str,
    name: str | None = None,
    sector: str | None = None,
) -> sqlite3.Row:
    existing = get_ticker(conn, symbol)
    if existing is not None:
        return existing
    ticker_id = create_ticker(conn, symbol, name, sector)
    row = conn.execute("SELECT * FROM tickers WHERE id = ?", (ticker_id,)).fetchone()
    assert row is not None
    return row


def list_tickers(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, symbol, name, sector FROM tickers ORDER BY symbol"
    ).fetchall()


def upsert_catalog(conn: sqlite3.Connection, catalog: list[TickerInfo]) -> dict[str, int]:
    """Ensure every catalog entry exists. Idempotent. Returns {created, existing}."""
    created = 0
    existing = 0
    for item in catalog:
        current = get_ticker(conn, item["symbol"])
        if current is None:
            create_ticker(conn, item["symbol"], item["name"], item["sector"])
            created += 1
        else:
            existing += 1
    return {"created": created, "existing": existing}


__all__ = [
    "get_ticker",
    "create_ticker",
    "get_or_create_ticker",
    "list_tickers",
    "upsert_catalog",
]