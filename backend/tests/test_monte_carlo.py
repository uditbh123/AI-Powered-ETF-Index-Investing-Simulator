"""Tests for the Monte Carlo simulation engine (app.simulation.monte_carlo).

The engine is validated against a naive, analytically solvable baseline:
closed-form compounding and the empirical distribution it bootstraps from.
"""
import numpy as np
import pytest

from app.simulation import (
    path_percentiles,
    returns_from_prices,
    run_simulation,
    simulate_paths,
    validate_bootstrap,
)

N_SIMS = 3000


@pytest.fixture
def synthetic_returns() -> np.ndarray:
    """Fixed, reproducible series of monthly returns (~0.5%/mo, ~2.5% vol)."""
    rng = np.random.default_rng(42)
    return rng.normal(0.005, 0.025, size=240).clip(min=-0.12, max=0.12)


# ---------------------------------------------------------------------------
# returns_from_prices
# ---------------------------------------------------------------------------

def test_returns_from_prices_arithmetic():
    prices = [100.0, 110.0, 99.0]
    assert np.allclose(returns_from_prices(prices), [0.10, -0.10])


@pytest.mark.parametrize("bad", [[100.0], [1.0, 0.0, 2.0], [[1.0, 2.0], [3.0, 4.0]]])
def test_returns_from_prices_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        returns_from_prices(bad)


# ---------------------------------------------------------------------------
# Determinism and shape
# ---------------------------------------------------------------------------

def test_simulation_shape_matches_specification():
    paths = simulate_paths(
        returns=[0.01] * 12,
        initial_balance=1000.0,
        monthly_contribution=100.0,
        horizon_months=12,
        n_simulations=N_SIMS,
    )
    assert paths.shape == (N_SIMS, 13)
    assert np.allclose(paths[:, 0], 1000.0)


def test_seed_makes_simulation_reproducible():
    returns = [0.01, -0.02, 0.03] * 40
    a = simulate_paths(returns, 1000, 100, 120, N_SIMS, seed=7)
    b = simulate_paths(returns, 1000, 100, 120, N_SIMS, seed=7)
    c = simulate_paths(returns, 1000, 100, 120, N_SIMS, seed=8)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_block_bootstrap_shape(synthetic_returns):
    paths = simulate_paths(
        synthetic_returns, 1000, 50, 60, N_SIMS, blocks=6, seed=3
    )
    assert paths.shape == (N_SIMS, 61)
    assert np.all(np.isfinite(paths))


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(initial_balance=-1.0),
        dict(initial_balance=1000.0, monthly_contribution=-1.0),
        dict(initial_balance=1000.0, horizon_months=0),
        dict(initial_balance=1000.0, n_simulations=0),
    ],
)
def test_simulation_rejects_invalid_parameters(kwargs):
    with pytest.raises(ValueError):
        simulate_paths(returns=[0.01] * 12, **kwargs)


# ---------------------------------------------------------------------------
# Closed-form baseline (constant return)
# ---------------------------------------------------------------------------

def test_constant_return_matches_closed_form():
    rate, balance, contribution, months = 0.01, 1000.0, 100.0, 12
    returns = [rate] * months
    paths = simulate_paths(
        returns=returns,
        initial_balance=balance,
        monthly_contribution=contribution,
        horizon_months=months,
        n_simulations=500,
        seed=1,
    )

    g = (1.0 + rate) ** np.arange(1, months + 1)
    expected = g * (balance + contribution * np.cumsum((1.0 + rate) ** -np.arange(1, months + 1)))
    # Every path is identical under a constant return.
    assert np.allclose(paths[-1, 1:], expected, rtol=1e-12)


def test_no_contribution_matches_compound_growth():
    rate, balance, months = 0.02, 5000.0, 36
    returns = [rate] * months
    paths = simulate_paths(returns, initial_balance=balance, horizon_months=months, n_simulations=100)
    assert np.allclose(paths[:, -1], balance * (1.0 + rate) ** months, rtol=1e-12)


# ---------------------------------------------------------------------------
# Statistical validation against the bootstrapped empirical distribution
# ---------------------------------------------------------------------------

def test_bootstrap_matches_empirical_distribution(synthetic_returns):
    report = validate_bootstrap(synthetic_returns, n_simulations=5000, seed=11)
    assert report.mean_match
    assert report.std_match
    assert report.geometric_mean_match
    # Simulated stats converge to the *historical sample*, not the population.
    assert abs(report.simulated_mean - report.historical_mean) < report.tolerance * abs(report.historical_mean)
    assert abs(report.simulated_std - report.historical_std) < report.tolerance * report.historical_std


def test_validation_constant_returns():
    returns = [0.01] * 120
    report = validate_bootstrap(returns, n_simulations=1000, seed=2)
    assert report.mean_match
    assert report.std_match
    assert report.simulated_std == pytest.approx(0.0, abs=1e-12)


def test_validation_rejects_bad_tolerance():
    with pytest.raises(ValueError):
        validate_bootstrap([0.01] * 24, tolerance=1.5)


# ---------------------------------------------------------------------------
# Percentiles and the high-level entry point
# ---------------------------------------------------------------------------

def test_percentiles_shape_and_ordering(synthetic_returns):
    paths = simulate_paths(synthetic_returns, 1000, 50, 60, N_SIMS, seed=5)
    bands = path_percentiles(paths, levels=(5, 50, 95))
    assert bands.shape == (3, 61)
    assert np.all(bands[0] <= bands[1])
    assert np.all(bands[1] <= bands[2])


def test_run_simulation_returns_percentile_trajectories(synthetic_returns):
    result = run_simulation(
        returns=synthetic_returns,
        initial_balance=5000.0,
        monthly_contribution=250.0,
        horizon_months=120,
        n_simulations=2000,
        seed=9,
    )
    assert result["paths"].shape == (2000, 121)
    assert result["percentiles"].shape == (3, 121)
    assert result["percentile_levels"] == [5, 50, 95]
    assert np.all(result["percentiles"] > 0)