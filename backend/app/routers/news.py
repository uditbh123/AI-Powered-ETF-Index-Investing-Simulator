"""News sentiment feed endpoint (Phase 7)."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query

from ..dao import news as news_dao
from ..deps import get_db
from ..schemas import HeadlineOut, NewsFeedOut

router = APIRouter(tags=["news"])

MAX_HEADLINES = 100


@router.get("/news", response_model=NewsFeedOut)
def get_news_feed(
    category: Literal["sector", "geopolitical"],
    ticker_id: int | None = None,
    days: int = Query(default=30),
    conn: sqlite3.Connection = Depends(get_db),
) -> NewsFeedOut:
    """Most recent scored headlines for a category, newest first.

    ``days`` is clamped to 1..90. ``ticker_id`` narrows sector headlines to a
    single ticker and is ignored for the geopolitical feed. The aggregate score
    is the mean of non-null sentiment scores in the returned window (null when
    there are no scored headlines). Headlines are hard-capped at 100 rows, and
    the cap is pushed into SQL (``list_sentiment(limit=...)``) so a wide window
    over a large news table is never fully loaded and then sliced.
    """
    days = max(1, min(days, 90))
    start = (date.today() - timedelta(days=days)).isoformat()

    # ticker_id only applies to sector rows; geopolitical news is macro-level.
    if category == "sector" and ticker_id is not None:
        rows = news_dao.list_sentiment(
            conn,
            category=category,
            ticker_id=ticker_id,
            start=start,
            desc=True,
            limit=MAX_HEADLINES,
        )
    else:
        rows = news_dao.list_sentiment(
            conn, category=category, start=start, desc=True, limit=MAX_HEADLINES
        )

    headlines = rows
    scores = [r["sentiment_score"] for r in headlines if r["sentiment_score"] is not None]
    return NewsFeedOut(
        category=category,
        days=days,
        n_headlines=len(headlines),
        aggregate_score=round(sum(scores) / len(scores), 6) if scores else None,
        headlines=[
            HeadlineOut(
                published_at=r["published_at"],
                source=r["source"],
                headline=r["headline"],
                sentiment_score=r["sentiment_score"],
            )
            for r in headlines
        ],
    )