"""End-to-end API tests: tickers, portfolios, simulation trigger + caching.

Uses a temp SQLite file and synthetic monthly close data inserted directly via
the DAO layer (no network). Scheduler is disabled for these tests.
"""
import sqlite3
from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.dao import news as news_dao
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
        ticker_dao.get_or_create_ticker(
            conn, symbol, name=f"{symbol} fund" if symbol != "^GSPC" else "S&P 500", sector="Equity"
        )
    for symbol in ("SPY", "QQQ"):
        ticker = ticker_dao.get_ticker(conn, symbol)
        price_dao.upsert_daily_prices(conn, ticker["id"], _monthly_close_rows())
    conn.commit()
    conn.close()


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "api.db"
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
        "name": "Test Portfolio",
        "monthly_contribution": 100.0,
        "holdings": [{"symbol": "SPY", "weight": 0.6}, {"symbol": "QQQ", "weight": 0.4}],
    }
    payload.update(overrides)
    return client.post("/portfolios", json=payload)


def _seed_sentiment(symbol: str, score: float, category: str = "sector") -> None:
    """Insert one recent scored headline for a ticker (or macro when symbol None)."""
    conn = sqlite3.connect(settings.database_url[10:])
    conn.row_factory = sqlite3.Row
    ticker_id = None
    if symbol is not None:
        ticker_id = ticker_dao.get_ticker(conn, symbol)["id"]
    news_dao.insert_sentiment(
        conn,
        [
            (
                ticker_id,
                f"{symbol or 'macro'} headline {score}",
                "test-src",
                date.today().isoformat(),
                score,
                category,
            )
        ],
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Tickers
# ---------------------------------------------------------------------------

def test_list_tickers(client):
    response = client.get("/tickers")
    assert response.status_code == 200
    body = response.json()
    by_symbol = {t["symbol"]: t for t in body}
    assert set(by_symbol) >= {"SPY", "QQQ"}
    spy = by_symbol["SPY"]
    assert spy["price_rows"] == MONTHS
    assert spy["first_date"]
    assert spy["last_date"]


def test_get_ticker_prices_returns_history(client):
    response = client.get("/tickers/SPY/prices")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "SPY"
    assert len(body["prices"]) == MONTHS
    assert body["prices"][0]["date"] < body["prices"][-1]["date"]
    assert body["prices"][-1]["close"] > body["prices"][0]["close"]


def test_get_ticker_prices_limit_returns_most_recent(client):
    response = client.get("/tickers/SPY/prices", params={"limit": 5})
    assert response.status_code == 200
    prices = response.json()["prices"]
    assert len(prices) == 5
    assert prices == sorted(prices, key=lambda p: p["date"])


def test_get_ticker_prices_unknown_symbol_returns_404(client):
    assert client.get("/tickers/NOPE/prices").status_code == 404


# ---------------------------------------------------------------------------
# Portfolios
# ---------------------------------------------------------------------------

def test_create_portfolio(client):
    response = _create_portfolio(client)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Test Portfolio"
    assert body["monthly_contribution"] == 100.0
    assert {h["symbol"] for h in body["holdings"]} == {"SPY", "QQQ"}


def test_create_portfolio_unknown_ticker_returns_404(client):
    response = _create_portfolio(client, holdings=[{"symbol": "NOPE", "weight": 1.0}])
    assert response.status_code == 404


def test_create_portfolio_invalid_weights_rejected(client):
    response = _create_portfolio(client, holdings=[{"symbol": "SPY", "weight": -1.0}])
    assert response.status_code == 422

    response = _create_portfolio(client, holdings=[])
    assert response.status_code == 422


def test_list_and_get_portfolio(client):
    created = _create_portfolio(client).json()
    pid = created["id"]

    listing = client.get("/portfolios")
    assert listing.status_code == 200
    assert any(p["id"] == pid for p in listing.json())

    detail = client.get(f"/portfolios/{pid}")
    assert detail.status_code == 200
    assert detail.json()["id"] == pid

    assert client.get("/portfolios/9999").status_code == 404


# ---------------------------------------------------------------------------
# Simulation trigger + caching
# ---------------------------------------------------------------------------

def test_trigger_simulation_returns_fan_chart(client):
    pid = _create_portfolio(client).json()["id"]
    response = client.post(
        f"/portfolios/{pid}/simulate",
        json={"initial_balance": 10_000, "horizon_months": 12, "n_simulations": 200},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["cached"] is False
    assert body["params"]["horizon_months"] == 12
    assert len(body["percentiles"]) == 3
    levels = [p["level"] for p in body["percentiles"]]
    assert levels == [10, 50, 90]
    for band in body["percentiles"]:
        assert len(band["path"]) == 13  # horizon + initial balance
        assert all(v > 0 for v in band["path"])
    assert body["summary"]["median_final_value"] > 0
    assert body["sentiment"] == {
        "applied": False,
        "score": None,
        "volatility_multiplier": 1.0,
    }


def test_simulation_reuses_cached_run_with_identical_params(client):
    pid = _create_portfolio(client).json()["id"]
    payload = {"initial_balance": 5_000, "horizon_months": 24, "n_simulations": 150, "seed": 3}

    first = client.post(f"/portfolios/{pid}/simulate", json=payload).json()
    second = client.post(f"/portfolios/{pid}/simulate", json=payload).json()

    assert first["cached"] is False
    assert second["cached"] is True
    assert second["run_id"] == first["run_id"]
    assert second["percentiles"] == first["percentiles"]


def test_different_params_generate_new_run(client):
    pid = _create_portfolio(client).json()["id"]
    payload = {"initial_balance": 5_000, "horizon_months": 24, "n_simulations": 150, "seed": 3}
    other = {"initial_balance": 5_000, "horizon_months": 25, "n_simulations": 150, "seed": 3}

    first = client.post(f"/portfolios/{pid}/simulate", json=payload).json()
    second = client.post(f"/portfolios/{pid}/simulate", json=other).json()

    assert first["run_id"] != second["run_id"]
    assert second["cached"] is False


def test_fetch_cached_run_by_id(client):
    pid = _create_portfolio(client).json()["id"]
    created = client.post(
        f"/portfolios/{pid}/simulate",
        json={"initial_balance": 5_000, "horizon_months": 12, "n_simulations": 150, "seed": 7},
    ).json()

    fetched = client.get(f"/simulation-runs/{created['run_id']}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["run_id"] == created["run_id"]
    assert body["cached"] is True
    assert body["percentiles"] == created["percentiles"]
    assert "maximum_balance" not in body["params"]

    assert client.get("/simulation-runs/99999").status_code == 404


def test_simulate_portfolio_without_holdings_returns_400(client):
    response = _create_portfolio(client)
    # not supported to create a portfolio without holdings via API, so bypass schema:
    conn = sqlite3.connect(settings.database_url[10:])
    conn.row_factory = sqlite3.Row
    user = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
    cur = conn.execute(
        "INSERT INTO portfolios (user_id, name, monthly_contribution) VALUES (?, ?, ?)",
        (user["id"], "Empty", 0.0),
    )
    conn.commit()
    pid = cur.lastrowid
    conn.close()

    response = client.post(
        f"/portfolios/{pid}/simulate", json={"initial_balance": 1000, "horizon_months": 12}
    )
    assert response.status_code == 400
    assert "no holdings" in response.json()["detail"]


def test_simulate_portfolio_with_unavailable_ticker_returns_400(client):
    """A holding whose ticker has no price history must not 500."""
    response = _create_portfolio(
        client, holdings=[{"symbol": "SPY", "weight": 0.5}, {"symbol": "GLD", "weight": 0.5}]
    )
    pid = response.json()["id"]
    resp = client.post(
        f"/portfolios/{pid}/simulate", json={"initial_balance": 1000, "horizon_months": 12}
    )
    assert resp.status_code == 400
    assert "GLD" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Sentiment-adjusted simulation (Phase 6)
# ---------------------------------------------------------------------------

def test_negative_sentiment_widens_the_fan_chart(client):
    pid = _create_portfolio(client).json()["id"]
    payload = {"initial_balance": 10_000, "horizon_months": 24, "n_simulations": 500, "seed": 5}

    baseline = client.post(f"/portfolios/{pid}/simulate", json=payload).json()

    _seed_sentiment("SPY", -0.9, category="sector")
    adjusted = client.post(
        f"/portfolios/{pid}/simulate", json={**payload, "use_sentiment": True}
    ).json()

    assert adjusted["cached"] is False
    assert adjusted["sentiment"]["applied"] is True
    assert adjusted["sentiment"]["score"] == pytest.approx(-0.9)
    assert adjusted["sentiment"]["volatility_multiplier"] > 1.0

    def final_spread(body):
        worst = next(p for p in body["percentiles"] if p["level"] == 10)["path"][-1]
        best = next(p for p in body["percentiles"] if p["level"] == 90)["path"][-1]
        return best - worst

    assert final_spread(adjusted) > final_spread(baseline)


def test_geopolitical_sentiment_also_adjusts_volatility(client):
    pid = _create_portfolio(client).json()["id"]
    _seed_sentiment(None, -0.8, category="geopolitical")
    body = client.post(
        f"/portfolios/{pid}/simulate",
        json={"initial_balance": 5000, "horizon_months": 12, "n_simulations": 200, "use_sentiment": True},
    ).json()
    assert body["sentiment"]["applied"] is True
    assert body["sentiment"]["score"] == pytest.approx(-0.8)
    assert body["sentiment"]["volatility_multiplier"] > 1.0


def test_positive_sentiment_narrows_volatility(client):
    pid = _create_portfolio(client).json()["id"]
    _seed_sentiment("SPY", 1.0, category="sector")
    body = client.post(
        f"/portfolios/{pid}/simulate",
        json={"initial_balance": 5000, "horizon_months": 12, "n_simulations": 200, "use_sentiment": True},
    ).json()
    assert body["sentiment"]["volatility_multiplier"] == pytest.approx(0.75)


def test_sentiment_flag_without_news_falls_back_to_neutral(client):
    pid = _create_portfolio(client).json()["id"]
    body = client.post(
        f"/portfolios/{pid}/simulate",
        json={"initial_balance": 5000, "horizon_months": 12, "n_simulations": 150, "use_sentiment": True},
    ).json()
    assert body["sentiment"] == {
        "applied": False,
        "score": None,
        "volatility_multiplier": 1.0,
    }


def test_sentiment_flag_changes_the_cache_key(client):
    pid = _create_portfolio(client).json()["id"]
    payload = {"initial_balance": 5000, "horizon_months": 12, "n_simulations": 150, "seed": 1}
    plain = client.post(f"/portfolios/{pid}/simulate", json=payload).json()
    senti = client.post(
        f"/portfolios/{pid}/simulate", json={**payload, "use_sentiment": True}
    ).json()
    assert plain["run_id"] != senti["run_id"]