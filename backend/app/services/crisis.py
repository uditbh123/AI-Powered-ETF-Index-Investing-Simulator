"""Crisis replay: re-run a portfolio through a fixed historical window.

The replayed trajectory compounds the portfolio's own *realized* monthly
returns over a known crisis window. Contributions are deposited at the start
of each month (the same annuity-due convention as the main engine, see
``docs/data_methodology.md``), so the path is directly comparable to a fan
chart. Alongside it the service returns 10/50/90 percentile bands resampled
from the full history by the bootstrap engine with a fixed seed, so the user
sees what the window *actually* did against what the simulation would have
predicted.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Sequence

import numpy as np
import pandas as pd

from ..dao import portfolios as portfolio_dao
from ..simulation import monte_carlo
from .simulation import portfolio_monthly_returns_with_dates

# name -> (start YYYY-MM, end YYYY-MM), month-end inclusive.
CRISIS_WINDOWS = {
    "dot_com_2000": ("2000-03", "2002-09"),
    "gfc_2008": ("2007-10", "2009-03"),
    "covid_2020": ("2020-02", "2020-04"),
}

CRISIS_SEED = 42
CRISIS_N_SIMULATIONS = 2000


def slice_window(
    dates: Sequence[str],
    returns: np.ndarray,
    crisis: str,
) -> tuple[np.ndarray, list[str]]:
    """Return the ``(returns, dates)`` inside the crisis window.

    Slices on calendar month (month-end labels inclusive). Raises a ValueError
    naming the crisis and the reason when history does not fully cover the
    window.
    """
    if crisis not in CRISIS_WINDOWS:
        raise ValueError(f"unknown crisis '{crisis}' (expected one of {sorted(CRISIS_WINDOWS)})")

    start, end = CRISIS_WINDOWS[crisis]
    start_period = pd.Period(start, freq="M")
    end_period = pd.Period(end, freq="M")
    months = [pd.Timestamp(d).to_period("M") for d in dates]
    required = int((end_period - start_period).n) + 1

    mask = np.array([start_period <= p <= end_period for p in months], dtype=bool)
    if int(mask.sum()) < required:
        raise ValueError(
            f"crisis '{crisis}' needs monthly history covering {start} to {end}, "
            f"but this portfolio's history ({dates[0] if dates else 'none'}.."
            f"{dates[-1] if dates else 'none'}) does not cover it: {_coverage_reason(months, start_period, end_period)}"
        )

    window_returns = np.asarray(returns, dtype=float)[mask]
    window_dates = [d for d, included in zip(dates, mask, strict=True) if included]
    return window_returns, window_dates


def _coverage_reason(
    months: list[pd.Period],
    start_period: pd.Period,
    end_period: pd.Period,
) -> str:
    if not months:
        return "no monthly history at all"
    first, last = months[0], months[-1]
    if last < start_period:
        return "price history ends before the crisis began"
    if first > end_period:
        return "instruments launched after the crisis window ended"
    return "history overlaps the window but does not cover it fully"


def compound_actual(
    returns: np.ndarray,
    initial_balance: float,
    monthly_contribution: float,
) -> np.ndarray:
    """Compound realized returns with start-of-month contributions.

    Mirrors ``simulate_paths`` in ``monte_carlo.py`` for a single deterministic
    path: with ``growth_t = prod(1 + r)`` through month t,

        value_t = growth_t * (initial + contribution * sum_{k<=t} 1/growth_k)

    (``growth_0 := 1``), i.e. the contribution deposited at the start of a month
    earns that month's return. Returns the trajectory including the initial
    balance at index 0.
    """
    returns = np.asarray(returns, dtype=float)
    growth = np.cumprod(1.0 + returns)
    inv = 1.0 / growth
    inv_shifted = np.concatenate([np.ones(1), inv[:-1]])
    inverse_sum = np.cumsum(inv_shifted)
    values = growth * (float(initial_balance) + float(monthly_contribution) * inverse_sum)
    return np.concatenate([[float(initial_balance)], values])


def run_crisis_replay(
    conn: sqlite3.Connection,
    portfolio_id: int,
    *,
    crisis: str,
    initial_balance: float,
    n_simulations: int = CRISIS_N_SIMULATIONS,
    seed: int = CRISIS_SEED,
) -> dict:
    """Replay ``portfolio_id`` through ``crisis``. Raises ValueError."""
    if crisis not in CRISIS_WINDOWS:
        raise ValueError(f"unknown crisis '{crisis}' (expected one of {sorted(CRISIS_WINDOWS)})")

    portfolio = portfolio_dao.get_portfolio(conn, portfolio_id)
    if portfolio is None:
        raise ValueError(f"portfolio {portfolio_id} not found")

    holdings = portfolio_dao.list_holdings(conn, portfolio_id)
    if not holdings:
        raise ValueError("portfolio has no holdings")

    dates, monthly = portfolio_monthly_returns_with_dates(conn, holdings)
    window_returns, window_dates = slice_window(dates, monthly, crisis)
    monthly_contribution = float(portfolio["monthly_contribution"])

    real_path = compound_actual(window_returns, initial_balance, monthly_contribution)

    # Bands from the full-history bootstrap, fixed seed for reproducible charts.
    result = monte_carlo.run_simulation(
        monthly,
        initial_balance=initial_balance,
        monthly_contribution=monthly_contribution,
        horizon_months=int(window_returns.size),
        n_simulations=n_simulations,
        seed=seed,
    )
    percentiles = [
        {"level": level, "path": [round(float(x), 2) for x in band]}
        for level, band in zip(
            result["percentile_levels"], result["percentiles"], strict=True
        )
    ]

    return {
        "portfolio_id": portfolio_id,
        "crisis": crisis,
        "window": {
            "start": window_dates[0],
            "end": window_dates[-1],
            "months": len(window_dates),
        },
        "initial_balance": float(initial_balance),
        "monthly_contribution": monthly_contribution,
        "real_path": [round(float(x), 2) for x in real_path],
        "percentiles": percentiles,
    }


__all__ = [
    "CRISIS_WINDOWS",
    "CRISIS_SEED",
    "CRISIS_N_SIMULATIONS",
    "slice_window",
    "compound_actual",
    "run_crisis_replay",
]