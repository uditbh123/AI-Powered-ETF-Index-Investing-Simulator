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
    yf = pytest.importorskip("yfinance")

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
    yf = pytest.importorskip("yfinance")

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
    yf = pytest.importorskip("yfinance")

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


def test_history_to_rows_drops_infinite_close():
    frame = make_frame(
        "SPY",
        [("2024-01-02", 100.0, 1.0), ("2024-01-03", np.inf, 1.0), ("2024-01-04", -np.inf, 1.0)],
    )
    assert history_to_rows(frame, "SPY") == [("2024-01-02", 100.0, 1)]


def test_history_to_rows_all_closes_invalid_returns_empty():
    frame = make_frame("SPY", [("2024-01-02", np.nan, 1.0), ("2024-01-03", np.inf, 1.0)])
    assert history_to_rows(frame, "SPY") == []


def test_history_to_rows_tz_aware_index_keeps_local_calendar_date():
    """A tz-aware index must yield the local trading date, not the UTC one.

    Vectorizing this by going through UTC would shift early US sessions onto
    the previous day; the conversion drops the offset instead.
    """
    idx = pd.to_datetime(["2024-01-02 14:30", "2024-01-03 14:30"]).tz_localize(
        "America/New_York"
    )
    frame = pd.DataFrame({"Close": [100.0, 101.0], "Volume": [5.0, 6.0]}, index=idx)
    assert history_to_rows(frame, "SPY") == [
        ("2024-01-02", 100.0, 5),
        ("2024-01-03", 101.0, 6),
    ]


def test_history_to_rows_tz_aware_volume_realigned_across_indexes():
    """Close dates missing from Volume must still be kept, with volume None."""
    close_idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]).tz_localize("UTC")
    vol_idx = pd.to_datetime(["2024-01-02", "2024-01-04"]).tz_localize("UTC")
    frame = pd.concat(
        [
            pd.DataFrame({"Close": [100.0, 101.0, 102.0]}, index=close_idx),
            pd.DataFrame({"Volume": [7.0, 9.0]}, index=vol_idx),
        ],
        axis=1,
    )
    assert history_to_rows(frame, "SPY") == [
        ("2024-01-02", 100.0, 7),
        ("2024-01-03", 101.0, None),
        ("2024-01-04", 102.0, 9),
    ]


def test_history_to_rows_integer_volume_is_cast_to_int():
    """int64 volume must not become a float via the float() coercion path."""
    idx = pd.to_datetime(["2024-01-02"])
    frame = pd.DataFrame(
        {"Close": np.array([100.0]), "Volume": np.array([1_234_567], dtype="int64")},
        index=idx,
    )
    (date, close, volume), = history_to_rows(frame, "SPY")
    assert (date, close) == ("2024-01-02", 100.0)
    assert volume == 1_234_567
    assert isinstance(volume, int)


def test_history_to_rows_requires_a_volume_column():
    """Pins existing behavior: a frame with no Volume column raises.

    yfinance always returns Volume for ``download``, so this is not worth
    handling; the point of the test is that vectorizing the extraction did not
    quietly turn a hard error into silently-None volumes.
    """
    idx = pd.to_datetime(["2024-01-02"])
    frame = pd.DataFrame({"Close": [100.0]}, index=idx)
    with pytest.raises(KeyError):
        history_to_rows(frame, "SPY")


def test_history_to_rows_single_row_frame():
    assert history_to_rows(make_frame("SPY", [("2024-01-02", 100.0, 3.0)]), "SPY") == [
        ("2024-01-02", 100.0, 3)
    ]


def test_history_to_rows_large_frame_matches_naive_reference():
    """Guards the vectorized path against dtype/index coercion on real sizes."""
    n = 5_000
    idx = pd.date_range("2010-01-01", periods=n, freq="B", tz="America/New_York")
    rng = np.random.default_rng(0)
    close = 100.0 * np.cumprod(1 + rng.normal(0, 0.01, n))
    close[rng.choice(n, 40, replace=False)] = np.nan
    volume = rng.integers(1_000, 9_000_000, n).astype(float)
    volume[rng.choice(n, 25, replace=False)] = np.nan
    frame = pd.DataFrame({"Close": close, "Volume": volume}, index=idx)

    rows = history_to_rows(frame, "SPY")
    assert len(rows) == n - 40
    assert rows[0][0] == "2010-01-01"
    assert all(len(r) == 3 and r[1] is not None for r in rows)
    assert any(r[2] is None for r in rows)
    assert all(isinstance(r[2], int) for r in rows if r[2] is not None)


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