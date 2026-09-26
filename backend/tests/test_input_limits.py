"""Regression tests for the Stage L4 hostile-input audit: request bounds.

Each test here corresponds to a failure the audit probe reproduced against the
pre-fix API -- an 800 GB allocation, an 18-second request, a 4 KB error body
echoing an unbounded symbol, a silently zero-variance simulation.
"""
import json
import sqlite3
from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.dao import news as news_dao
from app.dao import prices as price_dao
from app.dao import tickers as ticker_dao
from app.database import get_connection, init_db
from app.main import app
from app.routers.tickers import DEFAULT_PRICE_LIMIT
from app.schemas import (
    MAX_BLOCK_MONTHS,
    MAX_HOLDINGS,
    MAX_HOLDING_WEIGHT,
    MAX_INITIAL_BALANCE,
    MAX_MONTHLY_CONTRIBUTION,
    MAX_PATH_STEPS,
    MAX_SYMBOL_LENGTH,
    SimulationRequest,
)

MONTHS = 120


def _seed_market_data() -> None:
    conn = sqlite3.connect(settings.database_url[10:])
    conn.row_factory = sqlite3.Row
    dates = pd.date_range("2021-01-31", periods=MONTHS, freq="ME")
    rows = [
        (d.strftime("%Y-%m-%d"), round(100.0 * (1.004**i), 4), 1_000_000)
        for i, d in enumerate(dates)
    ]
    for symbol in ("SPY", "QQQ"):
        ticker_dao.get_or_create_ticker(
            conn, symbol, name=f"{symbol} fund", sector="Equity"
        )
        price_dao.upsert_daily_prices(conn, ticker_dao.get_ticker(conn, symbol)["id"], rows)
    conn.commit()
    conn.close()


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "limits.db"
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


@pytest.fixture
def pid(client):
    return client.post(
        "/portfolios",
        json={
            "name": "Limits",
            "monthly_contribution": 100.0,
            "holdings": [{"symbol": "SPY", "weight": 0.6}, {"symbol": "QQQ", "weight": 0.4}],
        },
    ).json()["id"]


# ---------------------------------------------------------------------------
# blocks: the memory-exhaustion vector
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("blocks", [10**6, 10**9, 10**12, 2**31])
def test_absurd_block_sizes_are_rejected(client, pid, blocks):
    """blocks=1e9 previously asked numpy for an 800 GB index matrix: a 500
    after 75 seconds. The block branch allocates
    (n_simulations, ceil(steps / blocks), blocks) int64 cells."""
    response = client.post(
        f"/portfolios/{pid}/simulate",
        json={"initial_balance": 1000, "horizon_months": 600, "n_simulations": 100,
              "blocks": blocks},
    )
    assert response.status_code == 422
    assert "blocks" in json.dumps(response.json())


def test_maximum_block_size_is_fast_and_small(client, pid):
    """The largest permitted block keeps the index matrix the same size as the
    i.i.d. branch (n_simulations x ~horizon)."""
    response = client.post(
        f"/portfolios/{pid}/simulate",
        json={"initial_balance": 1000, "horizon_months": 600, "n_simulations": 200,
              "blocks": MAX_BLOCK_MONTHS, "seed": 1},
    )
    assert response.status_code == 200
    assert response.json()["params"]["blocks"] == MAX_BLOCK_MONTHS


def test_blocks_of_one_is_still_allowed(client, pid):
    """The lower bound moved from gt=0 to ge=1; blocks=1 must keep working."""
    response = client.post(
        f"/portfolios/{pid}/simulate",
        json={"initial_balance": 1000, "horizon_months": 12, "n_simulations": 100,
              "blocks": 1},
    )
    assert response.status_code == 200
    assert response.json()["params"]["blocks"] == 1


def test_negative_seed_is_a_clean_422_not_a_numpy_message(client, pid):
    """seed=-1 used to return 400 {"detail": "expected non-negative integer"}."""
    response = client.post(
        f"/portfolios/{pid}/simulate",
        json={"initial_balance": 1000, "horizon_months": 12, "n_simulations": 100,
              "seed": -1},
    )
    assert response.status_code == 422
    assert "non-negative integer" not in response.text
    assert "seed" in json.dumps(response.json())


# ---------------------------------------------------------------------------
# Work factor: n_simulations * horizon_months
# ---------------------------------------------------------------------------

def test_measured_slow_combination_is_rejected(client, pid):
    """100k x 600 = 6e7 path-steps measured 18.4s before the cap."""
    response = client.post(
        f"/portfolios/{pid}/simulate",
        json={"initial_balance": 1000, "horizon_months": 600, "n_simulations": 100_000},
    )
    assert response.status_code == 422
    assert "n_simulations * horizon_months" in json.dumps(response.json())


def test_50k_paths_over_600_months_is_rejected(client, pid):
    response = client.post(
        f"/portfolios/{pid}/simulate",
        json={"initial_balance": 1000, "horizon_months": 600, "n_simulations": 50_000},
    )
    assert response.status_code == 422


def test_workload_cap_boundary_is_exact():
    """The cap is on the product, and sits just under the measured knee."""
    at_cap = MAX_PATH_STEPS // 600
    SimulationRequest(
        initial_balance=1000, horizon_months=600, n_simulations=at_cap
    )  # does not raise
    with pytest.raises(ValueError, match="n_simulations \\* horizon_months"):
        SimulationRequest(
            initial_balance=1000, horizon_months=600, n_simulations=at_cap + 1
        )


def test_largest_run_the_ui_can_produce_is_allowed():
    """The SPA never sends n_simulations, so its worst case is 1000 x 600."""
    SimulationRequest(initial_balance=10_000, horizon_months=600)
    assert 1000 * 600 <= MAX_PATH_STEPS


# ---------------------------------------------------------------------------
# Balance / contribution ceilings
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("balance", [1e13, 1e15, 1e100, 1e308])
def test_unbounded_balances_are_rejected(client, pid, balance):
    response = client.post(
        f"/portfolios/{pid}/simulate",
        json={"initial_balance": balance, "horizon_months": 12, "n_simulations": 100},
    )
    assert response.status_code == 422
    assert "numpy" not in response.text


def test_infinite_balance_token_is_rejected(client, pid):
    """``Infinity`` has no JSON encoding, so it is sent as a raw body token."""
    response = client.post(
        f"/portfolios/{pid}/simulate",
        content=b'{"initial_balance": Infinity, "horizon_months": 12}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert "numpy" not in response.text


def test_balance_ceiling_accepts_the_maximum():
    SimulationRequest(initial_balance=MAX_INITIAL_BALANCE, horizon_months=12)
    with pytest.raises(ValueError):
        SimulationRequest(initial_balance=MAX_INITIAL_BALANCE * 10, horizon_months=12)


def test_crisis_replay_balance_is_bounded(client, pid):
    assert client.post(
        f"/portfolios/{pid}/crisis-replay",
        json={"crisis": "covid_2020", "initial_balance": 1e308},
    ).status_code == 422
    assert client.post(
        f"/portfolios/{pid}/crisis-replay",
        json={"crisis": "covid_2020", "initial_balance": MAX_INITIAL_BALANCE},
    ).status_code in (200, 400)


def test_monthly_contribution_ceiling(client):
    too_big = client.post(
        "/portfolios",
        json={
            "name": "x",
            "monthly_contribution": MAX_MONTHLY_CONTRIBUTION * 1000,
            "holdings": [{"symbol": "SPY", "weight": 1.0}],
        },
    )
    assert too_big.status_code == 422
    ok = client.post(
        "/portfolios",
        json={
            "name": "x",
            "monthly_contribution": MAX_MONTHLY_CONTRIBUTION,
            "holdings": [{"symbol": "SPY", "weight": 1.0}],
        },
    )
    assert ok.status_code == 201


# ---------------------------------------------------------------------------
# Holdings payload: weight scale, list size, symbol length
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("weight", [1e308, 1e6, 100.0, 100.5, 2.0])
def test_percent_scale_and_overflowing_weights_are_rejected(client, weight):
    """A weight above a whole sleeve is refused.

    1e308 is the original overflow probe: two such holdings summed to inf,
    every normalized weight became 0, and the engine returned a silently flat,
    zero-variance fan chart. 100.0 / 100.5 / 2.0 are the percent-scale
    mistake this convention now catches at the door -- the interim ``<= 100``
    cap used to admit all three, and 60/40 silently became a uniform blend.
    """
    response = client.post(
        "/portfolios",
        json={
            "name": "overflow",
            "holdings": [{"symbol": "SPY", "weight": weight},
                         {"symbol": "QQQ", "weight": weight}],
        },
    )
    assert response.status_code == 422
    assert "weight" in json.dumps(response.json())


def test_infinite_weight_token_is_rejected(client):
    response = client.post(
        "/portfolios",
        content=b'{"name": "x", "holdings": [{"symbol": "SPY", "weight": Infinity}]}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert "weight" in json.dumps(response.json())


def test_weight_is_a_fraction_and_fractions_are_accepted():
    """The convention: fractions in (0, 1]. A whole sleeve is 1.0.

    Checked per-weight via the schema (each holding is paired with a
    complement so the sum rule cannot be what rejects the case).
    """
    for weight in (0.001, 0.1, 0.5, 0.6, 0.999, 1.0):
        assert _weight_accepted(weight), weight
    for weight in (100.0, 2.0, MAX_HOLDING_WEIGHT * 1.01):
        assert not _weight_accepted(weight), weight


def _weight_accepted(weight: float) -> bool:
    """Does HoldingIn accept this weight? (Sum rule deliberately satisfied.)"""
    from app.schemas import HoldingIn

    try:
        HoldingIn(symbol="SPY", weight=weight)
    except Exception:
        return False
    return True


def test_weight_ceiling_is_one():
    """MAX_HOLDING_WEIGHT is the fraction ceiling, not the old percent cap.

    It is the load-bearing constant for the overflow guard: with the sum
    bounded by MAX_HOLDINGS, the inf that motivated the cap is unreachable.
    """
    assert MAX_HOLDING_WEIGHT == 1.0
    assert MAX_HOLDING_WEIGHT * MAX_HOLDINGS == MAX_HOLDINGS


def test_weight_sum_must_be_one_within_tolerance_on_create(client):
    """The create endpoint enforces the same sum rule as PATCH.

    Before the convention change, POST only required a positive sum while
    PATCH required ~1.0, so a portfolio could be created that could never be
    re-saved with its own weights.
    """
    for holdings, why in (
        ([{"symbol": "SPY", "weight": 0.6}], "under: 0.6"),
        ([{"symbol": "SPY", "weight": 0.5}, {"symbol": "QQQ", "weight": 0.4}], "0.9"),
        ([{"symbol": "SPY", "weight": 0.6}, {"symbol": "QQQ", "weight": 0.6}], "over: 1.2"),
        ([{"symbol": "SPY", "weight": 0.995}, {"symbol": "QQQ", "weight": 0.02}], "1.015"),
    ):
        response = client.post("/portfolios", json={"name": "x", "holdings": holdings})
        assert response.status_code == 422, why
        detail = json.dumps(response.json())
        assert "sum" in detail, why

    # Inside the tolerance: float drift on an exact 1.0 is still accepted.
    ok = client.post(
        "/portfolios",
        json={"name": "x", "holdings": [{"symbol": "SPY", "weight": 0.1},
                                        {"symbol": "QQQ", "weight": 0.2},
                                        {"symbol": "VTI", "weight": 0.7}]},
    )
    assert ok.status_code == 201, ok.text


def test_percent_scale_payload_is_rejected_by_create_and_patch(client, pid):
    """The regression this convention exists for: 60/40 sent as 60/40.

    Asserted on both verbs, since a payload that creates cleanly must be
    re-savable and vice versa.
    """
    percent_scale = [
        {"symbol": "SPY", "weight": 60.0},
        {"symbol": "QQQ", "weight": 40.0},
    ]

    created = client.post(
        "/portfolios",
        json={"name": "percent", "monthly_contribution": 100.0, "holdings": percent_scale},
    )
    assert created.status_code == 422
    assert "0.6" in created.text, "the error should name the fraction it expected"

    patched = client.patch(
        f"/portfolios/{pid}",
        json={"name": "percent", "monthly_contribution": 100.0, "holdings": percent_scale},
    )
    assert patched.status_code == 422
    assert "0.6" in patched.text

    # ...and the portfolio is untouched by the rejected PATCH.
    assert {h["symbol"]: h["weight"] for h in client.get(f"/portfolios/{pid}").json()["holdings"]} == {
        "SPY": 0.6,
        "QQQ": 0.4,
    }


def test_holdings_list_length_is_capped(client):
    each = 1.0 / MAX_HOLDINGS
    too_many = client.post(
        "/portfolios",
        json={
            "name": "x",
            "holdings": [{"symbol": "SPY", "weight": each}] * (MAX_HOLDINGS + 1),
        },
    )
    assert too_many.status_code == 422
    at_cap = client.post(
        "/portfolios",
        json={
            "name": "x",
            "holdings": [{"symbol": "SPY", "weight": each}] * MAX_HOLDINGS,
        },
    )
    assert at_cap.status_code == 201


def test_absurd_symbol_is_rejected_not_echoed(client):
    """A 4000-char symbol used to come back inside a 4 KB 404 detail."""
    response = client.post(
        "/portfolios", json={"name": "x", "holdings": [{"symbol": "A" * 4000, "weight": 1.0}]}
    )
    assert response.status_code == 422
    assert len(response.text) < 1000
    assert "A" * 4000 not in response.text


def test_long_symbol_in_the_path_is_rejected_not_echoed(client):
    response = client.get(f"/tickers/{'A' * 4000}/prices")
    assert response.status_code == 422
    assert len(response.text) < 1000
    assert "A" * 4000 not in response.text


def test_symbol_at_the_cap_still_reaches_the_catalog_lookup(client):
    response = client.get(f"/tickers/{'A' * MAX_SYMBOL_LENGTH}/prices")
    assert response.status_code == 404
    assert response.json()["detail"] == f"ticker '{'A' * MAX_SYMBOL_LENGTH}' not found"


# ---------------------------------------------------------------------------
# List endpoints: the SQL cap and the default price limit
# ---------------------------------------------------------------------------

def test_news_headline_cap_is_applied_in_sql(client, monkeypatch):
    """The 100-row cap used to happen in Python, after every matching row in the
    window had been loaded. Now list_sentiment must receive the limit."""
    seen: list[int | None] = []
    original = news_dao.list_sentiment

    def _spy(conn, **kwargs):
        seen.append(kwargs.get("limit"))
        return original(conn, **kwargs)

    conn = get_connection()
    today = date.today().isoformat()
    news_dao.insert_sentiment(
        conn,
        [(None, f"headline {i}", "src", today, 0.1, "sector") for i in range(250)],
    )
    conn.commit()
    conn.close()

    import app.routers.news as news_router

    monkeypatch.setattr(news_router.news_dao, "list_sentiment", _spy)
    body = client.get("/news", params={"category": "sector", "days": 90}).json()

    assert body["n_headlines"] == 100
    assert len(body["headlines"]) == 100
    assert seen and all(limit == 100 for limit in seen)


def test_news_limit_reaches_the_dao_for_the_ticker_filtered_query(client, monkeypatch):
    seen: list[int | None] = []
    original = news_dao.list_sentiment

    def _spy(conn, **kwargs):
        seen.append(kwargs.get("limit"))
        return original(conn, **kwargs)

    import app.routers.news as news_router

    monkeypatch.setattr(news_router.news_dao, "list_sentiment", _spy)
    client.get("/news", params={"category": "sector", "ticker_id": 1})

    assert seen == [100]


def test_ticker_prices_are_bounded_without_an_explicit_limit(client):
    """limit used to default to None, i.e. the entire price table."""
    rows = DEFAULT_PRICE_LIMIT + 120
    conn = get_connection()
    ticker = ticker_dao.get_or_create_ticker(conn, "LONG", name="Long", sector="Equity")
    dates = pd.date_range("1950-01-02", periods=rows, freq="B")
    price_dao.upsert_daily_prices(
        conn, ticker["id"], [(d.strftime("%Y-%m-%d"), 100.0, 1) for d in dates]
    )
    conn.commit()
    conn.close()

    default = client.get("/tickers/LONG/prices")
    assert default.status_code == 200
    prices = default.json()["prices"]
    assert len(prices) == DEFAULT_PRICE_LIMIT
    # The most recent rows are kept, still in ascending date order.
    assert prices == sorted(prices, key=lambda p: p["date"])
    assert prices[-1]["date"] == dates[-1].strftime("%Y-%m-%d")

    assert client.get("/tickers/LONG/prices", params={"limit": 10_001}).status_code == 422
    assert client.get("/tickers/LONG/prices", params={"limit": 10}).json()["prices"].__len__() == 10


# ---------------------------------------------------------------------------
# Missing portfolios are 404, not 400
# ---------------------------------------------------------------------------

def test_simulate_missing_portfolio_returns_404(client):
    response = client.post(
        "/portfolios/999999/simulate", json={"initial_balance": 1000, "horizon_months": 12}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "portfolio not found"


def test_crisis_replay_missing_portfolio_returns_404(client):
    response = client.post(
        "/portfolios/999999/crisis-replay",
        json={"crisis": "gfc_2008", "initial_balance": 1000},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "portfolio not found"
