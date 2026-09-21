"""Simulation engine (pure, testable modules independent of the API)."""

from .monte_carlo import (
    DEFAULT_PERCENTILES,
    MAX_VOLATILITY_MULTIPLIER,
    MIN_VOLATILITY_MULTIPLIER,
    NEGATIVE_SENTIMENT_SENSITIVITY,
    POSITIVE_SENTIMENT_SENSITIVITY,
    ValidationReport,
    path_percentiles,
    returns_from_prices,
    run_simulation,
    scale_returns_volatility,
    simulate_paths,
    validate_bootstrap,
    volatility_multiplier_from_sentiment,
)

__all__ = [
    "DEFAULT_PERCENTILES",
    "MAX_VOLATILITY_MULTIPLIER",
    "MIN_VOLATILITY_MULTIPLIER",
    "NEGATIVE_SENTIMENT_SENSITIVITY",
    "POSITIVE_SENTIMENT_SENSITIVITY",
    "ValidationReport",
    "path_percentiles",
    "returns_from_prices",
    "run_simulation",
    "scale_returns_volatility",
    "simulate_paths",
    "validate_bootstrap",
    "volatility_multiplier_from_sentiment",
]