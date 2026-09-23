"""Tests for the ETF screener: unit stats + API wiring."""
import math

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.dao import prices as price_dao
from app.dao import tickers as ticker_dao
from app.database import init_db
from app.main import app
from app.services import screener

YEAR = screener.TRADING_DAYS_PER_YEAR


def _stats(dates, closes):
    return screener.compute_screener_stats(dates, closes)


def _dates(n, start="2020-01-02"):
    from pandas import bdate_range  # trading days for a natural-looking series

    return [d.strftime("%Y-%m-%d") for d in bdate_range(start, periods=n)]


def _flat_closes(n, value=100.0):
    return [value] * n


# ---------------------------------------------------------------------------
# Unit: one-year total return
# ---------------------------------------------------------------------------

def test_one_year_return_blank_under_one_year_of_history():
    stats = _stats(_dates(YEAR), _flat_closes(YEAR))  # 252 pts, one short of a year
    assert stats["one_year_total_return_pct"] is None


def test_one_year_return_plus_ten_percent_then_flat():
    closes = [100.0, 110.0] + _flat_closes(YEAR - 1, 110.0)  # 253 pts, +10% in first step
    stats = _stats(_dates(len(closes)), closes)
    assert stats["one_year_total_return_pct"] == pytest.approx(10.0)
    assert stats["latest_close"] == 110.0


# ---------------------------------------------------------------------------
# Unit: daily change
# ---------------------------------------------------------------------------

def test_one_day_change_uses_last_two_closes():
    stats = _stats(_dates(2), [100.0, 101.5])
    assert stats["prev_close"] == 100.0
    assert stats["one_day_change_pct"] == pytest.approx(1.5)


def test_one_day_change_null_when_single_point():
    stats = _stats(_dates(1), [100.0])
    assert stats["prev_close"] is None
    assert stats["one_day_change_pct"] is None


# ---------------------------------------------------------------------------
# Unit: volatility
# ---------------------------------------------------------------------------

def test_volatility_null_with_fewer_than_30_points():
    stats = _stats(_dates(29), _flat_closes(29))
    assert stats["annualized_volatility_pct"] is None


def test_volatility_of_alternating_one_percent_moves():
    closes = [100.0 if i % 2 == 0 else 101.0 for i in range(300)]
    stats = _stats(_dates(len(closes)), closes)
    expected = math.log(1.01) * math.sqrt(YEAR) * 100
    assert stats["annualized_volatility_pct"] == pytest.approx(expected, rel=0.05)


def test_volatility_zero_for_flat_series():
    stats = _stats(_dates(300), _flat_closes(300))
    assert stats["annualized_volatility_pct"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Unit: max drawdown
# ---------------------------------------------------------------------------

def test_max_drawdown_detects_peak_to_trough():
    stats = _stats(_dates(5), [100.0, 110.0, 80.0, 90.0, 95.0])
    assert stats["max_drawdown_pct"] == pytest.approx(-27.2727, abs=1e-3)


def test_max_drawdown_zero_when_never_declines():
    stats = _stats(_dates(300), [100.0 * (1.001**i) for i in range(300)])
    assert stats["max_drawdown_pct"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# API wiring
# ---------------------------------------------------------------------------

def _seed_market_data(db_url: str) -> None:
    import sqlite3

    conn = sqlite3.connect(db_url[10:])
    conn.row_factory = sqlite3.Row
    ticker = ticker_dao.get_or_create_ticker(conn, "SPY", "SPDR S&P 500 ETF", "Equity")
    # 36 month-end rows, climbing ~0.5%/mo
    import pandas as pd

    rows = []
    for i, d in enumerate(pd.date_range("2021-01-31", periods=36, freq="ME")):
        rows.append((d.strftime("%Y-%m-%d"), round(100.0 * (1.005**i), 4), 1_000_000))
    price_dao.upsert_daily_prices(conn, ticker["id"], rows)
    conn.commit()
    conn.close()


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "screener.db"
    original_url = settings.database_url
    original_sched = settings.enable_scheduler
    settings.database_url = f"sqlite:///{db_path.as_posix()}"
    settings.enable_scheduler = False
    init_db()
    _seed_market_data(settings.database_url)
    with TestClient(app) as c:
        yield c
    settings.enable_scheduler = original_sched
    settings.database_url = original_url


def test_screener_returns_stored_tickers_only(client):
    response = client.get("/screener")
    assert response.status_code == 200
    rows = response.json()
    symbols = {r["symbol"] for r in rows}
    assert "SPY" in symbols
    assert "GLD" not in symbols  # catalog ticker present but with no price rows


def test_screener_row_shape_and_values(client):
    rows = client.get("/screener").json()
    spy = next(r for r in rows if r["symbol"] == "SPY")
    assert set(spy) == {
        "symbol",
        "name",
        "sector",
        "latest_close",
        "prev_close",
        "one_day_change_pct",
        "one_year_total_return_pct",
        "annualized_volatility_pct",
        "max_drawdown_pct",
    }
    assert spy["latest_close"] > 100.0
    assert spy["one_year_total_return_pct"] is None  # only 36 rows of history


def test_screener_sorted_by_symbol(client):
    rows = client.get("/screener").json()
    assert [r["symbol"] for r in rows] == sorted(r["symbol"] for r in rows)