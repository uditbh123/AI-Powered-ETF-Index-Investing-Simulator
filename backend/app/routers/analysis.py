"""In-depth ETF analysis endpoint for the detail page.

Companion to ``GET /screener`` (``app/routers/screener.py``): the screener
returns one flat row per ticker for the sortable table, this endpoint returns
everything a single ETF's detail page needs -- key stats, trailing returns,
year-by-month return grid, daily-return histogram, drawdown series and a
correlation matrix against every other tracked ticker.

All figures are recomputed on the fly from the stored daily closes with pandas
(pure ``app.services.analysis``; no network).
"""
from __future__ import annotations

import sqlite3

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Path

from ..dao import prices as price_dao
from ..dao import tickers as ticker_dao
from ..deps import get_db
from ..schemas import MAX_SYMBOL_LENGTH, EtfAnalysisOut
from ..services.analysis import compute_analysis

router = APIRouter(tags=["analysis"])


def _daily_series(conn: sqlite3.Connection, ticker_id: int) -> pd.Series | None:
    """Close series (indexed by date) for one ticker, or None with no history."""
    rows = price_dao.get_price_history(conn, ticker_id)
    if not rows:
        return None
    return pd.Series(
        data=[float(r["close"]) for r in rows],
        index=pd.to_datetime([r["date"] for r in rows]),
        dtype=float,
    ).sort_index()


def _all_daily_series(conn: sqlite3.Connection) -> dict[str, pd.Series]:
    """Every ticker's close series, for the correlation matrix. Symbols as keys."""
    out: dict[str, pd.Series] = {}
    for row in ticker_dao.list_tickers(conn):
        series = _daily_series(conn, row["id"])
        if series is not None:
            out[row["symbol"]] = series
    return out


@router.get("/tickers/{symbol}/analysis", response_model=EtfAnalysisOut)
def get_ticker_analysis(
    symbol: str = Path(..., max_length=MAX_SYMBOL_LENGTH),
    conn: sqlite3.Connection = Depends(get_db),
) -> EtfAnalysisOut:
    """Full in-depth analysis for one tracked ticker, computed from stored closes.

    404 only when the ticker is not in the catalog. A ticker that exists but has
    no stored price history returns an empty payload (``stats`` null and empty
    series) rather than an error, matching ``/tickers/{symbol}/prices``.

    The correlation matrix is built against every other tracked ticker that has
    history, using up to 36 overlapping months of monthly returns; cells with
    fewer than 6 overlapping months are null. ``symbol`` is length-capped so a
    multi-kilobyte path segment cannot be echoed back inside the 404 detail.
    """
    ticker = ticker_dao.get_ticker(conn, symbol.upper())
    if ticker is None:
        raise HTTPException(status_code=404, detail=f"ticker '{symbol}' not found")

    series = _daily_series(conn, ticker["id"])
    all_series = _all_daily_series(conn) if series is not None else {}
    if series is not None:
        # Ensure the subject's own series is present under its symbol.
        all_series.setdefault(ticker["symbol"], series)

    dates = [d.strftime("%Y-%m-%d") for d in series.index] if series is not None else []
    closes = series.to_list() if series is not None else []

    payload = compute_analysis(
        symbol=ticker["symbol"],
        name=ticker["name"],
        sector=ticker["sector"],
        dates=dates,
        closes=closes,
        all_ticker_series=all_series if all_series else None,
    )
    return EtfAnalysisOut(**payload)
