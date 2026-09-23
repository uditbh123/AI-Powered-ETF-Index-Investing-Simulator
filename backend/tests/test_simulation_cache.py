"""Regression tests: simulation cache must invalidate when prices change.

Stored adjusted closes are rewritten on every daily ingest, so the monthly
return series the engine bootstraps from can change even when all parameters
are identical. The cache key therefore carries a fingerprint of the return
series; parameter equality alone must never serve a stale run.
"""
import pytest

from app.dao import portfolios as portfolio_dao
from app.dao import prices as price_dao
from app.dao import tickers as ticker_dao
from app.services.simulation import run_portfolio_simulation

_KWARGS = dict(initial_balance=10_000.0, horizon_months=36, n_simulations=200, seed=7)


def _seed_portfolio(db) -> int:
    user_id = portfolio_dao.get_or_create_user(db)
    ticker = ticker_dao.get_or_create_ticker(
        db, "SPY", name="SPDR S&P 500 ETF", sector="Equity"
    )
    rows = [
        ("2023-01-31", 100.0, 1_000_000),
        ("2023-02-28", 101.0, 1_000_000),
        ("2023-03-31", 103.0, 1_000_000),
        ("2023-04-28", 104.0, 1_000_000),
        ("2023-05-31", 106.0, 1_000_000),
    ]
    price_dao.upsert_daily_prices(db, ticker["id"], rows)
    portfolio_id = portfolio_dao.create_portfolio(
        db, user_id, name="Single ETF", monthly_contribution=100.0
    )
    portfolio_dao.add_holding(db, portfolio_id, ticker["id"], 1.0)
    db.commit()
    return portfolio_id


def test_identical_params_reuse_cached_run(db):
    pid = _seed_portfolio(db)
    first = run_portfolio_simulation(db, pid, **_KWARGS)
    second = run_portfolio_simulation(db, pid, **_KWARGS)

    assert first["cached"] is False
    assert second["cached"] is True
    assert second["run_id"] == first["run_id"]


def test_new_price_row_for_holding_invalidates_cache(db):
    pid = _seed_portfolio(db)
    first = run_portfolio_simulation(db, pid, **_KWARGS)
    assert first["cached"] is False

    # Simulate the daily ingest adding one new trading day for a holding.
    ticker = ticker_dao.get_ticker(db, "SPY")
    price_dao.upsert_daily_prices(
        db, ticker["id"], [("2023-06-30", 108.0, 1_000_000)]
    )
    db.commit()

    rerun = run_portfolio_simulation(db, pid, **_KWARGS)
    assert rerun["cached"] is False
    assert rerun["run_id"] != first["run_id"]


def test_rewritten_close_for_holding_invalidates_cache(db):
    """A changed adjusted close (not just a new date) must also invalidate."""
    pid = _seed_portfolio(db)
    first = run_portfolio_simulation(db, pid, **_KWARGS)

    ticker = ticker_dao.get_ticker(db, "SPY")
    price_dao.upsert_daily_prices(
        db, ticker["id"], [("2023-05-31", 100.0, 1_000_000)]  # basis changed
    )
    db.commit()

    rerun = run_portfolio_simulation(db, pid, **_KWARGS)
    assert rerun["cached"] is False
    assert rerun["run_id"] != first["run_id"]