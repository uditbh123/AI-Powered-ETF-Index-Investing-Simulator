"""Tests for the in-depth ETF analysis endpoint + service."""
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.dao import prices as price_dao
from app.dao import tickers as ticker_dao
from app.database import init_db
from app.main import app
from app.services import analysis

YEAR = analysis.TRADING_DAYS_PER_YEAR


def _dates(n, start="2024-01-02"):
    from pandas import bdate_range

    return [d.strftime("%Y-%m-%d") for d in bdate_range(start, periods=n)]


# ---------------------------------------------------------------------------
# Unit: empty / thin series
# ---------------------------------------------------------------------------

def test_no_history_returns_empty_payload():
    payload = analysis.compute_analysis("SPY", "SPY fund", "Equity", [], [])
    assert payload["stats"] is None
    assert payload["trailing_returns"] == []
    assert payload["monthly_returns"] == []
    assert payload["returns_histogram"] == []
    assert payload["drawdown_series"] == []
    assert payload["correlation"] is None


def test_single_point_returns_empty_payload():
    payload = analysis.compute_analysis("SPY", None, None, _dates(1), [100.0])
    assert payload["stats"] is None


# ---------------------------------------------------------------------------
# Unit: key stats on a known series
# ---------------------------------------------------------------------------

def test_stats_include_latest_and_daily_change():
    closes = [100.0, 101.0]
    payload = analysis.compute_analysis("SPY", None, None, _dates(2), closes)
    stats = payload["stats"]
    assert stats["latest_close"] == 101.0
    assert stats["prev_close"] == 100.0
    assert stats["one_day_change_pct"] == pytest.approx(1.0)
    assert stats["price_rows"] == 2


def test_full_max_drawdown_detects_peak_to_trough():
    closes = [100.0, 110.0, 80.0, 90.0, 95.0]
    payload = analysis.compute_analysis("SPY", None, None, _dates(5), closes)
    stats = payload["stats"]
    assert stats["full_max_drawdown_pct"] == pytest.approx(-27.2727, abs=1e-3)


def test_sharpe_is_none_for_very_short_history():
    payload = analysis.compute_analysis("SPY", None, None, _dates(10), [100.0] * 10)
    assert payload["stats"]["sharpe_annualized"] is None


def test_sharpe_none_for_flat_series():
    # Zero dispersion makes the ratio 0/0: undefined, reported as None.
    closes = [100.0] * (YEAR + 1)
    payload = analysis.compute_analysis("SPY", None, None, _dates(len(closes)), closes)
    assert payload["stats"]["sharpe_annualized"] is None


def test_best_worst_month_brackets_the_moves():
    # Build a year of daily closes with one strong up month and one down month.
    rng = np.random.default_rng(7)
    log_moves = rng.normal(0.0004, 0.01, YEAR + 1)
    closes = 100.0 * np.exp(np.cumsum(log_moves))
    payload = analysis.compute_analysis(
        "SPY", None, None, _dates(len(closes)), closes.tolist()
    )
    stats = payload["stats"]
    assert stats["best_month_pct"] is not None
    assert stats["worst_month_pct"] is not None
    assert stats["best_month_pct"] >= stats["worst_month_pct"]


# ---------------------------------------------------------------------------
# Unit: trailing returns
# ---------------------------------------------------------------------------

def test_trailing_returns_have_all_labels():
    closes = [100.0 * (1.001**i) for i in range(YEAR + 1)]
    payload = analysis.compute_analysis("SPY", None, None, _dates(len(closes)), closes)
    labels = [t["label"] for t in payload["trailing_returns"]]
    assert labels == ["1M", "3M", "6M", "1Y", "3Y", "5Y", "Max"]


def test_trailing_annualized_none_under_one_year():
    closes = [100.0, 101.0, 102.0]
    payload = analysis.compute_analysis("SPY", None, None, _dates(3), closes)
    one_m = next(t for t in payload["trailing_returns"] if t["label"] == "1M")
    # Only ~1 month of data exists; annualized is undefined below a year.
    assert one_m["annualized"] is None or one_m["months"] >= 12


# ---------------------------------------------------------------------------
# Unit: histogram, monthly grid, drawdown
# ---------------------------------------------------------------------------

def test_histogram_counts_sum_to_returns():
    closes = [100.0 * (1.001**i) for i in range(YEAR + 1)]
    payload = analysis.compute_analysis("SPY", None, None, _dates(len(closes)), closes)
    hist = payload["returns_histogram"]
    assert hist  # non-empty for a full year
    total = sum(b["count"] for b in hist)
    # The trailing-year window holds YEAR closes, hence YEAR - 1 daily log
    # returns, and every one lands in exactly one bin.
    assert total == YEAR - 1


def test_monthly_returns_are_year_month_shaped():
    closes = [100.0 * (1.005**i) for i in range(YEAR + 1)]
    payload = analysis.compute_analysis("SPY", None, None, _dates(len(closes)), closes)
    grid = payload["monthly_returns"]
    assert grid
    for cell in grid:
        assert 1 <= cell["month"] <= 12
        assert isinstance(cell["year"], int)


def test_drawdown_series_never_positive():
    closes = [100.0, 110.0, 80.0, 90.0, 95.0] * 6
    payload = analysis.compute_analysis(
        "SPY", None, None, _dates(len(closes)), closes
    )
    dd = payload["drawdown_series"]
    assert dd
    assert all(p["drawdown_pct"] <= 1e-9 for p in dd)


# ---------------------------------------------------------------------------
# Unit: correlation matrix
# ---------------------------------------------------------------------------

def test_correlation_identical_series_is_one():
    closes = [100.0 * (1.002**i) for i in range(YEAR + 1)]
    dates = _dates(len(closes))
    import pandas as pd

    subject = pd.Series(closes, index=pd.to_datetime(dates))
    all_series = {"SPY": subject, "VOO": subject.copy()}
    payload = analysis.compute_analysis(
        "SPY", None, None, dates, closes, all_ticker_series=all_series
    )
    corr = payload["correlation"]
    assert corr is not None
    assert corr["symbols"] == ["SPY", "VOO"]
    # SPY (subject) first; identical series correlate to 1.0.
    assert corr["matrix"][0][1] == pytest.approx(1.0)
    assert corr["matrix"][0][0] == pytest.approx(1.0)


def test_correlation_inverse_series_is_negative_one():
    dates = _dates(YEAR + 1)
    up = [100.0 * (1.002**i) for i in range(YEAR + 1)]
    down = [100.0 * (0.998**i) for i in range(YEAR + 1)]
    import pandas as pd

    all_series = {
        "SPY": pd.Series(up, index=pd.to_datetime(dates)),
        "TLT": pd.Series(down, index=pd.to_datetime(dates)),
    }
    payload = analysis.compute_analysis(
        "SPY", None, None, dates, up, all_ticker_series=all_series
    )
    corr = payload["correlation"]
    assert corr["matrix"][0][1] == pytest.approx(-1.0, abs=1e-6)


def test_correlation_none_without_history():
    payload = analysis.compute_analysis("SPY", None, None, _dates(3), [100, 101, 102])
    assert payload["correlation"] is None


# ---------------------------------------------------------------------------
# API wiring
# ---------------------------------------------------------------------------

def _seed(conn_url: str) -> None:
    import sqlite3

    conn = sqlite3.connect(conn_url[10:])
    conn.row_factory = sqlite3.Row
    spy = ticker_dao.get_or_create_ticker(conn, "SPY", "SPDR S&P 500 ETF", "Equity")
    tlt = ticker_dao.get_or_create_ticker(conn, "TLT", "iShares Treasury", "Bonds")
    # GHOST exists as a catalog ticker but gets no price rows.
    ticker_dao.get_or_create_ticker(conn, "GHOST", "No History", "Equity")

    dates = _dates(YEAR + 1)
    up = [100.0 * (1.002**i) for i in range(YEAR + 1)]
    down = [100.0 * (0.998**i) for i in range(YEAR + 1)]
    price_dao.upsert_daily_prices(
        conn, spy["id"], [(d, round(c, 4), 1_000_000) for d, c in zip(dates, up)]
    )
    price_dao.upsert_daily_prices(
        conn, tlt["id"], [(d, round(c, 4), 1_000_000) for d, c in zip(dates, down)]
    )
    conn.commit()
    conn.close()


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "analysis.db"
    original_url = settings.database_url
    original_sched = settings.enable_scheduler
    settings.database_url = f"sqlite:///{db_path.as_posix()}"
    settings.enable_scheduler = False
    init_db()
    _seed(settings.database_url)
    with TestClient(app) as c:
        yield c
    settings.enable_scheduler = original_sched
    settings.database_url = original_url


def test_analysis_endpoint_returns_full_payload(client):
    response = client.get("/tickers/SPY/analysis")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "SPY"
    assert body["stats"] is not None
    assert body["stats"]["latest_close"] > 0
    assert [t["label"] for t in body["trailing_returns"]][:4] == [
        "1M",
        "3M",
        "6M",
        "1Y",
    ]
    assert body["monthly_returns"]
    assert body["returns_histogram"]
    assert body["drawdown_series"]
    assert body["correlation"] is not None
    assert "SPY" in body["correlation"]["symbols"]
    assert "TLT" in body["correlation"]["symbols"]


def test_analysis_endpoint_404_for_unknown_symbol(client):
    response = client.get("/tickers/NOPE/analysis")
    assert response.status_code == 404


def test_analysis_endpoint_empty_payload_for_history_less_ticker(client):
    response = client.get("/tickers/GHOST/analysis")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "GHOST"
    assert body["stats"] is None


def test_analysis_symbol_is_case_insensitive(client):
    assert client.get("/tickers/spy/analysis").status_code == 200
