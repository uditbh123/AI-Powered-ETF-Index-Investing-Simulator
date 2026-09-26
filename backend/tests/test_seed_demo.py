"""Tests for the demo-data seeding script (app/scripts/seed_demo.py)."""
from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.dao import portfolios as portfolio_dao
from app.dao import prices as price_dao
from app.dao import tickers as ticker_dao
from app.data.ticker_catalog import DEFAULT_TICKERS, catalog_by_symbol
from app.database import get_connection, init_db
from app.main import app
from app.schemas import PortfolioCreate
from app.scripts import seed_demo as seed_demo_module
from app.scripts.seed_demo import DEMO_USER_NAME, seed_demo

EXPECTED_NAMES = ["All-World Growth", "Balanced 60/40", "Tech Tilt"]

SIMULATE_BODY = {
    "initial_balance": 10_000.0,
    "horizon_months": 60,
    "n_simulations": 500,
    "seed": 42,
}


def _monthly_close_rows(count: int = 36) -> list[tuple[str, float, int]]:
    rows = []
    month = 1
    year = 2021
    year_length = 12
    for i in range(count):
        month = (i % year_length) + 1
        year = 2021 + i // year_length
        rows.append((f"{year:04d}-{month:02d}-28", 100.0 + i, 1_000_000))
    return rows


def _volatile_close_rows(count: int = 60, phase: int = 0) -> list[tuple[str, float, int]]:
    """Monthly closes with real drawdowns, deterministic (no RNG).

    A monotonic series would push probability_of_profit to exactly 1.0, and an
    assertion of "1.0 < p" could not tell a correct 60/40 blend from a wrong
    uniform 1/N one. The cycle gives each symbol a different return path, so a
    mis-scaled weight changes the number instead of leaving it at a plausible
    extreme.
    """
    rows = []
    for i in range(count):
        year = 2021 + i // 12
        month = (i % 12) + 1
        close = 100.0 * (1.002**i) * (1.0 + 0.18 * math.sin((i + 3.0 * phase) / 3.0))
        rows.append((f"{year:04d}-{month:02d}-28", round(close, 4), 1_000_000))
    return rows


def _seed_catalog(conn, catalog: list | None = None) -> None:
    ticker_dao.upsert_catalog(conn, catalog or list(DEFAULT_TICKERS))
    conn.commit()


def _seed_prices(conn, symbols: list[str], rows: list[tuple[str, float, int]]) -> None:
    for symbol in symbols:
        ticker = ticker_dao.get_ticker(conn, symbol)
        assert ticker is not None, f"catalog missing {symbol}"
        price_dao.upsert_daily_prices(conn, ticker["id"], rows)
    conn.commit()


@pytest.fixture
def seeded_client(tmp_path):
    """A TestClient over a temp DB with the three demo portfolios seeded.

    Yields ``(client, seed_results)`` so a test can address the seeded
    portfolios by id.
    """
    db_path = tmp_path / "seeded.db"
    original_url = settings.database_url
    original_sched = settings.enable_scheduler
    settings.database_url = f"sqlite:///{db_path.as_posix()}"
    settings.enable_scheduler = False
    init_db()
    conn = get_connection()
    _seed_catalog(conn)
    for phase, symbol in enumerate(("VXUS", "VTI", "BND", "QQQ")):
        _seed_prices(conn, [symbol], _volatile_close_rows(phase=phase))
    results = seed_demo(conn)
    conn.close()
    with TestClient(app) as c:
        yield c, results
    settings.enable_scheduler = original_sched
    settings.database_url = original_url


def test_seed_demo_is_idempotent(db):
    _seed_catalog(db)

    first = seed_demo(db)
    second = seed_demo(db)

    assert [r["name"] for r in first] == EXPECTED_NAMES
    assert all(r["created"] for r in first)
    assert not any(r["created"] for r in second)
    # A second run finds the stored rows already correct, so it repairs nothing.
    assert not any(r["repaired"] for r in second)
    assert [r["id"] for r in first] == [r["id"] for r in second]

    user_id = portfolio_dao.get_or_create_user(db, DEMO_USER_NAME)
    portfolios = db.execute(
        "SELECT * FROM portfolios WHERE user_id = ?", (user_id,)
    ).fetchall()
    assert [p["name"] for p in portfolios] == EXPECTED_NAMES

    for r in first:
        assert sum(h["weight"] for h in r["holdings"]) == pytest.approx(1.0)
        assert len(r["holdings"]) >= 1


def test_seeded_weights_are_fractions_in_the_unit_interval(db):
    """The seeder must match the API convention: (0, 1] summing to 1.0.

    This is the guard that catches a return to percent scale. A 100.0 stored
    weight is rejected by PortfolioCreate/PortfolioUpdate, so the demo data
    would become unservable the moment anyone edited it through the UI.
    """
    _seed_catalog(db)
    results = seed_demo(db)

    for result in results:
        weights = [h["weight"] for h in result["holdings"]]
        for weight in weights:
            assert 0.0 < weight <= 1.0, f"{result['name']}: {weight} is not a fraction"
        assert sum(weights) == pytest.approx(1.0), result["name"]

        # Round-trips through the create schema, i.e. the API would accept it.
        PortfolioCreate(
            name=result["name"],
            holdings=[{"symbol": h["symbol"], "weight": h["weight"]} for h in result["holdings"]],
        )


def test_rerunning_repairs_percent_scale_rows_from_an_older_seed(db):
    """A DB seeded before the fraction convention holds 100/60/40 weights.

    Re-running the seeder must rewrite those to fractions rather than leaving
    them stranded: the API rejects them, so the portfolio could not be edited
    or re-saved through the UI until it was repaired.
    """
    _seed_catalog(db)
    first = seed_demo(db)
    balanced_id = next(r for r in first if r["name"] == "Balanced 60/40")["id"]

    # Simulate the old seed: overwrite the holdings with percent-scale values.
    user_id = portfolio_dao.get_or_create_user(db, DEMO_USER_NAME)
    portfolio_dao.delete_holdings(db, balanced_id)
    for symbol, weight in (("VTI", 60.0), ("BND", 40.0)):
        ticker = ticker_dao.get_ticker(db, symbol)
        portfolio_dao.add_holding(db, balanced_id, ticker["id"], weight)
    db.commit()

    second = seed_demo(db)
    repaired = next(r for r in second if r["name"] == "Balanced 60/40")
    assert repaired["id"] == balanced_id, "the same portfolio should be repaired, not recreated"
    assert repaired["created"] is False
    assert repaired["repaired"] is True
    assert [h["weight"] for h in repaired["holdings"]] == pytest.approx([0.6, 0.4])

    # And a third run is a no-op again.
    third = seed_demo(db)
    assert not any(r["repaired"] for r in third)


def test_rerunning_repairs_a_changed_monthly_contribution(db):
    _seed_catalog(db)
    first = seed_demo(db)
    tilt_id = next(r for r in first if r["name"] == "Tech Tilt")["id"]

    db.execute(
        "UPDATE portfolios SET monthly_contribution = 5.0 WHERE id = ?", (tilt_id,)
    )
    db.commit()

    second = seed_demo(db)
    tilt = next(r for r in second if r["name"] == "Tech Tilt")
    assert tilt["repaired"] is True
    assert tilt["monthly_contribution"] == 200.0


def test_rerunning_does_not_duplicate_holdings(db):
    """The repair path deletes before re-inserting; a bug there would double
    the holdings and silently renormalize the portfolio."""
    _seed_catalog(db)
    seed_demo(db)
    user_id = portfolio_dao.get_or_create_user(db, DEMO_USER_NAME)
    balanced = portfolio_dao.get_portfolio_by_user_and_name(db, user_id, "Balanced 60/40")
    portfolio_dao.update_portfolio(db, balanced["id"], name="Balanced 60/40", monthly_contribution=1.0)
    db.commit()

    seed_demo(db)
    holdings = portfolio_dao.list_holdings(db, balanced["id"])
    assert len(holdings) == 2
    assert sum(float(h["weight"]) for h in holdings) == pytest.approx(1.0)


def test_all_world_growth_is_single_global_equity_etf(db):
    _seed_catalog(db)
    results = seed_demo(db)
    portfolio = next(r for r in results if r["name"] == "All-World Growth")
    assert portfolio["monthly_contribution"] == 200.0
    assert portfolio["holdings"] == [
        {"symbol": "VXUS", "name": "Vanguard Total International Stock ETF", "weight": 1.0}
    ]


def test_balanced_uses_bond_etf_when_catalog_has_one(db):
    _seed_catalog(db)
    results = seed_demo(db)
    portfolio = next(r for r in results if r["name"] == "Balanced 60/40")
    symbols = [h["symbol"] for h in portfolio["holdings"]]
    assert symbols == ["VTI", "BND"]
    assert [h["weight"] for h in portfolio["holdings"]] == pytest.approx([0.6, 0.4])
    assert portfolio["note"] is None


def test_balanced_substitutes_lowest_volatility_when_no_bond(db, monkeypatch):
    no_bond = {
        symbol: info
        for symbol, info in catalog_by_symbol().items()
        if "bond" not in (info["sector"] or "").lower() and symbol not in {"BND", "TLT"}
    }
    monkeypatch.setattr(seed_demo_module, "catalog_by_symbol", lambda: no_bond)
    _seed_catalog(db, list(no_bond.values()))

    rows = _monthly_close_rows()
    _seed_prices(db, ["SPY", "VOO", "VTI"], rows)
    calm = [(d, 100.0, 1_000_000) for d, _, _ in rows]
    price_dao.upsert_daily_prices(db, ticker_dao.get_ticker(db, "SPY")["id"], calm)
    db.commit()

    results = seed_demo(db)
    portfolio = next(r for r in results if r["name"] == "Balanced 60/40")
    symbols = [h["symbol"] for h in portfolio["holdings"]]
    assert symbols == ["VTI", "SPY"]  # SPY = lowest volatility, not VTI/VOO
    assert portfolio["note"] is not None
    assert "SPY" in portfolio["note"]


def test_every_holding_resolves_to_real_ticker_with_price_history(db):
    _seed_catalog(db)
    _seed_prices(db, ["VXUS", "VTI", "BND", "QQQ"], _monthly_close_rows())

    results = seed_demo(db)

    for result in results:
        assert result["holdings"], f"{result['name']} has no holdings"
        for holding in result["holdings"]:
            ticker = ticker_dao.get_ticker(db, holding["symbol"])
            assert ticker is not None, f"{holding['symbol']} not in tickers table"
            assert holding["name"] == ticker["name"]
            history = price_dao.get_price_history(db, ticker["id"])
            assert history, f"{holding['symbol']} has no stored price history"


# ---------------------------------------------------------------------------
# Simulation regression guard: the seeded portfolios must still simulate to the
# same statistics they did before the percent -> fraction change.
# ---------------------------------------------------------------------------

def test_seeded_portfolios_simulate_to_sane_probabilities(seeded_client):
    """Every seeded portfolio produces a plausible probability of profit.

    A wrong-scale weight does not error -- the engine renormalizes -- it just
    returns a different portfolio's numbers. A real portfolio over a series
    with genuine drawdowns sits strictly inside (0, 1); 0.0 or 1.0 means the
    weights are degenerate, and NaN means they are not numbers.
    """
    client, results = seeded_client

    for result in results:
        response = client.post(
            f"/portfolios/{result['id']}/simulate", json=SIMULATE_BODY
        )
        assert response.status_code == 200, response.text
        stats = response.json()["stats"]
        pop = stats["probability_of_profit"]
        assert not math.isnan(pop), f"{result['name']}: NaN probability_of_profit"
        assert 0.0 < pop < 1.0, f"{result['name']}: probability_of_profit={pop}"
        assert math.isfinite(stats["median_max_drawdown"])


def test_seeded_balanced_portfolio_matches_the_same_weights_posted_by_hand(seeded_client):
    """The seeded 60/40 must simulate identically to a hand-built 0.6/0.4.

    This is the direct statement of "same stats as before the change": it
    compares the seeder against the API's own fraction contract using a fixed
    seed, so it passes only if the seeder writes the weights the contract
    expects. Had it written 60/40, the seeded run would renormalize to 50/50
    and disagree with the hand-built one.
    """
    client, results = seeded_client
    seeded = next(r for r in results if r["name"] == "Balanced 60/40")

    hand_built = client.post(
        "/portfolios",
        json={
            "name": "Hand-built 60/40",
            "monthly_contribution": 100.0,
            "holdings": [
                {"symbol": "VTI", "weight": 0.6},
                {"symbol": "BND", "weight": 0.4},
            ],
        },
    )
    assert hand_built.status_code == 201, hand_built.text
    hand_id = hand_built.json()["id"]

    seeded_stats = client.post(
        f"/portfolios/{seeded['id']}/simulate", json=SIMULATE_BODY
    ).json()["stats"]
    hand_stats = client.post(
        f"/portfolios/{hand_id}/simulate", json=SIMULATE_BODY
    ).json()["stats"]

    assert seeded_stats["probability_of_profit"] == hand_stats["probability_of_profit"]
    assert seeded_stats["final_percentiles"] == hand_stats["final_percentiles"]
    assert seeded_stats["median_max_drawdown"] == hand_stats["median_max_drawdown"]


def test_stored_seed_weights_are_fractions_over_http(seeded_client):
    """The API serves seeded weights as fractions, so the UI can render them."""
    client, results = seeded_client

    for result in results:
        detail = client.get(f"/portfolios/{result['id']}").json()
        weights = [h["weight"] for h in detail["holdings"]]
        assert all(0.0 < w <= 1.0 for w in weights), (result["name"], weights)
        assert sum(weights) == pytest.approx(1.0), result["name"]

    balanced = client.get(f"/portfolios/{results[1]['id']}").json()
    assert {h["symbol"]: h["weight"] for h in balanced["holdings"]} == {
        "VTI": 0.6,
        "BND": 0.4,
    }