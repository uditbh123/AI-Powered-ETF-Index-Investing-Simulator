"""Aggregate stored FinBERT sentiment into one portfolio-level signal.

Phase 5 persists per-headline scores in ``news_sentiment``: sector rows tied to
a ticker, and geopolitical/macro rows that are market-wide (NULL ticker). Phase
6 collapses those into a single number in [-1, 1] which the Monte Carlo engine
maps to a volatility multiplier (see ``monte_carlo``).
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from datetime import date, timedelta

from ..dao import news as news_dao

DEFAULT_LOOKBACK_DAYS = 30


def _scores(rows: Iterable[sqlite3.Row]) -> list[float]:
    """Pull the non-NULL ``sentiment_score`` values out of DAO rows."""
    return [
        float(row["sentiment_score"])
        for row in rows
        if row["sentiment_score"] is not None
    ]


def portfolio_sentiment_score(
    conn: sqlite3.Connection,
    holdings: Sequence[sqlite3.Row],
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    as_of: str | None = None,
) -> float | None:
    """Weighted mean recent sentiment for a portfolio, or None if no news.

    For each holding we average its sector headlines together with every
    geopolitical/macro headline (market-wide, so it applies to each holding),
    then combine the per-holding scores by portfolio weight. Holdings with no
    scored news in the window are skipped so they cannot dilute the signal.
    Returns None when there is nothing recent to score, letting the caller fall
    back to an unadjusted simulation.

    The per-holding query loop is deliberate. Folding it into one
    ``ticker_id IN (...)`` lookup was measured and is *slower*: the planner
    then chooses ``idx_news_category_published`` over the selective
    ``idx_news_ticker_published``, so the batched form scans the whole category
    in the window instead of one ticker's slice (4.7x slower at 13 holdings on a
    44k-row table). Making the batched form fast needs a hard ``INDEXED BY`` hint
    plus a SQL-side SUM/COUNT, which shifts the score by ~1e-18 - and that score
    feeds the volatility multiplier and therefore the run cache key. A ticker's
    own rows are indexed and the window is short, so the loop is cheap here.
    """
    reference = date.fromisoformat(as_of) if as_of else date.today()
    start = (reference - timedelta(days=lookback_days)).isoformat()
    end = reference.isoformat()

    macro_scores = _scores(
        news_dao.list_sentiment(conn, category="geopolitical", start=start, end=end)
    )

    weighted_sum = 0.0
    total_weight = 0.0
    for holding in holdings:
        sector_scores = _scores(
            news_dao.list_sentiment(
                conn,
                category="sector",
                ticker_id=holding["ticker_id"],
                start=start,
                end=end,
            )
        )
        scores = sector_scores + macro_scores
        if not scores:
            continue
        weight = float(holding["weight"])
        weighted_sum += weight * (sum(scores) / len(scores))
        total_weight += weight

    if total_weight == 0.0:
        return None
    return weighted_sum / total_weight


__all__ = ["DEFAULT_LOOKBACK_DAYS", "portfolio_sentiment_score"]
