"""Simulation orchestration: DB-backed returns, Monte Carlo, result caching.

This layer connects Phase 1 data (prices in SQLite) with the Phase 2 pure
engine. It converts daily closes to portfolio-level monthly returns so the
engine's per-period contribution aligns with monthly investing.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from ..simulation import monte_carlo
from ..dao import portfolios as portfolio_dao
from ..dao import prices as price_dao
from ..dao import simulations as simulation_dao
from . import sentiment_signal


def portfolio_monthly_returns(
    conn: sqlite3.Connection,
    holdings: Sequence[sqlite3.Row],
) -> np.ndarray:
    """Weighted monthly portfolio returns from stored daily closes.

    Each holding's closes are resampled to month-end, combined into a single
    frame, forward-filled, and the ragged early period (before every holding
    has data) is dropped. The monthly portfolio return is the weighted average
    of holding returns, weights normalized to sum to 1.
    """
    series_by_symbol: dict[str, pd.Series] = {}
    for holding in holdings:
        rows = price_dao.get_price_history(conn, holding["ticker_id"])
        if not rows:
            continue
        index = pd.to_datetime([r["date"] for r in rows])
        closes = pd.Series([float(r["close"]) for r in rows], index=index, dtype=float)
        series_by_symbol[holding["symbol"]] = closes.sort_index().resample("ME").last()

    missing = [h["symbol"] for h in holdings if h["symbol"] not in series_by_symbol]
    if missing:
        raise ValueError(f"no price history for holdings: {', '.join(sorted(missing))}")

    frame = pd.DataFrame(series_by_symbol).sort_index().ffill().dropna(how="any")
    monthly_returns = frame.pct_change().dropna(how="any")
    if monthly_returns.empty:
        raise ValueError("not enough overlapping monthly history to simulate")

    weights = np.array([float(h["weight"]) for h in holdings], dtype=float)
    weights = weights / weights.sum()
    symbols = [h["symbol"] for h in holdings]
    portfolio_returns = (monthly_returns[symbols].to_numpy() * weights).sum(axis=1)
    if portfolio_returns.size < 2:
        raise ValueError("need at least two monthly returns to simulate")
    return portfolio_returns


def canonical_params(
    *,
    initial_balance: float,
    monthly_contribution: float,
    horizon_months: int,
    n_simulations: int,
    blocks: int | None,
    seed: int | None,
    use_sentiment: bool = False,
    volatility_multiplier: float = 1.0,
    sentiment_score: float | None = None,
) -> dict[str, Any]:
    """Ordering-independent parameter key used for result caching.

    The sentiment fields are part of the key so a run is only reused while the
    sentiment it was built from is unchanged; a fresh news batch produces a new
    volatility multiplier and therefore a new run.
    """
    return {
        "initial_balance": float(initial_balance),
        "monthly_contribution": float(monthly_contribution),
        "horizon_months": int(horizon_months),
        "n_simulations": int(n_simulations),
        "blocks": blocks,
        "seed": seed,
        "use_sentiment": bool(use_sentiment),
        "volatility_multiplier": round(float(volatility_multiplier), 6),
        "sentiment_score": (
            None if sentiment_score is None else round(float(sentiment_score), 6)
        ),
    }


def _assemble_response(
    run_id: int,
    portfolio_id: int,
    created_at: str,
    params: dict[str, Any],
    levels: list[float],
    trajectories: list[list[float]],
    cached: bool,
) -> dict[str, Any]:
    finals = [path[-1] for path in trajectories]
    multiplier = float(params.get("volatility_multiplier", 1.0))
    final_by_level = dict(zip(levels, finals))
    return {
        "run_id": run_id,
        "portfolio_id": portfolio_id,
        "created_at": created_at,
        "cached": cached,
        "params": params,
        "sentiment": {
            "applied": bool(params.get("use_sentiment")) and multiplier != 1.0,
            "score": params.get("sentiment_score"),
            "volatility_multiplier": multiplier,
        },
        "percentiles": [
            {"level": level, "path": path}
            for level, path in zip(levels, trajectories, strict=True)
        ],
        "summary": {
            "worst_case_final_value": final_by_level[min(levels)],
            "median_final_value": final_by_level.get(50.0, finals[len(finals) // 2]),
            "best_case_final_value": final_by_level[max(levels)],
        },
    }


def run_portfolio_simulation(
    conn: sqlite3.Connection,
    portfolio_id: int,
    *,
    initial_balance: float,
    horizon_months: int,
    n_simulations: int = 1000,
    blocks: int | None = None,
    seed: int | None = None,
    use_sentiment: bool = False,
) -> dict[str, Any]:
    """Run (or fetch a cached) simulation for a portfolio. Raises ValueError.

    ``monthly_contribution`` comes from the portfolio record, so results are
    keyed by the contribution actually used. When ``use_sentiment`` is set, the
    recent sector + geopolitical news sentiment is aggregated into a score and
    mapped to a volatility multiplier applied to the historical returns.
    """
    portfolio = portfolio_dao.get_portfolio(conn, portfolio_id)
    if portfolio is None:
        raise ValueError(f"portfolio {portfolio_id} not found")

    holdings = portfolio_dao.list_holdings(conn, portfolio_id)
    if not holdings:
        raise ValueError("portfolio has no holdings")

    sentiment_score: float | None = None
    volatility_multiplier = 1.0
    if use_sentiment:
        sentiment_score = sentiment_signal.portfolio_sentiment_score(conn, holdings)
        if sentiment_score is not None:
            volatility_multiplier = monte_carlo.volatility_multiplier_from_sentiment(
                sentiment_score
            )

    monthly_contribution = float(portfolio["monthly_contribution"])
    params = canonical_params(
        initial_balance=initial_balance,
        monthly_contribution=monthly_contribution,
        horizon_months=horizon_months,
        n_simulations=n_simulations,
        blocks=blocks,
        seed=seed,
        use_sentiment=use_sentiment,
        volatility_multiplier=volatility_multiplier,
        sentiment_score=sentiment_score,
    )

    # The cached results are derived from the stored prices, which the daily
    # ingest rewrites on the current adjusted-close basis. Keying the cache on
    # parameters alone would serve a run computed from yesterday's prices
    # forever. Derive the portfolio return series BEFORE the cache lookup and
    # fold a fingerprint of it into the key so any price change invalidates.
    returns = portfolio_monthly_returns(conn, holdings)
    fingerprint = hashlib.sha1(returns.tobytes()).hexdigest()[:12]
    params["data_fingerprint"] = fingerprint
    params_json = json.dumps(params, sort_keys=True)

    cached_run = simulation_dao.find_cached_run(conn, portfolio_id, params_json)
    if cached_run is not None and simulation_dao.has_results(conn, cached_run["id"]):
        results = simulation_dao.get_results(conn, cached_run["id"])
        levels = [float(r["percentile"]) for r in results]
        trajectories = [json.loads(r["path_json"]) for r in results]
        return _assemble_response(
            run_id=cached_run["id"],
            portfolio_id=portfolio_id,
            created_at=cached_run["created_at"],
            params=params,
            levels=levels,
            trajectories=trajectories,
            cached=True,
        )

    result = monte_carlo.run_simulation(
        returns,
        initial_balance=initial_balance,
        monthly_contribution=monthly_contribution,
        horizon_months=horizon_months,
        n_simulations=n_simulations,
        blocks=blocks,
        seed=seed,
        volatility_multiplier=volatility_multiplier,
    )

    run_id = simulation_dao.create_run(conn, portfolio_id, params_json)
    levels_list = result["percentile_levels"]
    trajectories = [
        [round(float(x), 2) for x in path] for path in result["percentiles"]
    ]
    simulation_dao.save_results(
        conn, run_id, zip(levels_list, (json.dumps(p) for p in trajectories))
    )
    conn.commit()

    return _assemble_response(
        run_id=run_id,
        portfolio_id=portfolio_id,
        created_at=simulation_dao.get_run(conn, run_id)["created_at"],
        params=params,
        levels=levels_list,
        trajectories=trajectories,
        cached=False,
    )


def get_run_response(conn: sqlite3.Connection, run_id: int) -> dict[str, Any] | None:
    """Assemble a stored run's full response, or None if not found."""
    run = simulation_dao.get_run(conn, run_id)
    if run is None:
        return None
    results = simulation_dao.get_results(conn, run_id)
    if not results:
        return {"run_id": run_id, "error": "run has no stored results"}
    params = json.loads(run["params_json"])
    levels = [float(r["percentile"]) for r in results]
    trajectories = [json.loads(r["path_json"]) for r in results]
    return _assemble_response(
        run_id=run_id,
        portfolio_id=run["portfolio_id"],
        created_at=run["created_at"],
        params=params,
        levels=levels,
        trajectories=trajectories,
        cached=True,
    )


__all__ = [
    "portfolio_monthly_returns",
    "canonical_params",
    "run_portfolio_simulation",
    "get_run_response",
]