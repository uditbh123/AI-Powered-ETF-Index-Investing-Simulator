"""Tests for aggregating stored sentiment into a portfolio-level signal."""
import pytest

from app.dao import news as news_dao
from app.dao import tickers as ticker_dao
from app.services.sentiment_signal import portfolio_sentiment_score

AS_OF = "2026-06-30"


def _holding(db, symbol: str, weight: float) -> dict:
    ticker = ticker_dao.get_or_create_ticker(db, symbol)
    return {"ticker_id": ticker["id"], "weight": weight, "symbol": symbol}


def test_sector_and_geopolitical_headlines_combine(db):
    spy = _holding(db, "SPY", 1.0)
    news_dao.insert_sentiment(
        db,
        [
            (spy["ticker_id"], "SPY rallies", "src", "2026-06-29", 0.8, "sector"),
            (None, "Macro jitters", "src", "2026-06-29", -0.6, "geopolitical"),
        ],
    )
    score = portfolio_sentiment_score(db, [spy], as_of=AS_OF)
    assert score == pytest.approx((0.8 - 0.6) / 2)


def test_no_news_returns_none(db):
    spy = _holding(db, "SPY", 1.0)
    assert portfolio_sentiment_score(db, [spy], as_of=AS_OF) is None


def test_news_outside_lookback_is_ignored(db):
    spy = _holding(db, "SPY", 1.0)
    news_dao.insert_sentiment(
        db,
        [(spy["ticker_id"], "Stale headline", "src", "2026-01-01", -0.9, "sector")],
    )
    assert portfolio_sentiment_score(db, [spy], as_of=AS_OF, lookback_days=30) is None


def test_holdings_are_combined_by_weight(db):
    spy = _holding(db, "SPY", 3.0)
    qqq = _holding(db, "QQQ", 1.0)
    news_dao.insert_sentiment(
        db,
        [
            (spy["ticker_id"], "SPY good", "src", "2026-06-29", 1.0, "sector"),
            (qqq["ticker_id"], "QQQ bad", "src", "2026-06-29", -1.0, "sector"),
        ],
    )
    score = portfolio_sentiment_score(db, [spy, qqq], as_of=AS_OF)
    assert score == pytest.approx((3.0 * 1.0 + 1.0 * -1.0) / 4.0)


def test_holding_without_news_does_not_dilute_signal(db):
    spy = _holding(db, "SPY", 1.0)
    qqq = _holding(db, "QQQ", 1.0)
    news_dao.insert_sentiment(
        db,
        [(spy["ticker_id"], "SPY bad", "src", "2026-06-29", -0.5, "sector")],
    )
    # QQQ has no headlines, so the portfolio score is just SPY's.
    assert portfolio_sentiment_score(db, [spy, qqq], as_of=AS_OF) == pytest.approx(-0.5)
