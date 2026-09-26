"""News sentiment DAO: reads/writes the news_sentiment table.

Matches the schema from ``schema.sql``:

    news_sentiment(id, ticker_id_or_null, headline, source,
                   published_at, sentiment_score, category)

Access goes through this layer so the API/scripts never touch raw SQL.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from typing import Any

CATEGORIES = ("sector", "geopolitical")


def insert_sentiment(
    conn: sqlite3.Connection,
    rows: Iterable[
        tuple[int | None, str, str | None, str | None, float | None, str]
    ],
) -> int:
    """Insert scored headlines. Skips exact duplicates (same headline + source).

    Args are ``(ticker_id_or_null, headline, source, published_at,
    sentiment_score, category)`` tuples. Duplicate headlines from the same
    source are ignored so re-running ingestion is idempotent.
    """
    inserted = 0
    for ticker_id, headline, source, published_at, score, category in rows:
        dup = conn.execute(
            "SELECT 1 FROM news_sentiment "
            "WHERE headline = ? AND source = ? AND category = ? LIMIT 1",
            (headline, source, category),
        ).fetchone()
        if dup is not None:
            continue
        conn.execute(
            "INSERT INTO news_sentiment (ticker_id_or_null, headline, source,"
            " published_at, sentiment_score, category) VALUES (?, ?, ?, ?, ?, ?)",
            (ticker_id, headline, source, published_at, score, category),
        )
        inserted += 1
    return inserted


def list_sentiment(
    conn: sqlite3.Connection,
    *,
    category: str | None = None,
    ticker_id: int | None = None,
    start: str | None = None,
    end: str | None = None,
    desc: bool = False,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    """Return sentiment rows, optional category/ticker/date filters, by date.

    ``limit`` caps the row count in SQL (not in Python) so a wide window over a
    large news table is never fully materialized just to be sliced down to the
    newest few. Combined with the date ordering it returns the newest ``limit``
    rows when ``desc`` is set.
    """
    query = "SELECT id, ticker_id_or_null, headline, source, published_at, sentiment_score, category FROM news_sentiment WHERE 1 = 1"
    params: list[Any] = []
    if category is not None:
        query += " AND category = ?"
        params.append(category)
    if ticker_id is not None:
        query += " AND ticker_id_or_null = ?"
        params.append(ticker_id)
    if start is not None:
        query += " AND published_at >= ?"
        params.append(start)
    if end is not None:
        query += " AND published_at <= ?"
        params.append(end)
    query += " ORDER BY published_at DESC, id DESC" if desc else " ORDER BY published_at, id"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    return conn.execute(query, params).fetchall()


def count_sentiment(
    conn: sqlite3.Connection,
    *,
    category: str | None = None,
    ticker_id: int | None = None,
) -> int:
    query = "SELECT COUNT(*) FROM news_sentiment WHERE 1 = 1"
    params: list[Any] = []
    if category is not None:
        query += " AND category = ?"
        params.append(category)
    if ticker_id is not None:
        query += " AND ticker_id_or_null = ?"
        params.append(ticker_id)
    return conn.execute(query, params).fetchone()[0]


__all__ = [
    "CATEGORIES",
    "insert_sentiment",
    "list_sentiment",
    "count_sentiment",
]