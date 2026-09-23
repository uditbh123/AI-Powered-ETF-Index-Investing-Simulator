"""Tests for the market-data service (fetch normalization + persistence).

Network is never touched: fetchers are faked with in-memory DataFrames shaped
like real yfinance output (including the MultiIndex column layout).
"""
import numpy as np
import pandas as pd
import pytest

from app.dao import prices as price_dao
from app.dao import tickers as ticker_dao
from app.database import get_connection
from app.services.market_data import (
    fetch_history,
    history_to_rows,
    refresh_catalog,
    refresh_ticker,
)


def make_frame(symbol: str, rows: list[tuple[str, float, float]]) -> pd.DataFrame:
    """Build a DataFrame with yfinance's MultiIndex ('Price', 'Ticker') columns."""
    idx = pd.to_datetime([d for d, _, _ in rows], utc=True)
    cols = pd.MultiIndex.from_tuples(
        [("Close", symbol), ("Volume", symbol)], names=["Price", "Ticker"]
    )
    return pd.DataFrame([[c, v] for _, c, v in rows], index=idx, columns=cols)


def make_flat_frame(rows: list[tuple[str, float, float]]) -> pd.DataFrame:
    """Older yfinance layout: flat columns for a single ticker."""
    idx = pd.to_datetime([d for d, _, _ in rows])
    return pd.DataFrame(
        {
            "Open": [c for _, c, _ in rows],
            "Close": [c for _, c, _ in rows],
            "Volume": [v for _, _, v in rows],
        },
        index=idx,
    )


def fake_fetcher(frames: dict[str, pd.DataFrame]):
    def fetcher(symbol: str, start=None, end=None) -> pd.DataFrame:
        return frames.get(symbol, pd.DataFrame())
    return fetcher


# ---------------------------------------------------------------------------
# fetch_history defaults
# ---------------------------------------------------------------------------

def test_fetch_history_requests_full_history_when_no_bounds(monkeypatch):
    import yfinance as yf

    captured = {}

    def fake_download(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return pd.DataFrame()

    monkeypatch.setattr(yf, "download", fake_download)
    fetch_history("SPY")
    assert captured["kwargs"].get("period") == "max"
    assert "start" not in captured["kwargs"]
    assert "end" not in captured["kwargs"]


def test_fetch_history_end_without_start_never_passes_period(monkeypatch):
    """`end` must be honored even when `start` is None.

    yfinance gives `period` precedence over `end`, so combining period="max"
    with end= would silently drop the end bound. We pin start to a sentinel
    instead and pass no period.
    """
    import yfinance as yf

    captured = {}

    def fake_download(*args, **kwargs):
        captured["kwargs"] = kwargs
        return pd.DataFrame()

    monkeypatch.setattr(yf, "download", fake_download)
    fetch_history("SPY", end="2024-06-01")
    assert captured["kwargs"]["start"] == "1900-01-01"
    assert captured["kwargs"]["end"] == "2024-06-01"
    assert "period" not in captured["kwargs"]


def test_fetch_history_forwards_explicit_start(monkeypatch):
    import yfinance as yf

    captured = {}

    def fake_download(*args, **kwargs):
        captured["kwargs"] = kwargs
        return pd.DataFrame()

    monkeypatch.setattr(yf, "download", fake_download)
    fetch_history("SPY", start="2020-01-01", end="2020-06-01")
    assert captured["kwargs"]["start"] == "2020-01-01"
    assert captured["kwargs"]["end"] == "2020-06-01"
    assert "period" not in captured["kwargs"]


# ---------------------------------------------------------------------------
# history_to_rows (pure normalization)
# ---------------------------------------------------------------------------

def test_history_to_rows_multiindex_frame():
    frame = make_frame("SPY", [("2024-01-02", 100.0, 1_000_000.0), ("2024-01-03", 101.5, 1_200_000.0)])
    rows = history_to_rows(frame, "SPY")
    assert rows == [
        ("2024-01-02", 100.0, 1_000_000),
        ("2024-01-03", 101.5, 1_200_000),
    ]


def test_history_to_rows_flat_frame():
    frame = make_flat_frame([("2024-01-02", 50.0, 900_000.0)])
    assert history_to_rows(frame, "QQQ") == [("2024-01-02", 50.0, 900_000)]


def test_history_to_rows_skips_nan_close_and_null_volume():
    frame = make_frame(
        "SPY",
        [
            ("2024-01-02", 100.0, 1_000_000.0),
            ("2024-01-03", np.nan, 1_000_000.0),   # bad close -> dropped
            ("2024-01-04", 102.0, np.nan),          # missing volume -> None
        ],
    )
    rows = history_to_rows(frame, "SPY")
    assert rows == [("2024-01-02", 100.0, 1_000_000), ("2024-01-04", 102.0, None)]


def test_history_to_rows_empty_frame():
    assert history_to_rows(pd.DataFrame(), "SPY") == []


# ---------------------------------------------------------------------------
# refresh_ticker / refresh_catalog (persistence via mocked fetch)
# ---------------------------------------------------------------------------

def test_refresh_ticker_persists_and_handles_none_volume(db):
    rows = [("2024-01-02", 100.0, 1_000_000.0), ("2024-01-03", 101.0, np.nan)]
    frame = make_frame("SPY", rows)
    result = refresh_ticker("SPY", fetcher=fake_fetcher({"SPY": frame}))

    assert result["inserted"] == 2
    assert result["first"] == "2024-01-02"

    conn = get_connection()
    try:
        ticker = ticker_dao.get_ticker(conn, "SPY")
        history = price_dao.get_price_history(conn, ticker["id"])
        assert len(history) == 2
        assert history[1]["volume"] is None
        assert ticker_dao.get_ticker(conn, "SPY")["name"] == "SPDR S&P 500 ETF Trust"
    finally:
        conn.close()


def test_refresh_ticker_is_idempotent_on_re_fetch(db):
    frame = make_frame("SPY", [("2024-01-02", 100.0, 1_000_000.0)])
    fetcher = fake_fetcher({"SPY": frame})

    first = refresh_ticker("SPY", fetcher=fetcher)
    second = refresh_ticker("SPY", fetcher=fetcher)

    assert first["inserted"] == 1
    assert second["inserted"] == 0  # date already exists

    conn = get_connection()
    try:
        ticker = ticker_dao.get_ticker(conn, "SPY")
        assert price_dao.count_prices(conn, ticker_id=ticker["id"]) == 1
    finally:
        conn.close()


def test_refresh_ticker_reports_errors_without_raising(db):
    def broken(symbol, start=None, end=None):
        raise ConnectionError("rate limited")

    result = refresh_ticker("SPY", fetcher=broken)
    assert "error" in result
    assert "rate limited" in result["error"]


def test_refresh_ticker_no_data_returns_error(db):
    result = refresh_ticker("SPY", fetcher=fake_fetcher({}))
    assert "error" in result
    assert result["inserted"] == 0


def test_refresh_catalog_aggregates_results(db):
    frames = {
        "SPY": make_frame("SPY", [("2024-01-02", 100.0, 1.0)]),
        "QQQ": make_frame("QQQ", [("2024-01-02", 400.0, 1.0)]),
    }
    results = refresh_catalog(
        [
            {"symbol": "SPY", "name": "SPDR S&P 500 ETF", "sector": "US Large-Cap Equity"},
            {"symbol": "QQQ", "name": "Invesco QQQ", "sector": "Growth"},
        ],
        fetcher=fake_fetcher(frames),
    )
    assert set(results) == {"SPY", "QQQ"}
    assert results["SPY"]["inserted"] == 1
    assert results["QQQ"]["inserted"] == 1