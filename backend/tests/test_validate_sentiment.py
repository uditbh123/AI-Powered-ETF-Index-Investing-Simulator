"""Tests for the sentiment↔volatility validation math (synthetic data).

We build a price series with a clear volatility regime, then construct
sentiment that is (by construction) strongly negatively correlated with
forward realized volatility. The validator must recover that signal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

scipy = pytest.importorskip("scipy")  # ingest-only dep, absent in the runtime venv

from app.dao import news as news_dao
from app.dao import prices as price_dao
from app.dao import tickers as ticker_dao
from app.scripts.validate_sentiment import (
    analyze_ticker,
    daily_returns,
    forward_vol,
    realized_vol,
    render_report,
    correlate,
)


def _synthetic_closes(n_days: int = 800, seed: int = 7) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2022-01-03", periods=n_days)
    # volatility regime: high for the first third, low after
    sigma = np.where(np.arange(n_days) < n_days / 3, 0.02, 0.005)
    drift = 0.0003
    rets = rng.normal(drift, sigma)
    closes = 100 * np.exp(np.cumsum(rets))
    return pd.Series(closes, index=idx)


def test_daily_returns_and_vol():
    closes = _synthetic_closes(400)
    df = pd.DataFrame({"close": closes})
    df["ret"] = df["close"].pct_change(fill_method=None)
    ret_series = df["ret"].dropna()

    trailing = realized_vol(ret_series).dropna()
    fwd = forward_vol(ret_series).dropna()
    assert len(trailing) > 300
    assert len(fwd) > 300
    # high-vol regime (daily 2%) should roughly hit ~30% annualized
    assert 0.2 < trailing.iloc[0] < 0.45


def test_analyze_ticker_finds_strong_inverse_correlation(db):
    ticker = ticker_dao.get_or_create_ticker(db, "SPY", "SPDR S&P 500 ETF", "Equity")

    closes = _synthetic_closes()
    rets = closes.pct_change(fill_method=None).dropna()
    fwd = forward_vol(rets)
    rows = [
        (d.strftime("%Y-%m-%d"), float(c), int(1_000_000))
        for d, c in closes.items()
    ]
    price_dao.upsert_daily_prices(db, ticker["id"], rows)

    # sentiment mirrors forward vol negatively, scaled into [-1, 1]
    scoring_days = [(d.strftime("%Y-%m-%d"), float(-2.0 * v))
                    for d, v in fwd.items() if not np.isnan(v)]
    news_dao.insert_sentiment(
        db,
        [(ticker["id"], f"Headline {i}", "Google News", date, score, "sector")
         for i, (date, score) in enumerate(scoring_days)],
    )

    result = analyze_ticker(db, "SPY", ticker_id=ticker["id"])
    assert "error" not in result
    assert result["n"] >= 300
    assert result["pearson_forward"] < -0.90
    assert result["spearman_forward"] < -0.90


def test_analyze_ticker_reports_missing_data_gracefully(db):
    ticker = ticker_dao.get_or_create_ticker(db, "QQQ")
    result = analyze_ticker(db, "QQQ", ticker_id=ticker["id"])
    assert result.get("error") == "no price data"


def test_correlate_nan_guard(db):
    empty = correlate(pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float))
    assert empty["n"] == 0
    assert np.isnan(empty["pearson_forward"])


def test_render_report_formats_table():
    rows = [
        {"symbol": "SPY", "category": "sector", "n": 100,
         "pearson_forward": -0.42, "p_forward": 0.001,
         "pearson_trailing": 0.31, "p_trailing": 0.05},
        {"symbol": "QQQ", "category": "sector", "error": "no sentiment data"},
    ]
    report = render_report(rows)
    assert "SPY" in report and "-0.420" in report and "+0.310" in report
    assert "no sentiment data" in report