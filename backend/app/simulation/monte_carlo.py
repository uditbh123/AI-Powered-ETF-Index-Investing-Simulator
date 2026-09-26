"""Vectorized Monte Carlo simulation for long-term investing strategies.

Pure module: no API, database, or network dependencies. It takes historical
returns (e.g. a NumPy array of daily or monthly returns) as input and
produces simulated portfolio value trajectories using bootstrap resampling.

Everything is vectorized with NumPy; there are no Python-level loops over
simulated paths. A bootstrap draws historical returns with replacement (iid)
or in contiguous blocks (to preserve short-run autocorrelation).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

# Phase 6 fan chart uses the 10th-90th confidence interval around the median.
DEFAULT_PERCENTILES = (10, 50, 90)

# --- Sentiment -> volatility mapping ---------------------------------------
# FinBERT scores live in [-1, 1]. We scale the *dispersion* of the bootstrap
# returns about their mean: multiplier > 1 widens the simulated distribution
# (more risk), < 1 narrows it. The band is deliberately narrow (score -1 ->
# 1.10x vol, score +1 -> 0.95x vol) because the sentiment->volatility
# correlation in our validation was weak (docs/sentiment_validation.md):
# sentiment is mostly noise, so we act only lightly on it. The asymmetry is
# retained because negative news / uncertainty moves markets harder than
# positive news calms them (leverage effect, Black 1976).
NEGATIVE_SENTIMENT_SENSITIVITY = 0.10
POSITIVE_SENTIMENT_SENSITIVITY = 0.05
MIN_VOLATILITY_MULTIPLIER = 0.9
MAX_VOLATILITY_MULTIPLIER = 1.1


def returns_from_prices(prices: Sequence[float]) -> np.ndarray:
    """Convert a series of prices/closes into period-over-period returns."""
    prices = np.asarray(prices, dtype=float)
    if prices.ndim != 1:
        raise ValueError(f"Expected a 1-D price series, got shape {prices.shape}")
    if prices.size < 2:
        raise ValueError("At least two prices are required to compute returns")
    if np.any(prices <= 0):
        raise ValueError("Prices must be strictly positive")
    return np.diff(prices) / prices[:-1]


def volatility_multiplier_from_sentiment(
    score: float,
    *,
    negative_sensitivity: float = NEGATIVE_SENTIMENT_SENSITIVITY,
    positive_sensitivity: float = POSITIVE_SENTIMENT_SENSITIVITY,
) -> float:
    """Map a [-1, 1] sentiment score to a volatility multiplier.

    Math: the multiplier is piecewise-linear in the score,

        multiplier = 1 + negative_sensitivity * (-score)   if score <  0
        multiplier = 1 - positive_sensitivity *   score    if score >= 0

    so it is exactly 1 (no adjustment) at neutral sentiment, rises above 1 as
    sentiment turns negative (wider simulated paths) and dips below 1 as it
    turns positive. The result is clipped to [0.9, 1.1] so one noisy headline
    batch can never produce a degenerate (near-zero variance) or explosive
    distribution. Non-finite input is treated as neutral.
    """
    if not math.isfinite(score):
        return 1.0
    score = float(np.clip(score, -1.0, 1.0))
    if score < 0.0:
        multiplier = 1.0 + negative_sensitivity * (-score)
    else:
        multiplier = 1.0 - positive_sensitivity * score
    return float(
        np.clip(multiplier, MIN_VOLATILITY_MULTIPLIER, MAX_VOLATILITY_MULTIPLIER)
    )


def scale_returns_volatility(
    returns: Sequence[float],
    multiplier: float,
) -> np.ndarray:
    """Rescale a return series' standard deviation, preserving its mean.

    Math: with sample mean ``mu``, the transform ``r' = mu + multiplier *
    (r - mu)`` multiplies the deviations about the mean, which scales the
    standard deviation by exactly ``multiplier`` while leaving the mean (the
    drift) untouched. Scaling the bootstrap *inputs* this way shifts the whole
    resampled distribution rather than post-processing individual paths.
    Results are floored at -0.99 so a scaled draw can never imply a loss of
    more than the entire position.
    """
    returns = np.asarray(returns, dtype=float)
    if multiplier < 0:
        raise ValueError("volatility multiplier must be >= 0")
    if returns.size == 0 or multiplier == 1.0:
        return returns
    mean = float(np.mean(returns))
    scaled = mean + multiplier * (returns - mean)
    return np.maximum(scaled, -0.99)


def _draw_returns(
    rng: np.random.Generator,
    returns: np.ndarray,
    n_simulations: int,
    n_steps: int,
    blocks: int | None,
) -> np.ndarray:
    """Resample ``returns`` into an (n_simulations, n_steps) matrix."""
    n_history = returns.size
    if blocks is None:
        return rng.choice(returns, size=(n_simulations, n_steps), replace=True)

    if blocks <= 0:
        raise ValueError("blocks must be a positive integer or None")
    n_blocks = int(np.ceil(n_steps / blocks))
    starts = rng.integers(0, n_history, size=(n_simulations, n_blocks))
    idx = starts[:, :, None] + np.arange(blocks)[None, None, :]
    sampled = np.take(returns, idx % n_history, axis=-1)
    flat = sampled.reshape(n_simulations, n_blocks * blocks)
    return flat[:, :n_steps]


def simulate_paths(
    returns: Sequence[float],
    initial_balance: float,
    monthly_contribution: float = 0.0,
    horizon_months: int = 120,
    n_simulations: int = 1000,
    blocks: int | None = None,
    seed: int | None = None,
    volatility_multiplier: float = 1.0,
) -> np.ndarray:
    """Simulate portfolio value trajectories via bootstrap resampling.

    Contributions are deposited at the start of each period and then grow with
    that period's return. Returns an array of shape
    (n_simulations, horizon_months + 1) where column ``t`` is the portfolio
    value at the end of period ``t`` (column 0 is the initial balance).

    ``volatility_multiplier`` optionally rescales the historical returns'
    dispersion before resampling (see :func:`scale_returns_volatility`); the
    sentiment pipeline uses this to widen/narrow the fan chart.
    """
    if initial_balance < 0:
        raise ValueError("initial_balance must be >= 0")
    if monthly_contribution < 0:
        raise ValueError("monthly_contribution must be >= 0")
    if horizon_months < 1:
        raise ValueError("horizon_months must be >= 1")
    if n_simulations < 1:
        raise ValueError("n_simulations must be >= 1")

    rng = np.random.default_rng(seed)
    returns = np.asarray(returns, dtype=float)
    if returns.ndim != 1 or returns.size == 0:
        raise ValueError("returns must be a non-empty 1-D array")
    if volatility_multiplier != 1.0:
        returns = scale_returns_volatility(returns, volatility_multiplier)

    drawn = _draw_returns(rng, returns, n_simulations, horizon_months, blocks)

    growth = np.cumprod(1.0 + drawn, axis=1)
    inv = 1.0 / growth
    # start-of-period contributions: contribution in period k grows from period k,
    # so it needs 1/growth[k-1] with growth[0] := 1 (shift right by one column)
    inv_shifted = np.concatenate([np.ones((inv.shape[0], 1)), inv[:, :-1]], axis=1)
    inverse_sum = np.cumsum(inv_shifted, axis=1)
    values = growth * (float(initial_balance) + float(monthly_contribution) * inverse_sum)

    start = np.full((n_simulations, 1), float(initial_balance))
    return np.concatenate([start, values], axis=1)


def path_percentiles(
    paths: np.ndarray,
    levels: Sequence[float] = DEFAULT_PERCENTILES,
) -> np.ndarray:
    """Return percentile trajectories of shape (len(levels), n_steps).

    With default levels this gives the best-case (90th), median (50th) and
    worst-case (10th) growth trajectories used for fan charts.
    """
    paths = np.asarray(paths, dtype=float)
    if paths.ndim != 2:
        raise ValueError(f"Expected a 2-D paths matrix, got shape {paths.shape}")
    return np.percentile(paths, list(levels), axis=0)


def compute_distribution_stats(
    paths: np.ndarray,
    initial_balance: float,
    monthly_contribution: float = 0.0,
    horizon_months: int = 120,
) -> dict:
    """Summarize a simulated final-value distribution into actionable stats.

    ``paths`` is the (n_simulations, n_steps) matrix produced by
    :func:`simulate_paths`. ``total_contributed`` is the book value (initial
    balance plus all monthly contributions) and is the baseline
    ``probability_of_profit`` is measured against: the fraction of paths that
    end above it.

    ``upside_downside_ratio`` is the Sortino-family ratio computed on *monthly
    simple returns* with a zero threshold: mean of the positive months divided
    by the root-mean-square of the negative months. It deliberately does not
    use final-value percentiles. The earlier definition,
    ``(p90 - total_contributed) / (total_contributed - p10)``, was undefined in
    the common case rather than the degenerate one: over any horizon long
    enough for drift to matter, even the 10th-percentile path finishes above
    the book value, so the denominator turned negative and the stat was
    reported as null for most realistic long-horizon runs. The return-based
    form only requires a losing month to exist somewhere in the fan, which is
    not a meaningful restriction for a multi-period equity path. It is null
    only when no step return is negative at all.

    ``median_max_drawdown`` is the median over paths of each path's peak-to-end
    drawdown. It is computed on the *portfolio* trajectory, so contributions
    proportionally dampen it (every deposit raises the running peak that later
    drawdowns are measured from); it is therefore not the drawdown a
    buy-and-hold investor in the underlying index would have seen.

    ``histogram`` buckets the final values into 20 equal-width bins, returning
    the bin edges and counts for a distribution chart. All outputs are
    JSON-serializable.
    """
    paths = np.asarray(paths, dtype=float)
    if paths.ndim != 2:
        raise ValueError(f"Expected a 2-D paths matrix, got shape {paths.shape}")
    if initial_balance < 0:
        raise ValueError("initial_balance must be >= 0")
    if monthly_contribution < 0:
        raise ValueError("monthly_contribution must be >= 0")
    if horizon_months < 1:
        raise ValueError("horizon_months must be >= 1")

    total_contributed = float(initial_balance) + float(monthly_contribution) * horizon_months

    finals = paths[:, -1]

    p10, p25, p50, p75, p90 = np.percentile(finals, [10, 25, 50, 75, 90])
    final_percentiles = {
        "p10": float(p10),
        "p25": float(p25),
        "p50": float(p50),
        "p75": float(p75),
        "p90": float(p90),
    }

    running_peak = np.maximum.accumulate(paths, axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        drawdowns = paths / running_peak - 1.0
    # Months before any money is in the portfolio (initial balance 0) have a
    # zero running peak; the drawdown there is exactly 0, not NaN.
    drawdowns = np.where(running_peak > 0, drawdowns, 0.0)
    median_max_drawdown = float(np.median(drawdowns.min(axis=1)))

    # Upside/downside ratio over monthly simple returns, threshold 0.
    # See the docstring for why this is not a final-value percentile ratio.
    upside_downside_ratio: float | None = None
    if paths.shape[1] >= 2:
        opening = paths[:, :-1]
        with np.errstate(invalid="ignore", divide="ignore"):
            # A step opening on zero (initial_balance 0) has no defined
            # return; 0 is the neutral choice, matching the drawdown
            # convention above, and `np.where` keeps the division itself
            # out of the result so no NaN can survive into the mean.
            step_returns = np.where(
                opening > 0, paths[:, 1:] / opening - 1.0, 0.0
            )
        mean_gain = float(np.mean(np.maximum(step_returns, 0.0)))
        downside_deviation = float(
            np.sqrt(np.mean(np.minimum(step_returns, 0.0) ** 2))
        )
        if downside_deviation > 0.0:
            upside_downside_ratio = mean_gain / downside_deviation

    counts, bin_edges = np.histogram(finals, bins=20)
    histogram = {
        "bin_edges": bin_edges.tolist(),
        "counts": [int(c) for c in counts],
    }

    return {
        "total_contributed": total_contributed,
        "probability_of_profit": float(np.mean(finals > total_contributed)),
        "final_percentiles": final_percentiles,
        "median_max_drawdown": median_max_drawdown,
        "upside_downside_ratio": upside_downside_ratio,
        "histogram": histogram,
    }


@dataclass
class ValidationReport:
    """Comparison of simulated returns against the historical sample."""

    historical_mean: float
    historical_std: float
    historical_geometric_mean: float | None
    simulated_mean: float
    simulated_std: float
    simulated_geometric_mean: float
    mean_match: bool
    std_match: bool
    geometric_mean_match: bool | None
    tolerance: float

    def as_dict(self) -> dict:
        return {
            "historical_mean": self.historical_mean,
            "historical_std": self.historical_std,
            "historical_geometric_mean": self.historical_geometric_mean,
            "simulated_mean": self.simulated_mean,
            "simulated_std": self.simulated_std,
            "simulated_geometric_mean": self.simulated_geometric_mean,
            "mean_match": self.mean_match,
            "std_match": self.std_match,
            "geometric_mean_match": self.geometric_mean_match,
            "tolerance": self.tolerance,
        }


def validate_bootstrap(
    returns: Sequence[float],
    n_simulations: int = 5000,
    horizon_months: int = 60,
    tolerance: float = 0.05,
    seed: int | None = None,
) -> ValidationReport:
    """Validate the engine against a naive baseline.

    A correct engine resamples from the historical distribution, so the mean
    and standard deviation of the simulated per-period returns must converge
    to the historical arithmetic mean/std. The average per-path geometric
    (compounded) return must converge to the historical geometric mean.
    """
    if not 0.0 < tolerance < 1.0:
        raise ValueError("tolerance must be between 0 and 1")

    returns = np.asarray(returns, dtype=float)
    periods = np.arange(1, horizon_months + 1)
    hist_arith_mean = float(np.mean(returns))
    hist_std = float(np.std(returns, ddof=1))
    hist_geom_mean = float(np.exp(np.mean(np.log1p(returns))) - 1.0) if np.all(returns > -1.0) else None

    paths = simulate_paths(
        returns=returns,
        initial_balance=1.0,
        monthly_contribution=0.0,
        horizon_months=horizon_months,
        n_simulations=n_simulations,
        seed=seed,
    )
    periods_path = paths[:, 1:]
    per_period = (periods_path[:, 1:] / periods_path[:, :-1]) - 1.0

    sim_mean = float(np.mean(per_period))
    sim_std = float(np.std(per_period, ddof=1))

    sim_geom = np.exp(np.mean(np.log(periods_path[:, -1])) / horizon_months) - 1.0

    def _within_sim(a: float, b: float) -> bool:
        if a == 0.0 and b == 0.0:
            return True
        return abs(a - b) <= tolerance * max(abs(a), abs(b))

    # If the historical geometric mean is undefined (some return <= -1), do not
    # fabricate a match: report None instead of comparing sim against itself.
    geometric_mean_match = (
        _within_sim(hist_geom_mean, sim_geom) if hist_geom_mean is not None else None
    )

    return ValidationReport(
        historical_mean=hist_arith_mean,
        historical_std=hist_std,
        historical_geometric_mean=hist_geom_mean,
        simulated_mean=sim_mean,
        simulated_std=sim_std,
        simulated_geometric_mean=float(sim_geom),
        mean_match=_within_sim(hist_arith_mean, sim_mean),
        std_match=_within_sim(hist_std, sim_std),
        geometric_mean_match=geometric_mean_match,
        tolerance=tolerance,
    )


def run_simulation(
    returns: Sequence[float],
    initial_balance: float,
    monthly_contribution: float = 0.0,
    horizon_months: int = 120,
    n_simulations: int = 1000,
    blocks: int | None = None,
    percentile_levels: Sequence[float] = DEFAULT_PERCENTILES,
    seed: int | None = None,
    volatility_multiplier: float = 1.0,
) -> dict:
    """High-level helper returning trajectories and percentile bands.

    This is the single entry point the Phase 3/6 API calls. Inputs are the same
    as :func:`simulate_paths`; ``volatility_multiplier`` lets the sentiment
    layer scale the simulated dispersion.
    """
    paths = simulate_paths(
        returns,
        initial_balance=initial_balance,
        monthly_contribution=monthly_contribution,
        horizon_months=horizon_months,
        n_simulations=n_simulations,
        blocks=blocks,
        seed=seed,
        volatility_multiplier=volatility_multiplier,
    )
    bands = path_percentiles(paths, levels=percentile_levels)
    return {
        "paths": paths,
        "percentiles": bands,
        "percentile_levels": list(percentile_levels),
        "horizon_months": horizon_months,
        "n_simulations": n_simulations,
        "seed": seed,
        "volatility_multiplier": volatility_multiplier,
    }


__all__ = [
    "returns_from_prices",
    "volatility_multiplier_from_sentiment",
    "scale_returns_volatility",
    "simulate_paths",
    "path_percentiles",
    "compute_distribution_stats",
    "validate_bootstrap",
    "run_simulation",
    "ValidationReport",
    "DEFAULT_PERCENTILES",
    "NEGATIVE_SENTIMENT_SENSITIVITY",
    "POSITIVE_SENTIMENT_SENSITIVITY",
    "MIN_VOLATILITY_MULTIPLIER",
    "MAX_VOLATILITY_MULTIPLIER",
]