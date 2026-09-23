"""ETF screener endpoint: per-ticker stats computed from stored closes."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from ..dao import prices as price_dao
from ..dao import tickers as ticker_dao
from ..deps import get_db
from ..schemas import ScreenerOut
from ..services.screener import compute_screener_stats

router = APIRouter(tags=["screener"])


@router.get("/screener", response_model=list[ScreenerOut])
def get_etf_screener(
    conn: sqlite3.Connection = Depends(get_db),
) -> list[ScreenerOut]:
    """Screen every tracked ticker that has local price history.

    All figures are recomputed on the fly from the stored daily closes (pandas;
    no network). Only tickers with at least one price row appear. Sorted by
    symbol.

    KNOWN LIMITATION: every metric derives from the stored Close column, which
    Yahoo serves on the adjustment basis of the most recent download. The exact
    basis used is under review (see ``docs/data_methodology.md``). Because the
    close is a price, income metrics such as the 1-year total return exclude
    dividend reinvestment and may understate a dividend payer's true return.
    """
    out: list[ScreenerOut] = []
    for row in ticker_dao.list_tickers(conn):
        price_rows = price_dao.get_price_history(conn, row["id"])
        if not price_rows:
            continue
        stats = compute_screener_stats(
            [p["date"] for p in price_rows],
            [float(p["close"]) for p in price_rows],
        )
        out.append(
            ScreenerOut(
                symbol=row["symbol"],
                name=row["name"],
                sector=row["sector"],
                **stats,
            )
        )
    out.sort(key=lambda s: s.symbol)
    return out