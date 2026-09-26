"""Available tickers endpoint (Phase 1 data, exposed for the UI)."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from ..dao import prices as price_dao
from ..dao import tickers as ticker_dao
from ..deps import get_db
from ..schemas import MAX_SYMBOL_LENGTH, PricePoint, TickerOut, TickerPricesOut

router = APIRouter(tags=["tickers"])

#: Rows returned when the caller does not ask for a specific window. Matches the
#: per-request maximum, so the series a caller can pull is always bounded: the
#: full history of a 25-year daily ETF is ~6,300 rows, and the SPA's chart wants
#: everything it can get (it slices client-side by range).
DEFAULT_PRICE_LIMIT = 10_000


@router.get("/tickers", response_model=list[TickerOut])
def list_tickers(conn: sqlite3.Connection = Depends(get_db)) -> list[TickerOut]:
    out: list[TickerOut] = []
    for row in ticker_dao.list_tickers(conn):
        first = conn.execute(
            "SELECT MIN(date) AS d FROM prices WHERE ticker_id = ?", (row["id"],)
        ).fetchone()
        last = conn.execute(
            "SELECT MAX(date) AS d FROM prices WHERE ticker_id = ?", (row["id"],)
        ).fetchone()
        out.append(
            TickerOut(
                symbol=row["symbol"],
                name=row["name"],
                sector=row["sector"],
                price_rows=price_dao.count_prices(conn, ticker_id=row["id"]),
                first_date=first["d"] if first["d"] else None,
                last_date=last["d"] if last["d"] else None,
            )
        )
    return out


@router.get("/tickers/{symbol}/prices", response_model=TickerPricesOut)
def get_ticker_prices(
    symbol: str = Path(..., max_length=MAX_SYMBOL_LENGTH),
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(default=DEFAULT_PRICE_LIMIT, ge=1, le=DEFAULT_PRICE_LIMIT),
    conn: sqlite3.Connection = Depends(get_db),
) -> TickerPricesOut:
    """Historical daily closes for one ticker, ordered oldest -> newest.

    Returns at most ``DEFAULT_PRICE_LIMIT`` rows (the most recent ones, still in
    ascending date order) so the response is always bounded. ``symbol`` is
    length-capped so a multi-kilobyte path segment cannot be echoed back inside
    the 404 detail.
    """
    ticker = ticker_dao.get_ticker(conn, symbol.upper())
    if ticker is None:
        raise HTTPException(status_code=404, detail=f"ticker '{symbol}' not found")

    rows = price_dao.get_price_history(
        conn, ticker["id"], start=start, end=end, limit=limit
    )
    return TickerPricesOut(
        symbol=ticker["symbol"],
        name=ticker["name"],
        sector=ticker["sector"],
        prices=[
            PricePoint(date=row["date"], close=row["close"], volume=row["volume"])
            for row in rows
        ],
    )