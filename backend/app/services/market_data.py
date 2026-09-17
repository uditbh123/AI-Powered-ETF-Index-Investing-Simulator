"""Orchestrates fetching historical closes via yfinance and persisting them.

Design notes:
- yfinance is imported lazily inside functions so the API server still boots
  even if the optional data provider is unavailable.
- ``refresh_ticker`` accepts an injectable ``fetcher`` so tests can substitute
  a fake DataFrame without hitting the network.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

import pandas as pd

from ..config import settings
from ..dao import prices as price_dao
from ..dao import tickers as ticker_dao
from ..data.ticker_catalog import DEFAULT_TICKERS, TickerInfo
from ..database import get_connection

# Types: a fetcher is (symbol, start, end) -> pandas.DataFrame
Fetcher = Callable[[str, str | None, str | None], pd.DataFrame]


def fetch_history(
    symbol: str,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Download daily OHLCV history for a single symbol via yfinance.

    With no explicit start date, requests the full available history: yfinance
    defaults to only one month when both period and start are omitted, so we
    explicitly pass ``period="max"``.
    """
    import yfinance as yf  # lazy: keep yfinance optional at import time

    if start is None:
        return yf.download(
            symbol,
            period="max",
            end=end,
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False,
        )
    return yf.download(
        symbol,
        start=start,
        end=end,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
    )


def _extract_series(frame: pd.DataFrame, symbol: str, field: str) -> pd.Series:
    """Pull a single field out of a yfinance download result.

    yfinance attaches a MultiIndex of (Price, Ticker) columns to every result
    these days, but older versions return flat columns for single tickers.
    """
    series: Any = frame[field]
    if isinstance(series, pd.DataFrame):
        if symbol in series.columns:
            series = series[symbol]
        else:
            series = series.iloc[:, 0]
    return series


def history_to_rows(
    frame: pd.DataFrame,
    symbol: str,
) -> list[tuple[str, float, int | None]]:
    """Convert a yfinance history frame into (date, close, volume) tuples.

    Rows whose close is missing/NaN are dropped; a missing volume becomes None
    (the prices.volume column is nullable).
    """
    if frame is None or frame.empty:
        return []

    close = _extract_series(frame, symbol, "Close")
    volume = _extract_series(frame, symbol, "Volume")

    rows: list[tuple[str, float, int | None]] = []
    for ts, close_value in close.items():
        if close_value is None or not math.isfinite(float(close_value)):
            continue
        vol_raw = volume.get(ts)
        if hasattr(ts, "tz") and getattr(getattr(ts, "tz", None), "utcoffset", None):
            ts = ts.tz_localize(None)
        date = ts.strftime("%Y-%m-%d")
        vol: int | None = None
        if vol_raw is not None and not (isinstance(vol_raw, float) and math.isnan(vol_raw)):
            vol = int(vol_raw)
        rows.append((date, float(close_value), vol))
    return rows


def refresh_ticker(
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    fetcher: Fetcher = fetch_history,
) -> dict[str, Any]:
    """Fetch and store full price history for one symbol. Never raises."""
    conn = get_connection()
    try:
        meta = {t["symbol"]: t for t in DEFAULT_TICKERS}.get(symbol)
        ticker = ticker_dao.get_or_create_ticker(
            conn,
            symbol=symbol,
            name=meta["name"] if meta else None,
            sector=meta["sector"] if meta else None,
        )
        frame = fetcher(symbol, start, end)
        rows = history_to_rows(frame, symbol)
        if not rows:
            return {
                "symbol": symbol,
                "rows": 0,
                "inserted": 0,
                "error": "no data returned",
            }
        inserted = price_dao.upsert_daily_prices(conn, ticker["id"], rows)
        conn.commit()
        return {
            "symbol": symbol,
            "rows": len(rows),
            "inserted": inserted,
            "first": rows[0][0],
            "last": rows[-1][0],
        }
    except Exception as exc:  # noqa: BLE001 - one bad ticker must not kill the batch
        conn.rollback()
        return {"symbol": symbol, "rows": 0, "inserted": 0, "error": str(exc)}
    finally:
        conn.close()


def refresh_catalog(
    catalog: Sequence[TickerInfo] = DEFAULT_TICKERS,
    start: str | None = None,
    end: str | None = None,
    fetcher: Fetcher = fetch_history,
) -> dict[str, dict[str, Any]]:
    """Refresh every symbol in the catalog. Returns per-symbol summaries."""
    results: dict[str, dict[str, Any]] = {}
    for item in catalog:
        results[item["symbol"]] = refresh_ticker(item["symbol"], start, end, fetcher=fetcher)
    return results


def seed_catalog() -> dict[str, int]:
    """Insert the default catalog rows if missing. Used at app startup."""
    conn = get_connection()
    try:
        result = ticker_dao.upsert_catalog(conn, list(DEFAULT_TICKERS))
        conn.commit()
        return result
    finally:
        conn.close()


__all__ = ["fetch_history", "history_to_rows", "refresh_ticker", "refresh_catalog", "seed_catalog"]