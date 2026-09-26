"""Seed three demo portfolios attached to a "Demo User".

Weights follow the app-wide convention: FRACTIONS summing to 1.0 (0.6 is 60%),
which is what ``PortfolioCreate``/``PortfolioUpdate`` accept and what
``portfolio_monthly_returns`` consumes. This script writes them directly, so it
is the one place that had to change when the API tightened from the interim
``<= 100`` percent cap to the fraction convention.

Upserts by (user, name): a re-run creates missing portfolios and *repairs*
existing ones, rewriting stale holdings left over from an earlier seed. That
matters because a database seeded by an older revision holds percent-scale
weights (100/60/40) that the API would now reject, and those rows are exactly
what a fresh `python -m app.scripts.seed_demo` should repair.

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
BALANCED_EQUITY_WEIGHT = 0.6
BALANCED_BOND_WEIGHT = 0.4

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
            "holdings": [("VXUS", 1.0)],
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
            "holdings": [("QQQ", 0.7), ("VXUS", 0.3)],
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


def _summary(conn, portfolio_id: int, spec: dict, created: bool, repaired: bool) -> dict:
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
        "repaired": repaired,
        "note": spec.get("note"),
    }


def _stored_signature(conn, portfolio_id: int, resolved: list[dict], contribution: float) -> tuple:
    """What the DB currently holds, for deciding whether a repair is needed."""
    stored = portfolio_dao.list_holdings(conn, portfolio_id)
    stored_weights = [
        (row["ticker_id"], float(row["weight"])) for row in stored
    ]
    target_weights = [(h["ticker_id"], float(h["weight"])) for h in resolved]
    row = portfolio_dao.get_portfolio(conn, portfolio_id)
    return (
        float(row["monthly_contribution"] if row else contribution) == float(contribution),
        stored_weights == target_weights,
    )


def seed_demo(conn) -> list[dict]:
    """Upsert the demo portfolios for "Demo User", keyed by (user, name).

    Returns a summary dict per portfolio (id, holdings, weights, created,
    repaired). Caller commits. A portfolio that already exists with the
    intended scalars and fraction weights is left alone; one that does not
    (an older percent-scale seed, a hand-edited row) has its holdings
    replaced and is reported as ``repaired``.
    """
    user_id = portfolio_dao.get_or_create_user(conn, DEMO_USER_NAME)
    results = []
    for spec in _demo_specs(conn):
        resolved = _resolve_holdings(conn, spec["holdings"])
        existing = portfolio_dao.get_portfolio_by_user_and_name(conn, user_id, spec["name"])

        if existing is None:
            portfolio_id = portfolio_dao.create_portfolio(
                conn,
                user_id=user_id,
                name=spec["name"],
                monthly_contribution=spec["monthly_contribution"],
            )
            for holding in resolved:
                portfolio_dao.add_holding(
                    conn, portfolio_id, holding["ticker_id"], holding["weight"]
                )
            results.append(_summary(conn, portfolio_id, spec, created=True, repaired=False))
            continue

        portfolio_id = existing["id"]
        contribution_ok, weights_ok = _stored_signature(
            conn, portfolio_id, resolved, spec["monthly_contribution"]
        )
        repaired = not (contribution_ok and weights_ok)
        if repaired:
            portfolio_dao.update_portfolio(
                conn,
                portfolio_id,
                name=spec["name"],
                monthly_contribution=spec["monthly_contribution"],
            )
            portfolio_dao.delete_holdings(conn, portfolio_id)
            for holding in resolved:
                portfolio_dao.add_holding(
                    conn, portfolio_id, holding["ticker_id"], holding["weight"]
                )
        results.append(
            _summary(conn, portfolio_id, spec, created=False, repaired=repaired)
        )
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
        if r["created"]:
            status = "created"
        elif r["repaired"]:
            status = "repaired"
        else:
            status = "unchanged"
        contribution = f"{r['monthly_contribution']:.0f}"
        print(f"[{status}] #{r['id']}  {r['name']}  (${contribution}/mo)")
        for h in r["holdings"]:
            # Stored as a fraction; shown as the percent a person expects.
            print(f"    {h['symbol']:<6} {h['weight']:.1%}  {h['name']}")
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