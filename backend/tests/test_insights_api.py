"""API tests for the insights layer (Stage I).

Covers the distribution stats attached to simulation responses (stats_json on
simulation_runs) and the per-portfolio monthly-returns endpoint.
"""
import sqlite3

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.dao import prices as price_dao
from app.dao import tickers as ticker_dao
from app.database import init_db
from app.main import app

MONTHS = 36


def _monthly_close_rows() -> list[tuple[str, float, int]]:
    dates = pd.date_range("2021-01-31", periods=MONTHS, freq="ME")
    rows = []
    for i, d in enumerate(dates):
        close = 100.0 * (1.005**i)
        rows.append((d.strftime("%Y-%m-%d"), round(close, 4), 1_000_000))
    return rows


def _seed_market_data() -> None:
    conn = sqlite3.connect(settings.database_url[10:])
    conn.row_factory = sqlite3.Row
    for symbol in ("SPY", "QQQ"):
        ticker_dao.get_or_create_ticker(conn, symbol, name=f"{symbol} fund", sector="Equity")
    for symbol in ("SPY", "QQQ"):
        ticker = ticker_dao.get_ticker(conn, symbol)
        price_dao.upsert_daily_prices(conn, ticker["id"], _monthly_close_rows())
    conn.commit()
    conn.close()


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "insights.db"
    original_url = settings.database_url
    original_sched = settings.enable_scheduler
    settings.database_url = f"sqlite:///{db_path.as_posix()}"
    settings.enable_scheduler = False
    init_db()
    _seed_market_data()
    with TestClient(app) as c:
        yield c
    settings.enable_scheduler = original_sched
    settings.database_url = original_url


def _create_portfolio(client: TestClient, **overrides) -> dict:
    payload = {
        "name": "Insights Portfolio",
        "monthly_contribution": 100.0,
        "holdings": [{"symbol": "SPY", "weight": 0.6}, {"symbol": "QQQ", "weight": 0.4}],
    }
    payload.update(overrides)
    return client.post("/portfolios", json=payload).json()


def _simulate(client: TestClient, pid: int, **overrides) -> dict:
    payload = {"initial_balance": 10_000.0, "horizon_months": 36, "n_simulations": 200}
    payload.update(overrides)
    return client.post(f"/portfolios/{pid}/simulate", json=payload).json()


# ---------------------------------------------------------------------------
# Distribution stats (I2)
# ---------------------------------------------------------------------------

def test_simulate_response_includes_distribution_stats(client):
    pid = _create_portfolio(client)["id"]
    body = _simulate(client, pid)

    stats = body["stats"]
    assert stats is not None
    assert stats["total_contributed"] == pytest.approx(10_000.0 + 100.0 * 36)
    assert 0.0 <= stats["probability_of_profit"] <= 1.0

    p = stats["final_percentiles"]
    assert p["p10"] <= p["p25"] <= p["p50"] <= p["p75"] <= p["p90"]

    assert stats["median_max_drawdown"] is not None
    assert stats["median_max_drawdown"] <= 0.0
    assert stats["upside_downside_ratio"] is None or stats["upside_downside_ratio"] > 0.0

    hist = stats["histogram"]
    assert len(hist["bin_edges"]) == 21
    assert len(hist["counts"]) == 20
    assert sum(hist["counts"]) == body["params"]["n_simulations"]


def test_cached_simulate_returns_identical_stats(client):
    pid = _create_portfolio(client)["id"]
    payload = {"initial_balance": 5_000.0, "horizon_months": 24, "n_simulations": 150, "seed": 3}

    first = client.post(f"/portfolios/{pid}/simulate", json=payload).json()
    second = client.post(f"/portfolios/{pid}/simulate", json=payload).json()

    assert first["cached"] is False
    assert second["cached"] is True
    assert second["stats"] == first["stats"]


def test_legacy_run_without_stats_serves_null(client):
    pid = _create_portfolio(client)["id"]
    created = _simulate(client, pid)
    assert created["stats"] is not None

    conn = sqlite3.connect(settings.database_url[10:])
    conn.execute("UPDATE simulation_runs SET stats_json = NULL WHERE id = ?", (created["run_id"],))
    conn.commit()
    conn.close()

    fetched = client.get(f"/simulation-runs/{created['run_id']}").json()
    assert fetched["stats"] is None


# ---------------------------------------------------------------------------
# Monthly returns (I3)
# ---------------------------------------------------------------------------

def test_monthly_returns_endpoint_shape(client):
    pid = _create_portfolio(client)["id"]
    response = client.get(f"/portfolios/{pid}/monthly-returns")
    assert response.status_code == 200
    rows = response.json()

    # 36 month-ends -> 35 period returns (pct_change drops the first).
    assert len(rows) == MONTHS - 1
    assert rows[0] == {"year": 2021, "month": 2, "return": 0.005}
    assert rows[34] == {"year": 2023, "month": 12, "return": 0.005}
    years = [row["year"] for row in rows]
    assert years == sorted(years) and len(set(years)) == 3
    for row in rows:
        assert set(row) == {"year", "month", "return"}
        assert isinstance(row["year"], int)
        assert isinstance(row["month"], int)
        assert 1 <= row["month"] <= 12
    assert all(row["return"] == pytest.approx(0.005, abs=1e-4) for row in rows)


def test_monthly_returns_missing_portfolio_404(client):
    assert client.get("/portfolios/9999/monthly-returns").status_code == 404


def test_monthly_returns_no_history_400(client):
    # A portfolio whose holding has no price rows: the service must 400.
    pid = _create_portfolio(client, holdings=[{"symbol": "QQQ", "weight": 1.0}, {"symbol": "SPY", "weight": 1.0}])["id"]
    # Remove every price row to force the "no price history" branch.
    conn = sqlite3.connect(settings.database_url[10:])
    conn.execute("DELETE FROM prices")
    conn.commit()
    conn.close()
    response = client.get(f"/portfolios/{pid}/monthly-returns")
    assert response.status_code == 400