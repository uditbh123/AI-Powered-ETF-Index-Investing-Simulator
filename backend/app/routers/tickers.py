"""Available tickers endpoint (Phase 1 data, exposed for the UI)."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from ..dao import prices as price_dao
from ..dao import tickers as ticker_dao
from ..deps import get_db
from ..schemas import TickerOut

router = APIRouter(tags=["tickers"])


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