"""Simulation engine (pure, testable modules independent of the API)."""

from .monte_carlo import (
    DEFAULT_PERCENTILES,
    ValidationReport,
    path_percentiles,
    returns_from_prices,
    run_simulation,
    simulate_paths,
    validate_bootstrap,
)

__all__ = [
    "DEFAULT_PERCENTILES",
    "ValidationReport",
    "path_percentiles",
    "returns_from_prices",
    "run_simulation",
    "simulate_paths",
    "validate_bootstrap",
]