"""Portfolio configuration endpoints."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..dao import portfolios as portfolio_dao
from ..dao import tickers as ticker_dao
from ..deps import get_db
from ..schemas import PortfolioCreate, PortfolioOut
from ..services.simulation import portfolio_monthly_returns_with_dates

router = APIRouter(tags=["portfolios"])


@router.post("/portfolios", response_model=PortfolioOut, status_code=201)
def create_portfolio(
    payload: PortfolioCreate,
    conn: sqlite3.Connection = Depends(get_db),
) -> PortfolioOut:
    user_id = portfolio_dao.get_or_create_user(conn)
    holdings = []
    for holding in payload.holdings:
        ticker = ticker_dao.get_ticker(conn, holding.symbol.upper())
        if ticker is None:
            raise HTTPException(
                status_code=404,
                detail=f"ticker '{holding.symbol}' not in catalog",
            )
        holdings.append({"id": ticker["id"], "weight": holding.weight, "symbol": ticker["symbol"]})

    portfolio_id = portfolio_dao.create_portfolio(
        conn,
        user_id=user_id,
        name=payload.name,
        monthly_contribution=payload.monthly_contribution,
    )
    for h in holdings:
        portfolio_dao.add_holding(conn, portfolio_id, h["id"], h["weight"])
    conn.commit()

    return PortfolioOut(
        id=portfolio_id,
        name=payload.name,
        monthly_contribution=payload.monthly_contribution,
        holdings=[{"symbol": h["symbol"], "weight": h["weight"]} for h in holdings],
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