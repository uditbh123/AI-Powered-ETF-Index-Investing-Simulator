"""Seed three demo portfolios attached to a "Demo User".

Idempotent: portfolios are keyed by (user, name), so re-running creates no
duplicates and leaves existing rows untouched.

Usage (from backend/):
    python -m app.scripts.seed_demo
"""
from __future__ import annotations

import sys

from app.dao import portfolios as portfolio_dao
from app.dao import prices as price_dao
from app.dao import tickers as ticker_dao
from app.data.ticker_catalog import TickerInfo, catalog_by_symbol
from app.database import get_connection, init_db
from app.services.market_data import seed_catalog

DEMO_USER_NAME = "Demo User"

# "Balanced 60/40" split: ~60% equity / 40% bond ETF. The bond leg falls back
# to the lowest-volatility catalog ticker when no bond ETF is available.
BALANCED_EQUITY = "VTI"
BALANCED_EQUITY_WEIGHT = 60.0
BALANCED_BOND_WEIGHT = 40.0

# Known bond ETFs (catalog also often flags them via sector == "... Bonds").
_BOND_SYMBOLS = {"BND", "TLT", "SHY", "AGG", "GOVT"}


def _catalog_bond_symbol(catalog: dict[str, TickerInfo]) -> str | None:
    for info in catalog.values():
        sector = (info.get("sector") or "").lower()
        if info["symbol"] in _BOND_SYMBOLS or "bond" in sector:
            return info["symbol"]
    return None


def _lowest_volatility_symbol(
    conn, catalog: dict[str, TickerInfo], exclude: set[str]
) -> str:
    """Pick the catalog ticker with the lowest annualized volatility.

    Requires at least 30 stored daily closes (mirrors the screener's floor).
    ``exclude`` prevents substituting a ticker already used elsewhere in the
    same portfolio (e.g. the equity leg).
    """
    import numpy as np

    best: str | None = None
    best_vol = None
    for info in catalog.values():
        symbol = info["symbol"]
        if symbol in exclude:
            continue
        ticker = ticker_dao.get_ticker(conn, symbol)
        if ticker is None:
            continue
        closes = [float(r["close"]) for r in price_dao.get_price_history(conn, ticker["id"])]
        if len(closes) < 30:
            continue
        diffs = np.diff(closes) / np.asarray(closes[:-1])
        vol = float(np.std(diffs, ddof=1) * (252 ** 0.5))
        if best_vol is None or vol < best_vol:
            best_vol = vol
            best = symbol
    if best is None:
        raise ValueError(
            "no bond ETF in catalog and no ticker with >=30 closes to "
            "substitute for 'Balanced 60/40'"
        )
    return best


def _demo_specs(conn) -> list[dict]:
    """Build the three demo portfolio specs, resolving the bond leg."""
    catalog = catalog_by_symbol()
    bond = _catalog_bond_symbol(catalog)
    note = None
    if bond is None:
        bond = _lowest_volatility_symbol(conn, catalog, exclude={BALANCED_EQUITY})
        note = (
            f"no bond ETF in catalog — substituted the lowest-volatility "
            f"ticker {bond} for the 40% bond leg"
        )
    return [
        {
            "name": "All-World Growth",
            "monthly_contribution": 200.0,
            "holdings": [("VXUS", 100.0)],
            "note": None,
        },
        {
            "name": "Balanced 60/40",
            "monthly_contribution": 100.0,
            "holdings": [(BALANCED_EQUITY, BALANCED_EQUITY_WEIGHT), (bond, BALANCED_BOND_WEIGHT)],
            "note": note,
        },
        {
            "name": "Tech Tilt",
            "monthly_contribution": 200.0,
            "holdings": [("QQQ", 70.0), ("VXUS", 30.0)],
            "note": None,
        },
    ]


def _resolve_holdings(conn, holdings: list[tuple[str, float]]) -> list[dict]:
    resolved = []
    for symbol, weight in holdings:
        ticker = ticker_dao.get_ticker(conn, symbol)
        if ticker is None:
            raise ValueError(
                f"symbol '{symbol}' is not in the tickers table; seed the "
                "catalog first (python -m app.scripts.ingest or seed_catalog)"
            )
        resolved.append({"ticker_id": int(ticker["id"]), "symbol": symbol, "weight": weight})
    return resolved


def _summary(conn, portfolio_id: int, spec: dict, created: bool) -> dict:
    holdings = []
    for row in portfolio_dao.list_holdings(conn, portfolio_id):
        holdings.append(
            {
                "symbol": row["symbol"],
                "name": row["name"],
                "weight": float(row["weight"]),
            }
        )
    return {
        "id": int(portfolio_id),
        "name": spec["name"],
        "monthly_contribution": float(spec["monthly_contribution"]),
        "holdings": holdings,
        "created": created,
        "note": spec.get("note"),
    }


def seed_demo(conn) -> list[dict]:
    """Create the demo portfolios for "Demo User". Idempotent by name.

    Returns a summary dict per portfolio (id, holdings, weights, created).
    Caller commits.
    """
    user_id = portfolio_dao.get_or_create_user(conn, DEMO_USER_NAME)
    results = []
    for spec in _demo_specs(conn):
        existing = portfolio_dao.get_portfolio_by_user_and_name(conn, user_id, spec["name"])
        if existing is not None:
            results.append(_summary(conn, existing["id"], spec, created=False))
            continue
        resolved = _resolve_holdings(conn, spec["holdings"])
        portfolio_id = portfolio_dao.create_portfolio(
            conn,
            user_id=user_id,
            name=spec["name"],
            monthly_contribution=spec["monthly_contribution"],
        )
        for holding in resolved:
            portfolio_dao.add_holding(conn, portfolio_id, holding["ticker_id"], holding["weight"])
        results.append(_summary(conn, portfolio_id, spec, created=True))
    conn.commit()
    return results


def main(argv: list[str] | None = None) -> int:
    init_db()
    seed_catalog()
    conn = get_connection()
    try:
        results = seed_demo(conn)
    finally:
        conn.close()

    for r in results:
        status = "created" if r["created"] else "already exists"
        contribution = f"{r['monthly_contribution']:.0f}"
        print(f"[{status}] #{r['id']}  {r['name']}  (${contribution}/mo)")
        for h in r["holdings"]:
            print(f"    {h['symbol']:<6} {h['weight']:.0f}%  {h['name']}")
        if r.get("note"):
            print(f"    note: {r['note']}")
    print(f"\nDemo user: {DEMO_USER_NAME} — {len(results)} portfolios.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "DEMO_USER_NAME",
    "seed_demo",
]