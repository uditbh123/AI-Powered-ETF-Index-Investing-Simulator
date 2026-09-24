"""API tests for PATCH /portfolios/{id} (full-holdings replacement).

Uses two tickers with DIFFERENT growth curves so a holdings swap is proven to
change the simulated outcome (identical curves would hide weight changes behind
variance). SPY drifts up 0.6%/mo, QQQ 0.3%/mo.
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


def _close_rows(drift: float) -> list[tuple[str, float, int]]:
    rows = []
    for i, d in enumerate(pd.date_range("2021-01-31", periods=MONTHS, freq="ME")):
        rows.append((d.strftime("%Y-%m-%d"), round(100.0 * (1.0 + drift) ** i, 4), 1_000_000))
    return rows


def _seed_market_data() -> None:
    conn = sqlite3.connect(settings.database_url[10:])
    conn.row_factory = sqlite3.Row
    for symbol in ("SPY", "QQQ"):
        ticker_dao.get_or_create_ticker(conn, symbol, name=f"{symbol} fund", sector="Equity")
        ticker = ticker_dao.get_ticker(conn, symbol)
        drift = 0.006 if symbol == "SPY" else 0.003
        price_dao.upsert_daily_prices(conn, ticker["id"], _close_rows(drift))
    conn.commit()
    conn.close()


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "patch.db"
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
        "name": "To Patch",
        "monthly_contribution": 100.0,
        "holdings": [{"symbol": "SPY", "weight": 0.6}, {"symbol": "QQQ", "weight": 0.4}],
    }
    payload.update(overrides)
    return client.post("/portfolios", json=payload)


def test_patch_portfolio_updates_fields_and_holdings(client):
    pid = _create_portfolio(client).json()["id"]

    response = client.patch(
        f"/portfolios/{pid}",
        json={
            "name": "Renamed",
            "monthly_contribution": 250.0,
            "holdings": [{"symbol": "QQQ", "weight": 0.7}, {"symbol": "SPY", "weight": 0.3}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == pid
    assert body["name"] == "Renamed"
    assert body["monthly_contribution"] == 250.0
    assert body["holdings"] == [
        {"symbol": "QQQ", "weight": 0.7},
        {"symbol": "SPY", "weight": 0.3},
    ]
    assert body["created_at"]

    detail = client.get(f"/portfolios/{pid}").json()
    assert detail["name"] == "Renamed"
    assert detail["monthly_contribution"] == 250.0
    assert {h["symbol"]: h["weight"] for h in detail["holdings"]} == {"QQQ": 0.7, "SPY": 0.3}


def test_patch_invalid_weights_rejected_with_422(client):
    pid = _create_portfolio(client).json()["id"]

    cases = [
        {"name": "X", "monthly_contribution": 0, "holdings": []},  # >=1 holding
        {
            "name": "X",
            "monthly_contribution": 0,
            "holdings": [{"symbol": "SPY", "weight": 0.0}],  # weight must be > 0
        },
        {
            "name": "X",
            "monthly_contribution": 0,
            "holdings": [{"symbol": "SPY", "weight": -0.5}, {"symbol": "QQQ", "weight": 1.5}],
        },
        {
            "name": "X",
            "monthly_contribution": 0,
            "holdings": [{"symbol": "SPY", "weight": 0.6}],  # sum 0.6 != 1.0
        },
        {
            "name": "X",
            "monthly_contribution": 0,
            "holdings": [{"symbol": "SPY", "weight": 0.5}, {"symbol": "QQQ", "weight": 0.4}],  # 0.9
        },
        {
            "name": "X",
            "monthly_contribution": 0,
            "holdings": [{"symbol": "SPY", "weight": 0.6}, {"symbol": "QQQ", "weight": 1.0}],  # 1.6
        },
    ]
    for payload in cases:
        assert client.patch(f"/portfolios/{pid}", json=payload).status_code == 422, payload

    # A rejected patch must not touch the stored holdings.
    detail = client.get(f"/portfolios/{pid}").json()
    assert {h["symbol"]: h["weight"] for h in detail["holdings"]} == {"SPY": 0.6, "QQQ": 0.4}


def test_patch_unknown_ticker_returns_404_and_leaves_holdings_untouched(client):
    pid = _create_portfolio(client).json()["id"]

    response = client.patch(
        f"/portfolios/{pid}",
        json={
            "name": "Should Not Stick",
            "monthly_contribution": 0,
            "holdings": [{"symbol": "SPY", "weight": 0.5}, {"symbol": "NOPE", "weight": 0.5}],
        },
    )
    assert response.status_code == 404

    detail = client.get(f"/portfolios/{pid}").json()
    assert detail["name"] == "To Patch"
    assert {h["symbol"]: h["weight"] for h in detail["holdings"]} == {"SPY": 0.6, "QQQ": 0.4}


def test_patch_missing_portfolio_returns_404(client):
    _create_portfolio(client)
    response = client.patch(
        "/portfolios/9999",
        json={
            "name": "Ghost",
            "monthly_contribution": 0,
            "holdings": [{"symbol": "SPY", "weight": 1.0}],
        },
    )
    assert response.status_code == 404


def test_patch_then_simulate_reflects_new_holdings(client):
    """Simulating after a patch uses the replaced holdings, not the old mix."""
    pid = _create_portfolio(client, holdings=[{"symbol": "SPY", "weight": 1.0}]).json()["id"]
    payload = {"initial_balance": 10_000, "horizon_months": 24, "n_simulations": 200, "seed": 3}

    run_before = client.post(f"/portfolios/{pid}/simulate", json=payload).json()
    assert run_before["cached"] is False

    patched = client.patch(
        f"/portfolios/{pid}",
        json={
            "name": "SPY, holding mix",
            "monthly_contribution": 100.0,
            "holdings": [{"symbol": "QQQ", "weight": 1.0}],
        },
    )
    assert patched.status_code == 200

    run_after = client.post(f"/portfolios/{pid}/simulate", json=payload).json()
    assert run_after["cached"] is False
    assert run_after["run_id"] != run_before["run_id"]
    # QQQ drifts half as fast as SPY -> lower simulated median outcome.
    assert run_after["summary"]["median_final_value"] < run_before["summary"]["median_final_value"]


def test_existing_simulation_runs_keep_fk_integrity_after_patch(client):
    """Runs/results referencing the portfolio survive a holdings replacement."""
    pid = _create_portfolio(client, holdings=[{"symbol": "SPY", "weight": 1.0}]).json()["id"]
    first = client.post(
        f"/portfolios/{pid}/simulate",
        json={"initial_balance": 5_000, "horizon_months": 12, "n_simulations": 150, "seed": 5},
    ).json()
    first_run_id = first["run_id"]

    patched = client.patch(
        f"/portfolios/{pid}",
        json={
            "name": "Reallocated",
            "monthly_contribution": 100.0,
            "holdings": [{"symbol": "SPY", "weight": 0.5}, {"symbol": "QQQ", "weight": 0.5}],
        },
    )
    assert patched.status_code == 200

    conn = sqlite3.connect(settings.database_url[10:])
    conn.row_factory = sqlite3.Row
    try:
        runs = conn.execute(
            "SELECT COUNT(*) FROM simulation_runs WHERE portfolio_id = ?", (pid,)
        ).fetchone()[0]
        results = conn.execute(
            "SELECT COUNT(*) FROM simulation_results WHERE run_id = ?", (first_run_id,)
        ).fetchone()[0]
        holdings = conn.execute(
            "SELECT COUNT(*) FROM portfolio_holdings WHERE portfolio_id = ?", (pid,)
        ).fetchone()[0]
    finally:
        conn.close()

    assert runs == 1
    assert results == 3
    assert holdings == 2

    # The old run is still queryable and report-generates with its stored paths.
    fetched = client.get(f"/simulation-runs/{first_run_id}")
    assert fetched.status_code == 200
    assert fetched.json()["run_id"] == first_run_id

    detail = client.get(f"/portfolios/{pid}").json()
    assert detail["name"] == "Reallocated"
    assert {h["symbol"]: h["weight"] for h in detail["holdings"]} == {"SPY": 0.5, "QQQ": 0.5}