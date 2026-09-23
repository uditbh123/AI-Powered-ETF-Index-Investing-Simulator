"""Tests for crisis replay: window slicing, closed-form compounding, API wiring."""
import sqlite3

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.dao import prices as price_dao
from app.dao import tickers as ticker_dao
from app.database import init_db
from app.main import app
from app.services import crisis


def _month_end_dates(start="2000-01-31", periods=48):
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(start, periods=periods, freq="ME")]


# ---------------------------------------------------------------------------
# Unit: window slicing
# ---------------------------------------------------------------------------

def test_slice_gfc_takes_exactly_eighteen_months():
    dates = _month_end_dates("2007-01-31", 48)
    returns = np.linspace(-0.01, 0.01, len(dates))
    sliced, window = crisis.slice_window(dates, returns, "gfc_2008")
    assert len(window) == 18
    assert window[0] == "2007-10-31"
    assert window[-1] == "2009-03-31"
    assert len(sliced) == 18


def test_slice_dot_com_takes_thirty_one_months():
    dates = _month_end_dates("2000-01-31", 72)
    returns = np.zeros(len(dates))
    _, window = crisis.slice_window(dates, returns, "dot_com_2000")
    assert len(window) == 31
    assert window[0] == "2000-03-31"
    assert window[-1] == "2002-09-30"


def test_slice_covid_takes_three_months():
    dates = _month_end_dates("2019-12-31", 24)
    returns = np.zeros(len(dates))
    sliced, window = crisis.slice_window(dates, returns, "covid_2020")
    assert len(window) == 3
    assert window[0] == "2020-02-29"
    assert window[-1] == "2020-04-30"
    assert len(sliced) == 3


def test_slice_error_names_crisis_and_history_ended_too_early():
    dates = _month_end_dates("2000-01-31", 48)  # ends ~2003-12, pre-dates gfc
    with pytest.raises(ValueError, match="gfc_2008"):
        crisis.slice_window(dates, np.zeros(len(dates)), "gfc_2008")
    with pytest.raises(ValueError, match="price history ends before the crisis began"):
        crisis.slice_window(dates, np.zeros(len(dates)), "gfc_2008")


def test_slice_error_when_launched_after_window():
    dates = _month_end_dates("2010-01-31", 24)
    with pytest.raises(ValueError, match="instruments launched after the crisis window ended"):
        crisis.slice_window(dates, np.zeros(len(dates)), "dot_com_2000")


def test_slice_error_on_partial_overlap():
    dates = _month_end_dates("2007-01-31", 24)  # 2007-01..2008-12 only
    with pytest.raises(ValueError, match="does not cover it fully"):
        crisis.slice_window(dates, np.zeros(len(dates)), "gfc_2008")


# ---------------------------------------------------------------------------
# Unit: compounding closed form (annuity-due, matches the engine convention)
# ---------------------------------------------------------------------------

def test_compound_actual_matches_annuity_due_closed_form():
    r, t = 0.01, 18
    path = crisis.compound_actual(np.full(t, r), initial_balance=1000.0, monthly_contribution=100.0)
    assert len(path) == t + 1
    assert path[0] == 1000.0
    expected = 1000 * (1 + r) ** t + 100 * (1 + r) * (((1 + r) ** t - 1) / r)
    assert np.allclose(path[-1], expected)


def test_compound_actual_no_contributions_is_plain_growth():
    r, t = 0.02, 12
    path = crisis.compound_actual(np.full(t, r), initial_balance=5000.0, monthly_contribution=0.0)
    assert np.allclose(path[-1], 5000.0 * (1 + r) ** t)


# ---------------------------------------------------------------------------
# API wiring
# ---------------------------------------------------------------------------

def _seed_covid_market_data(db_url: str) -> None:
    conn = sqlite3.connect(db_url[10:])
    conn.row_factory = sqlite3.Row
    ticker = ticker_dao.get_or_create_ticker(conn, "SPY", "SPDR S&P 500 ETF", "Equity")
    rows = []
    for i, d in enumerate(pd.date_range("2019-01-31", periods=24, freq="ME")):
        close = 100.0 * (1.01**i)
        if d.month == 2 and d.year == 2020:
            close *= 0.85
        if d.month == 3 and d.year == 2020:
            close *= 0.80
        if d.month == 4 and d.year == 2020:
            close *= 1.05
        rows.append((d.strftime("%Y-%m-%d"), round(close, 4), 1_000_000))
    price_dao.upsert_daily_prices(conn, ticker["id"], rows)
    conn.commit()
    conn.close()


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "crisis.db"
    original_url = settings.database_url
    original_sched = settings.enable_scheduler
    settings.database_url = f"sqlite:///{db_path.as_posix()}"
    settings.enable_scheduler = False
    init_db()
    _seed_covid_market_data(settings.database_url)
    with TestClient(app) as c:
        yield c
    settings.enable_scheduler = original_sched
    settings.database_url = original_url


def _create_portfolio(client: TestClient) -> int:
    payload = {
        "name": "Crisis test",
        "monthly_contribution": 100.0,
        "holdings": [{"symbol": "SPY", "weight": 1.0}],
    }
    return client.post("/portfolios", json=payload).json()["id"]


def test_crisis_replay_seeds_history_covering_window(client):
    pid = _create_portfolio(client)
    response = client.post(
        f"/portfolios/{pid}/crisis-replay",
        json={"crisis": "covid_2020", "initial_balance": 10_000},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["crisis"] == "covid_2020"
    assert body["portfolio_id"] == pid
    assert body["window"]["months"] == 3
    assert body["window"]["start"] == "2020-02-29"
    assert body["window"]["end"] == "2020-04-30"
    assert body["initial_balance"] == 10_000
    assert body["monthly_contribution"] == 100.0

    assert body["real_path"][0] == 10_000
    assert len(body["real_path"]) == 4  # initial + 3 months

    levels = [p["level"] for p in body["percentiles"]]
    assert levels == [10, 50, 90]
    for band in body["percentiles"]:
        assert len(band["path"]) == 4
        assert all(v > 0 for v in band["path"])


def test_crisis_replay_deterministic_with_fixed_seed(client):
    pid = _create_portfolio(client)
    payload = {"crisis": "covid_2020", "initial_balance": 10_000}
    first = client.post(f"/portfolios/{pid}/crisis-replay", json=payload).json()
    second = client.post(f"/portfolios/{pid}/crisis-replay", json=payload).json()
    assert first["percentiles"] == second["percentiles"]


def test_crisis_replay_insufficient_history_returns_400(client):
    # A fresh portfolio on the seeded series covers covid, this one does too,
    # but a dot_com replay predates all seeded prices.
    pid = _create_portfolio(client)
    response = client.post(
        f"/portfolios/{pid}/crisis-replay",
        json={"crisis": "dot_com_2000", "initial_balance": 10_000},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "dot_com_2000" in detail


def test_crisis_replay_unknown_crisis_returns_422(client):
    pid = _create_portfolio(client)
    response = client.post(
        f"/portfolios/{pid}/crisis-replay",
        json={"crisis": "tech_wreck", "initial_balance": 10_000},
    )
    assert response.status_code == 422


def test_crisis_replay_invalid_initial_balance_returns_422(client):
    pid = _create_portfolio(client)
    assert (
        client.post(
            f"/portfolios/{pid}/crisis-replay",
            json={"crisis": "covid_2020", "initial_balance": 0},
        ).status_code
        == 422
    )


def test_crisis_replay_missing_portfolio_returns_400(client):
    response = client.post(
        "/portfolios/9999/crisis-replay",
        json={"crisis": "covid_2020", "initial_balance": 10_000},
    )
    assert response.status_code == 400
    assert "portfolio 9999 not found" == response.json()["detail"]


def test_crisis_replay_portfolio_without_holdings_returns_400(client):
    from app.dao import portfolios as portfolio_dao

    conn = sqlite3.connect(settings.database_url[10:])
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "INSERT INTO portfolios (user_id, name, monthly_contribution) VALUES (?, ?, ?)",
        (portfolio_dao.get_or_create_user(conn), "Empty", 0.0),
    )
    conn.commit()
    pid = cur.lastrowid
    conn.close()

    response = client.post(
        f"/portfolios/{pid}/crisis-replay",
        json={"crisis": "covid_2020", "initial_balance": 10_000},
    )
    assert response.status_code == 400
    assert "no holdings" in response.json()["detail"]