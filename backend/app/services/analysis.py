"""Per-ETF in-depth analysis computed from stored daily closes.

Companion to :mod:`app.services.screener`. Where the screener returns one flat
row per ticker for the sortable table, this module builds the richer payload a
single ETF's detail page needs: a key-stat block, trailing returns across
horizons (for a bar chart), a year-by-month return grid (for a heatmap), a
daily-return histogram, a drawdown series (for an area chart) and a correlation
matrix against every other tracked ticker (for a second heatmap).

Everything derives from the local ``prices`` table with pandas/numpy. No
network, no heavy ingest-only dependency -- both are in ``requirements.txt`` and
imported at module scope the same way the screener does. The same KNOWN
LIMITATION applies: the stored Close carries Yahoo's most recent adjustment
basis, so income metrics are price-return only (see docs/data_methodology.md).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252

#: How many trailing months of returns the year-by-month heatmap shows.
HEATMAP_MONTHS = 60

#: How many trailing months of drawdown the area chart shows.
DRAWDOWN_MONTHS = 36

#: How many trailing months of monthly returns the correlation matrix uses.
CORRELATION_MONTHS = 36

#: Fewest overlapping monthly returns before a correlation is reported as None.
#: Below this a Pearson coefficient is noise (a 2-point overlap is always +-1).
MIN_CORRELATION_OVERLAP = 6

#: Equal-width bins the daily-return histogram is sliced into.
HISTOGRAM_BINS = 40

#: Risk-free rate used for the simplified Sharpe ratio. Zero, because a
#: free-risk benchmark is not tracked in the catalog; a user who wants one can
#: read ``one_year_total_return_pct`` next to it instead.
SHARPE_RISK_FREE = 0.0


def _empty_analysis(symbol: str) -> dict:
    """The shape returned for a ticker with no price history at all."""
    return {
        "symbol": symbol,
        "stats": None,
        "trailing_returns": [],
        "monthly_returns": [],
        "returns_histogram": [],
        "drawdown_series": [],
        "correlation": None,
    }


def _monthly_close_series(series: pd.Series) -> pd.Series:
    """Month-end closes of a daily series, forward-filled over gaps."""
    return series.resample("ME").last().ffill().dropna()


def _annualize(total_return: float, months: int) -> float | None:
    """Compound a total return over ``months`` to a per-annum figure."""
    if months <= 0:
        return None
    growth = 1.0 + total_return
    if growth <= 0:
        # A total return that wiped the position out has no real annual rate.
        return None
    return growth ** (12.0 / months) - 1.0


def _trailing_return(series: pd.Series, months: int) -> tuple[float | None, int]:
    """Total return and month count for a trailing ``months``-month window."""
    monthly = _monthly_close_series(series)
    if monthly.size < 2:
        return None, int(monthly.size)
    last = float(monthly.iloc[-1])
    target = len(monthly) - 1 - months
    if target < 0:
        # Not enough history for the full window: use however much exists,
        # which keeps a young fund's early numbers defined.
        target = 0
    base = float(monthly.iloc[target])
    if base <= 0:
        return None, int(monthly.size - 1 - target)
    return last / base - 1.0, int(monthly.size - 1 - target)


def _build_trailing_returns(series: pd.Series) -> list[dict]:
    """Trailing total returns over standard horizons, annualized past 1Y.

    Each entry is ``{"label", "return_pct", "months", "annualized"}`` where
    ``return_pct`` is the plain total return over the window and
    ``annualized`` is the per-annum figure (None when the window is under a
    year or undefined). Both are surfaced because a bar chart of mixed windows
    is only honest when the viewer can see which bars are annualized.
    """
    horizons = [
        ("1M", 1),
        ("3M", 3),
        ("6M", 6),
        ("1Y", 12),
        ("3Y", 36),
        ("5Y", 60),
    ]
    out: list[dict] = []
    for label, months in horizons:
        total, span = _trailing_return(series, months)
        if total is None:
            out.append(
                {"label": label, "return_pct": None, "months": span, "annualized": None}
            )
            continue
        annualized = _annualize(total, span) if span >= 12 else None
        out.append(
            {
                "label": label,
                "return_pct": round(total * 100, 4),
                "months": span,
                "annualized": round(annualized * 100, 4) if annualized is not None else None,
            }
        )

    # "Max" over whatever full history exists, annualized only if >= 1 year.
    monthly = _monthly_close_series(series)
    if monthly.size >= 2:
        base = float(monthly.iloc[0])
        last = float(monthly.iloc[-1])
        span = int(monthly.size - 1)
        if base > 0:
            total = last / base - 1.0
            annualized = _annualize(total, span) if span >= 12 else None
            out.append(
                {
                    "label": "Max",
                    "return_pct": round(total * 100, 4),
                    "months": span,
                    "annualized": round(annualized * 100, 4)
                    if annualized is not None
                    else None,
                }
            )
    return out


def _build_monthly_returns(series: pd.Series, months: int) -> list[dict]:
    """Last ``months`` calendar-month returns as a flat year/month grid.

    Each entry is ``{"year", "month" (1-12), "return_pct"}``, one per calendar
    month from the series' month-end closes. A month with no bar is skipped
    (forward-fill in the month-end series absorbs the gap only if a later bar
    in the same month exists); the newest month is included even if partial,
    because that is what the trader is looking at.
    """
    monthly = _monthly_close_series(series)
    if monthly.size < 2:
        return []
    returns = monthly.pct_change().dropna()
    returns = returns.iloc[-months:]
    out: list[dict] = []
    for timestamp, value in returns.items():
        if not math.isfinite(float(value)):
            continue
        out.append(
            {
                "year": int(timestamp.year),
                "month": int(timestamp.month),
                "return_pct": round(float(value) * 100, 4),
            }
        )
    return out


def _build_histogram(series: pd.Series, n_bins: int = HISTOGRAM_BINS) -> list[dict]:
    """Equal-width histogram of the last year's daily log returns, in percent.

    Returns ``{"start_pct", "end_pct", "count"}`` bins. The bin edges are taken
    from the observed range, so a volatile fund gets wider bins than a calm one
    -- a fixed absolute range would either crush a bond fund into one spike or
    spread an equity fund across empty space. The caller can label each bar
    with its midpoint.
    """
    window = series.iloc[-TRADING_DAYS_PER_YEAR:]
    if window.size < 2:
        return []
    log_returns = np.log(window / window.shift(1)).dropna()
    log_returns = log_returns[np.isfinite(log_returns)]
    if log_returns.size < 2:
        return []
    values = (log_returns.to_numpy() * 100)
    low = float(values.min())
    high = float(values.max())
    if not (math.isfinite(low) and math.isfinite(high)):
        return []
    if high <= low:
        # Degenerate (flat) series: a single zero-width bin holding everything.
        return [{"start_pct": round(low, 4), "end_pct": round(low, 4), "count": int(values.size)}]
    counts, edges = np.histogram(values, bins=n_bins, range=(low, high))
    out: list[dict] = []
    for i, count in enumerate(counts):
        out.append(
            {
                "start_pct": round(float(edges[i]), 4),
                "end_pct": round(float(edges[i + 1]), 4),
                "count": int(count),
            }
        )
    return out


def _build_drawdown_series(series: pd.Series, months: int) -> list[dict]:
    """Running drawdown of month-end closes over the last ``months`` months.

    Each entry is ``{"date", "drawdown_pct"}`` where drawdown is the percentage
    below the running peak of the (month-end) series, so 0 means at a high and
    -30 means 30% below the prior peak. Truncated to the trailing window.
    """
    monthly = _monthly_close_series(series)
    if monthly.size < 2:
        return []
    window = monthly.iloc[-months:]
    peak = window.cummax()
    drawdown = (window / peak - 1.0) * 100.0
    return [
        {
            "date": timestamp.strftime("%Y-%m-%d"),
            "drawdown_pct": round(float(value), 4),
        }
        for timestamp, value in drawdown.items()
        if math.isfinite(float(value))
    ]


def _build_correlation(
    subject_symbol: str,
    series: pd.Series,
    all_series: dict[str, pd.Series],
    months: int = CORRELATION_MONTHS,
    min_overlap: int = MIN_CORRELATION_OVERLAP,
) -> dict | None:
    """Pearson correlation of this ticker against every other, monthly returns.

    ``all_series`` maps symbol -> daily close series (including this one). Only
    the trailing ``months`` months of monthly returns enter, and a pair needs at
    least ``min_overlap`` overlapping months before a coefficient is reported;
    otherwise that cell is None. Returns ``{"symbols", "matrix"}`` with the
    subject symbol first (so its diagonal 1.0 sits at index 0), or None when
    this ticker itself has no usable history.
    """

    def _tail_monthly(s: pd.Series) -> pd.Series:
        monthly = _monthly_close_series(s)
        if monthly.size < 2:
            return pd.Series(dtype=float)
        return monthly.pct_change().dropna().iloc[-months:]

    subject = _tail_monthly(series)
    if subject.size < min_overlap:
        return None

    # Subject first, then every other symbol with history, sorted for stability.
    others = sorted(s for s in all_series if s != subject_symbol)
    ordered = [subject_symbol, *others]
    tails = {name: _tail_monthly(all_series[name]) for name in ordered}

    n = len(ordered)
    matrix: list[list[float | None]] = [[None] * n for _ in range(n)]
    for i, a in enumerate(ordered):
        for j, b in enumerate(ordered):
            if i == j:
                overlap = int(tails[a].size)
                matrix[i][j] = 1.0 if overlap >= min_overlap else None
                continue
            left, right = tails[a].align(tails[b], join="inner")
            if left.size < min_overlap:
                matrix[i][j] = None
                continue
            if left.std(ddof=1) == 0 or right.std(ddof=1) == 0:
                # Zero-variance side makes Pearson undefined (0/0).
                matrix[i][j] = None
                continue
            coef = float(np.corrcoef(left.to_numpy(), right.to_numpy())[0, 1])
            matrix[i][j] = round(coef, 4) if math.isfinite(coef) else None
    return {"symbols": ordered, "matrix": matrix}


def _sharpe_annualized(series: pd.Series) -> float | None:
    """Simplified annualized Sharpe from daily log returns over the last year.

    ``(mean_daily - rf_daily) / std_daily * sqrt(252)`` with rf = 0 (see
    SHARPE_RISK_FREE). Undefined with under 30 returns or zero dispersion.
    """
    window = series.iloc[-TRADING_DAYS_PER_YEAR:]
    if window.size < 2:
        return None
    log_returns = np.log(window / window.shift(1)).dropna()
    log_returns = log_returns[np.isfinite(log_returns)]
    if log_returns.size < 30:
        return None
    std = float(log_returns.std(ddof=1))
    if std == 0 or not math.isfinite(std):
        return None
    rf_daily = SHARPE_RISK_FREE / TRADING_DAYS_PER_YEAR
    excess = float(log_returns.mean()) - rf_daily
    return round(excess / std * math.sqrt(TRADING_DAYS_PER_YEAR), 4)


def compute_analysis(
    symbol: str,
    name: str | None,
    sector: str | None,
    dates: list[str],
    closes: list[float],
    all_ticker_series: dict[str, pd.Series] | None = None,
) -> dict:
    """Build the full in-depth analysis payload for one ticker.

    ``dates``/``closes`` are the stored daily series for this ticker,
    oldest-first. ``all_ticker_series`` optionally maps every tracked symbol
    (including this one) to its daily close series so the correlation matrix can
    be built without a second pass in the router.

    The payload mirrors :class:`app.schemas.EtfAnalysisOut`. With fewer than two
    closes the payload is empty except for ``symbol`` (the router raises a 404
    before reaching here for a ticker that truly has no rows, so this branch is
    a safety net for a race between the router and a concurrent wipe).
    """
    if not closes or len(closes) < 2:
        payload = _empty_analysis(symbol)
        payload["name"] = name
        payload["sector"] = sector
        return payload

    series = pd.Series(
        data=closes, index=pd.to_datetime(dates), dtype=float
    ).sort_index()
    series = series[series > 0]
    if series.size < 2:
        payload = _empty_analysis(symbol)
        payload["name"] = name
        payload["sector"] = sector
        return payload

    latest_close = float(series.iloc[-1])
    prev_close = float(series.iloc[-2]) if series.size >= 2 else None
    one_day_change_pct = None
    if prev_close is not None and prev_close > 0:
        one_day_change_pct = round((latest_close / prev_close - 1) * 100, 4)

    # --- Screener-equivalent risk stats (reuse the same definitions) --------
    one_year_total_return_pct = None
    if series.size > TRADING_DAYS_PER_YEAR:
        base = float(series.iloc[-(TRADING_DAYS_PER_YEAR + 1)])
        if base > 0:
            one_year_total_return_pct = round((latest_close / base - 1) * 100, 4)

    annualized_volatility_pct = None
    vol_window = series.iloc[-TRADING_DAYS_PER_YEAR:]
    if vol_window.size >= 30:
        log_returns = np.log(vol_window / vol_window.shift(1)).dropna()
        if log_returns.size >= 2 and np.isfinite(log_returns).all():
            annualized_volatility_pct = round(
                float(log_returns.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100),
                4,
            )

    # 1Y max drawdown, matching the screener so the two views never disagree.
    max_drawdown_pct = 0.0
    dd_window = (
        series.iloc[-(TRADING_DAYS_PER_YEAR + 1):]
        if series.size > TRADING_DAYS_PER_YEAR
        else series
    )
    if dd_window.size > 0:
        peak = dd_window.cummax()
        if (peak > 0).all():
            max_drawdown_pct = round(float(((dd_window / peak) - 1).min() * 100), 4)

    # Full-history max drawdown, the other number a detail page wants.
    full_max_drawdown_pct = None
    if series.size > 1:
        peak = series.cummax()
        if (peak > 0).all():
            full_max_drawdown_pct = round(float(((series / peak) - 1).min() * 100), 4)

    # Best / worst single-day move over the trailing year.
    daily = series.pct_change().dropna()
    daily_window = daily.iloc[-TRADING_DAYS_PER_YEAR:]
    best_day_pct = None
    worst_day_pct = None
    if daily_window.size > 0:
        finite = daily_window[np.isfinite(daily_window)]
        if finite.size > 0:
            best_day_pct = round(float(finite.max()) * 100, 4)
            worst_day_pct = round(float(finite.min()) * 100, 4)

    # Best / worst calendar month over the heatmap window.
    monthly = _monthly_close_series(series)
    monthly_returns = monthly.pct_change().dropna()
    best_month_pct = None
    worst_month_pct = None
    if monthly_returns.size > 0:
        finite = monthly_returns[np.isfinite(monthly_returns)]
        if finite.size > 0:
            best_month_pct = round(float(finite.max()) * 100, 4)
            worst_month_pct = round(float(finite.min()) * 100, 4)

    stats = {
        "latest_close": latest_close,
        "prev_close": prev_close,
        "one_day_change_pct": one_day_change_pct,
        "one_year_total_return_pct": one_year_total_return_pct,
        "annualized_volatility_pct": annualized_volatility_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "full_max_drawdown_pct": full_max_drawdown_pct,
        "best_day_pct": best_day_pct,
        "worst_day_pct": worst_day_pct,
        "best_month_pct": best_month_pct,
        "worst_month_pct": worst_month_pct,
        "sharpe_annualized": _sharpe_annualized(series),
        "price_rows": int(series.size),
        "first_date": series.index[0].strftime("%Y-%m-%d"),
        "last_date": series.index[-1].strftime("%Y-%m-%d"),
    }

    correlation = None
    if all_ticker_series:
        correlation = _build_correlation(symbol, series, all_ticker_series)

    return {
        "symbol": symbol,
        "name": name,
        "sector": sector,
        "stats": stats,
        "trailing_returns": _build_trailing_returns(series),
        "monthly_returns": _build_monthly_returns(series, HEATMAP_MONTHS),
        "returns_histogram": _build_histogram(series),
        "drawdown_series": _build_drawdown_series(series, DRAWDOWN_MONTHS),
        "correlation": correlation,
    }


__all__ = [
    "compute_analysis",
    "TRADING_DAYS_PER_YEAR",
    "HEATMAP_MONTHS",
    "DRAWDOWN_MONTHS",
    "CORRELATION_MONTHS",
    "MIN_CORRELATION_OVERLAP",
    "HISTOGRAM_BINS",
]
