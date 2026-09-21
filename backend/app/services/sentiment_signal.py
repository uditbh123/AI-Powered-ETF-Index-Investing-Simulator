"""Aggregate stored FinBERT sentiment into one portfolio-level signal.

Phase 5 persists per-headline scores in ``news_sentiment``: sector rows tied to
a ticker, and geopolitical/macro rows that are market-wide (NULL ticker). Phase
6 collapses those into a single number in [-1, 1] which the Monte Carlo engine
maps to a volatility multiplier (see ``monte_carlo``).
"""
from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import date, timedelta

from ..dao import news as news_dao

DEFAULT_LOOKBACK_DAYS = 30


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
    """
    reference = date.fromisoformat(as_of) if as_of else date.today()
    start = (reference - timedelta(days=lookback_days)).isoformat()
    end = reference.isoformat()

    macro_scores = [
        float(row["sentiment_score"])
        for row in news_dao.list_sentiment(
            conn, category="geopolitical", start=start, end=end
        )
        if row["sentiment_score"] is not None
    ]

    weighted_sum = 0.0
    total_weight = 0.0
    for holding in holdings:
        sector_scores = [
            float(row["sentiment_score"])
            for row in news_dao.list_sentiment(
                conn,
                category="sector",
                ticker_id=holding["ticker_id"],
                start=start,
                end=end,
            )
            if row["sentiment_score"] is not None
        ]
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
