"""Screening statistics computed purely from the stored daily close series.

Every figure here is derived from the local ``prices`` table with pandas — the
screener makes no network calls. The ``KNOWN LIMITATION`` in the endpoint
docstring (which this module shares conceptually) is that the stored Close
column carries Yahoo's most recent adjustment basis, so income-heavy metrics
like the 1-year return are price-return only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252
MIN_VOLATILITY_WINDOW = 30  # fewer closes => annualized volatility is undefined


def compute_screener_stats(dates: list[str], closes: list[float]) -> dict:
    """Screen one (dates, closes) series into a stats dict.

    Returns ``latest_close``, ``prev_close``, ``one_day_change_pct``,
    ``one_year_total_return_pct``, ``annualized_volatility_pct`` and
    ``max_drawdown_pct``. Percentage fields are ``None`` when there is not
    enough history to define them; ``max_drawdown_pct`` is a negative percent
    (0 when the series never declined). Closes are expected to be positive.
    """
    series = pd.Series(data=closes, index=pd.to_datetime(dates), dtype=float).sort_index()
    n = int(series.size)
    if n == 0:
        raise ValueError("no price history to screen")

    latest_close = float(series.iloc[-1])
    prev_close = float(series.iloc[-2]) if n >= 2 else None

    one_day_change_pct = None
    if prev_close is not None and prev_close > 0:
        one_day_change_pct = round((latest_close / prev_close - 1) * 100, 4)

    one_year_total_return_pct = None
    if n >= TRADING_DAYS_PER_YEAR + 1:
        base = float(series.iloc[-(TRADING_DAYS_PER_YEAR + 1)])
        if base > 0:
            one_year_total_return_pct = round((latest_close / base - 1) * 100, 4)

    annualized_volatility_pct = None
    vol_window = series.iloc[-TRADING_DAYS_PER_YEAR:]
    positive = vol_window[vol_window > 0]
    if len(positive) >= MIN_VOLATILITY_WINDOW and len(positive) == len(vol_window):
        log_returns = np.log(vol_window / vol_window.shift(1)).dropna()
        if log_returns.size >= 2 and np.isfinite(log_returns).all():
            annualized_volatility_pct = round(
                float(log_returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR) * 100),
                4,
            )

    max_drawdown_pct = 0.0
    dd_window = (
        series.iloc[-(TRADING_DAYS_PER_YEAR + 1):]
        if n > TRADING_DAYS_PER_YEAR
        else series
    )
    if dd_window.size > 0:
        peak = dd_window.cummax()
        if (peak > 0).all():
            max_drawdown_pct = round(float(((dd_window / peak) - 1).min() * 100), 4)

    return {
        "latest_close": latest_close,
        "prev_close": prev_close,
        "one_day_change_pct": one_day_change_pct,
        "one_year_total_return_pct": one_year_total_return_pct,
        "annualized_volatility_pct": annualized_volatility_pct,
        "max_drawdown_pct": max_drawdown_pct,
    }


__all__ = ["compute_screener_stats", "TRADING_DAYS_PER_YEAR"]