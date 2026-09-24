"""Portfolio configuration endpoints."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..dao import portfolios as portfolio_dao
from ..dao import tickers as ticker_dao
from ..deps import get_db
from ..schemas import HoldingIn, PortfolioCreate, PortfolioOut, PortfolioUpdate
from ..services.simulation import portfolio_monthly_returns_with_dates

router = APIRouter(tags=["portfolios"])


def _resolve_holdings(
    conn: sqlite3.Connection, holdings: list[HoldingIn]
) -> list[dict[str, object]]:
    """Map payload holdings to catalog rows; raises 404 for unknown tickers.

    Mirrors the create endpoint's lookup so PATCH and POST share behavior.
    """
    resolved = []
    for holding in holdings:
        ticker = ticker_dao.get_ticker(conn, holding.symbol.upper())
        if ticker is None:
            raise HTTPException(
                status_code=404,
                detail=f"ticker '{holding.symbol}' not in catalog",
            )
        resolved.append(
            {"id": ticker["id"], "weight": holding.weight, "symbol": ticker["symbol"]}
        )
    return resolved


@router.post("/portfolios", response_model=PortfolioOut, status_code=201)
def create_portfolio(
    payload: PortfolioCreate,
    conn: sqlite3.Connection = Depends(get_db),
) -> PortfolioOut:
    user_id = portfolio_dao.get_or_create_user(conn)
    holdings = _resolve_holdings(conn, payload.holdings)

    portfolio_id = portfolio_dao.create_portfolio(
        conn,
        user_id=user_id,
        name=payload.name,
        monthly_contribution=payload.monthly_contribution,
    )
    for h in holdings:
        portfolio_dao.add_holding(conn, portfolio_id, h["id"], h["weight"])
    conn.commit()

    created_at = portfolio_dao.get_portfolio(conn, portfolio_id)["created_at"]
    return PortfolioOut(
        id=portfolio_id,
        name=payload.name,
        monthly_contribution=payload.monthly_contribution,
        holdings=[{"symbol": h["symbol"], "weight": h["weight"]} for h in holdings],
        created_at=created_at,
    )


@router.patch("/portfolios/{portfolio_id}", response_model=PortfolioOut)
def update_portfolio(
    portfolio_id: int,
    payload: PortfolioUpdate,
    conn: sqlite3.Connection = Depends(get_db),
) -> PortfolioOut:
    """Full holdings replacement update, applied in one transaction.

    Unequivocally 404s for a missing portfolio (checked before any write) and
    for unknown tickers (raised before commit, so a failed replacement leaves
    the existing holdings untouched). The weight-sum rule lives in
    ``PortfolioUpdate`` -> 422.
    """
    if portfolio_dao.get_portfolio(conn, portfolio_id) is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    holdings = _resolve_holdings(conn, payload.holdings)

    portfolio_dao.update_portfolio(
        conn,
        portfolio_id,
        name=payload.name,
        monthly_contribution=payload.monthly_contribution,
    )
    portfolio_dao.delete_holdings(conn, portfolio_id)
    for h in holdings:
        portfolio_dao.add_holding(conn, portfolio_id, h["id"], h["weight"])
    conn.commit()

    created_at = portfolio_dao.get_portfolio(conn, portfolio_id)["created_at"]
    return PortfolioOut(
        id=portfolio_id,
        name=payload.name,
        monthly_contribution=payload.monthly_contribution,
        holdings=[{"symbol": h["symbol"], "weight": h["weight"]} for h in holdings],
        created_at=created_at,
    )


@router.get("/portfolios", response_model=list[PortfolioOut])
def list_portfolios(conn: sqlite3.Connection = Depends(get_db)) -> list[PortfolioOut]:
    out: list[PortfolioOut] = []
    for row in portfolio_dao.list_portfolios(conn):
        holdings = portfolio_dao.list_holdings(conn, row["id"])
        out.append(
            PortfolioOut(
                id=row["id"],
                name=row["name"],
                monthly_contribution=row["monthly_contribution"],
                holdings=[{"symbol": h["symbol"], "weight": h["weight"]} for h in holdings],
                created_at=row["created_at"],
            )
        )
    return out


@router.get("/portfolios/{portfolio_id}", response_model=PortfolioOut)
def get_portfolio(
    portfolio_id: int,
    conn: sqlite3.Connection = Depends(get_db),
) -> PortfolioOut:
    row = portfolio_dao.get_portfolio(conn, portfolio_id)
    if row is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    holdings = portfolio_dao.list_holdings(conn, portfolio_id)
    return PortfolioOut(
        id=row["id"],
        name=row["name"],
        monthly_contribution=row["monthly_contribution"],
        holdings=[{"symbol": h["symbol"], "weight": h["weight"]} for h in holdings],
        created_at=row["created_at"],
    )


@router.get("/portfolios/{portfolio_id}/monthly-returns")
def get_portfolio_monthly_returns(
    portfolio_id: int,
    conn: sqlite3.Connection = Depends(get_db),
) -> list[dict]:
    """Return the portfolio's realized monthly returns as {year, month, return}.

    Year/month are the calendar period of each month-end return; ``return`` is
    the weighted portfolio return for that month (see
    :func:`portfolio_monthly_returns_with_dates`). Raises 404 for a missing
    portfolio and 400 when there is not enough overlapping history.
    """
    row = portfolio_dao.get_portfolio(conn, portfolio_id)
    if row is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    holdings = portfolio_dao.list_holdings(conn, portfolio_id)
    if not holdings:
        raise HTTPException(status_code=400, detail="portfolio has no holdings")
    try:
        dates, returns = portfolio_monthly_returns_with_dates(conn, holdings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [
        {
            "year": int(date[:4]),
            "month": int(date[5:7]),
            "return": round(float(value), 6),
        }
        for date, value in zip(dates, returns, strict=True)
    ]


@router.delete("/portfolios/{portfolio_id}", status_code=204)
def delete_portfolio(
    portfolio_id: int,
    conn: sqlite3.Connection = Depends(get_db),
) -> None:
    """Delete a portfolio and all of its runs, results, and holdings."""
    if not portfolio_dao.delete_portfolio(conn, portfolio_id):
        raise HTTPException(status_code=404, detail="portfolio not found")
    conn.commit()