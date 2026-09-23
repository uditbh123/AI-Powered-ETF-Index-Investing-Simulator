"""API tests for DELETE /portfolios/{id} (FK-safe cascade)."""
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
    rows = []
    for i, d in enumerate(pd.date_range("2021-01-31", periods=MONTHS, freq="ME")):
        rows.append((d.strftime("%Y-%m-%d"), round(100.0 * (1.005**i), 4), 1_000_000))
    return rows


def _seed_market_data(db_url: str) -> None:
    conn = sqlite3.connect(db_url[10:])
    conn.row_factory = sqlite3.Row
    for symbol in ("SPY", "QQQ"):
        ticker_dao.get_or_create_ticker(conn, symbol, name=f"{symbol} fund", sector="Equity")
        ticker = ticker_dao.get_ticker(conn, symbol)
        price_dao.upsert_daily_prices(conn, ticker["id"], _monthly_close_rows())
    conn.commit()
    conn.close()


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "delete.db"
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


def _create_portfolio(client: TestClient) -> int:
    payload = {
        "name": "To delete",
        "monthly_contribution": 100.0,
        "holdings": [{"symbol": "SPY", "weight": 0.6}, {"symbol": "QQQ", "weight": 0.4}],
    }
    return client.post("/portfolios", json=payload).json()["id"]


def _row_counts(db_url: str, portfolio_id: int) -> dict[str, int]:
    conn = sqlite3.connect(db_url[10:])
    conn.row_factory = sqlite3.Row
    counts = {
        "portfolios": conn.execute(
            "SELECT COUNT(*) FROM portfolios WHERE id = ?", (portfolio_id,)
        ).fetchone()[0],
        "holdings": conn.execute(
            "SELECT COUNT(*) FROM portfolio_holdings WHERE portfolio_id = ?",
            (portfolio_id,),
        ).fetchone()[0],
        "runs": conn.execute(
            "SELECT COUNT(*) FROM simulation_runs WHERE portfolio_id = ?",
            (portfolio_id,),
        ).fetchone()[0],
        "results": conn.execute(
            "SELECT COUNT(*) FROM simulation_results WHERE run_id IN "
            "(SELECT id FROM simulation_runs WHERE portfolio_id = ?)",
            (portfolio_id,),
        ).fetchone()[0],
    }
    conn.close()
    return counts


def test_delete_portfolio_removes_everything(client):
    pid = _create_portfolio(client)
    sim = client.post(
        f"/portfolios/{pid}/simulate",
        json={"initial_balance": 10_000, "horizon_months": 12, "n_simulations": 150},
    )
    assert sim.status_code == 200

    assert _row_counts(settings.database_url, pid) == {
        "portfolios": 1,
        "holdings": 2,
        "runs": 1,
        "results": 3,
    }

    response = client.delete(f"/portfolios/{pid}")
    assert response.status_code == 204

    assert _row_counts(settings.database_url, pid) == {
        "portfolios": 0,
        "holdings": 0,
        "runs": 0,
        "results": 0,
    }
    assert client.get(f"/portfolios/{pid}").status_code == 404
    assert pid not in [p["id"] for p in client.get("/portfolios").json()]


def test_delete_missing_portfolio_returns_404(client):
    assert client.delete("/portfolios/9999").status_code == 404


def test_delete_again_returns_404(client):
    pid = _create_portfolio(client)
    assert client.delete(f"/portfolios/{pid}").status_code == 204
    assert client.delete(f"/portfolios/{pid}").status_code == 404


def test_delete_other_portfolio_untouched(client):
    keep = _create_portfolio(client)
    gone = _create_portfolio(client)
    client.delete(f"/portfolios/{gone}")

    assert client.get(f"/portfolios/{keep}").status_code == 200
    assert _row_counts(settings.database_url, keep)["portfolios"] == 1