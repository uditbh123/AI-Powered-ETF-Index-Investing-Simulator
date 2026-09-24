"""Tests for the demo-data seeding script (app/scripts/seed_demo.py)."""
from __future__ import annotations

import pytest

from app.dao import portfolios as portfolio_dao
from app.dao import prices as price_dao
from app.dao import tickers as ticker_dao
from app.data.ticker_catalog import DEFAULT_TICKERS, catalog_by_symbol
from app.scripts import seed_demo as seed_demo_module
from app.scripts.seed_demo import DEMO_USER_NAME, seed_demo

EXPECTED_NAMES = ["All-World Growth", "Balanced 60/40", "Tech Tilt"]


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


def _seed_catalog(conn, catalog: list | None = None) -> None:
    ticker_dao.upsert_catalog(conn, catalog or list(DEFAULT_TICKERS))
    conn.commit()


def _seed_prices(conn, symbols: list[str], rows: list[tuple[str, float, int]]) -> None:
    for symbol in symbols:
        ticker = ticker_dao.get_ticker(conn, symbol)
        assert ticker is not None, f"catalog missing {symbol}"
        price_dao.upsert_daily_prices(conn, ticker["id"], rows)
    conn.commit()


def test_seed_demo_is_idempotent(db):
    _seed_catalog(db)

    first = seed_demo(db)
    second = seed_demo(db)

    assert [r["name"] for r in first] == EXPECTED_NAMES
    assert all(r["created"] for r in first)
    assert not any(r["created"] for r in second)
    assert [r["id"] for r in first] == [r["id"] for r in second]

    user_id = portfolio_dao.get_or_create_user(db, DEMO_USER_NAME)
    portfolios = db.execute(
        "SELECT * FROM portfolios WHERE user_id = ?", (user_id,)
    ).fetchall()
    assert [p["name"] for p in portfolios] == EXPECTED_NAMES

    for r in first:
        assert sum(h["weight"] for h in r["holdings"]) == pytest.approx(100.0)
        assert len(r["holdings"]) >= 1


def test_all_world_growth_is_single_global_equity_etf(db):
    _seed_catalog(db)
    results = seed_demo(db)
    portfolio = next(r for r in results if r["name"] == "All-World Growth")
    assert portfolio["monthly_contribution"] == 200.0
    assert portfolio["holdings"] == [
        {"symbol": "VXUS", "name": "Vanguard Total International Stock ETF", "weight": 100.0}
    ]


def test_balanced_uses_bond_etf_when_catalog_has_one(db):
    _seed_catalog(db)
    results = seed_demo(db)
    portfolio = next(r for r in results if r["name"] == "Balanced 60/40")
    symbols = [h["symbol"] for h in portfolio["holdings"]]
    assert symbols == ["VTI", "BND"]
    assert [h["weight"] for h in portfolio["holdings"]] == [60.0, 40.0]
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