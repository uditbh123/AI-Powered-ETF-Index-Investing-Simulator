"""News sentiment DAO: reads/writes the news_sentiment table.

Matches the schema from ``schema.sql``:

    news_sentiment(id, ticker_id_or_null, headline, source,
                   published_at, sentiment_score, category)

Access goes through this layer so the API/scripts never touch raw SQL.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from typing import Any

CATEGORIES = ("sector", "geopolitical")

_SELECT_COLUMNS = (
    "SELECT id, ticker_id_or_null, headline, source, published_at, "
    "sentiment_score, category FROM news_sentiment"
)

_INSERT_SENTIMENT = (
    "INSERT INTO news_sentiment (ticker_id_or_null, headline, source,"
    " published_at, sentiment_score, category) VALUES (?, ?, ?, ?, ?, ?)"
)

# Rows per dedupe lookup. Three bound parameters per row keeps a chunk well
# under SQLite's 999-variable default on older builds.
_DEDUPE_CHUNK_ROWS = 300


def _existing_keys(
    conn: sqlite3.Connection,
    keys: Sequence[tuple[str, str, str]],
) -> set[tuple[str, str, str]]:
    """Return which of ``keys`` are already stored, in as few queries as possible.

    One row-value ``IN (VALUES ...)`` lookup per chunk replaces the ``SELECT 1``
    this used to issue once per row.

    A key whose ``source`` is NULL never matches: SQL ``NULL = NULL`` is
    unknown, and a row-value comparison inherits that, so NULL-source
    headlines are *not* treated as duplicates of each other. That is the
    behavior the per-row ``SELECT`` had, and it is preserved deliberately.
    """
    found: set[tuple[str, str, str]] = set()
    for start in range(0, len(keys), _DEDUPE_CHUNK_ROWS):
        chunk = keys[start : start + _DEDUPE_CHUNK_ROWS]
        placeholders = ", ".join(["(?, ?, ?)"] * len(chunk))
        params = [part for key in chunk for part in key]
        rows = conn.execute(
            "SELECT headline, source, category FROM news_sentiment "
            f"WHERE (headline, source, category) IN (VALUES {placeholders})",
            params,
        )
        found.update((r["headline"], r["source"], r["category"]) for r in rows)
    return found


def insert_sentiment(
    conn: sqlite3.Connection,
    rows: Iterable[
        tuple[int | None, str, str | None, str | None, float | None, str]
    ],
) -> int:
    """Insert scored headlines. Skips exact duplicates (same headline + source).

    Args are ``(ticker_id_or_null, headline, source, published_at,
    sentiment_score, category)`` tuples. Duplicate headlines from the same
    source are ignored so re-running ingestion is idempotent; within a single
    call the first occurrence of a duplicate wins.

    Duplicates are resolved in two bulk steps rather than one query per row: an
    in-memory ``seen`` set collapses repeats inside the batch, then one chunked
    lookup finds what the table already holds. The remaining rows go in through
    a single ``executemany``. Rows with a NULL ``source`` are always inserted,
    because ``NULL`` never compares equal to ``NULL`` in the dedupe predicate.
    """
    pending: list[tuple] = []
    seen: set[tuple[str, str, str]] = set()
    for ticker_id, headline, source, published_at, score, category in rows:
        if source is not None:
            key = (headline, source, category)
            if key in seen:
                continue
            seen.add(key)
        pending.append((ticker_id, headline, source, published_at, score, category))

    if not pending:
        return 0

    keys = [
        (headline, source, category)
        for _, headline, source, _, _, category in pending
        if source is not None
    ]
    existing = _existing_keys(conn, keys) if keys else set()
    fresh = [
        row
        for row in pending
        if row[2] is None or (row[1], row[2], row[5]) not in existing
    ]
    if not fresh:
        return 0

    conn.executemany(_INSERT_SENTIMENT, fresh)
    return len(fresh)


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
    query = f"{_SELECT_COLUMNS} WHERE 1 = 1"
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