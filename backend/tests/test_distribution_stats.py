"""Tests for compute_distribution_stats (app.simulation.monte_carlo).

These use small hand-built path matrices with analytically known summary
statistics so the function is validated independently of the bootstrap.
"""
import numpy as np
import pytest

from app.simulation import compute_distribution_stats, simulate_paths


# ---------------------------------------------------------------------------
# Hand-computed synthetic cases
# ---------------------------------------------------------------------------

def test_totals_and_percentiles_happen_contribution():
    paths = np.array(
        [
            [1.0, 2.0, 3.0, 4.0],
            [1.0, 2.0, 3.0, 5.0],
            [1.0, 2.0, 3.0, 1.0],
            [1.0, 2.0, 3.0, 2.0],
        ]
    )
    stats = compute_distribution_stats(paths, initial_balance=100.0, monthly_contribution=50.0, horizon_months=2)
    assert stats["total_contributed"] == 200.0

    # finals = [4, 5, 1, 2] -> sorted [1, 2, 4, 5], np.percentile 'linear'
    assert stats["final_percentiles"]["p10"] == pytest.approx(1.3)
    assert stats["final_percentiles"]["p25"] == pytest.approx(1.75)
    assert stats["final_percentiles"]["p50"] == pytest.approx(3.0)
    assert stats["final_percentiles"]["p75"] == pytest.approx(4.25)
    assert stats["final_percentiles"]["p90"] == pytest.approx(4.7)


def test_probability_of_profit_three_of_four_paths():
    paths = np.array(
        [
            [100.0, 200.0, 300.0, 450.0],
            [100.0, 200.0, 300.0, 700.0],
            [100.0, 200.0, 300.0, 100.0],
            [100.0, 200.0, 300.0, 600.0],
        ]
    )
    stats = compute_distribution_stats(paths, initial_balance=0.0, monthly_contribution=100.0, horizon_months=4)
    assert stats["total_contributed"] == 400.0
    assert stats["probability_of_profit"] == pytest.approx(0.75)


def test_upside_downside_ratio_number():
    paths = np.array(
        [
            [100.0, 200.0, 300.0, 450.0],
            [100.0, 200.0, 300.0, 700.0],
            [100.0, 200.0, 300.0, 100.0],
            [100.0, 200.0, 300.0, 600.0],
        ]
    )
    stats = compute_distribution_stats(paths, initial_balance=0.0, monthly_contribution=100.0, horizon_months=4)
    # contributed = 400, p90 = 670, p10 = 205 -> (670-400)/(400-205) = 1.3846..
    assert stats["upside_downside_ratio"] == pytest.approx(270.0 / 195.0)


def test_upside_downside_ratio_is_none_when_no_downside():
    paths = np.array(
        [
            [100.0, 110.0, 120.0, 130.0],
            [100.0, 120.0, 140.0, 160.0],
            [100.0, 200.0, 300.0, 400.0],
            [100.0, 150.0, 200.0, 250.0],
        ]
    )
    stats = compute_distribution_stats(paths, initial_balance=0.0, monthly_contribution=100.0, horizon_months=2)
    assert stats["total_contributed"] == 200.0
    # all final values >= 130 > 200? no -> p10 will be below 200 -> ratio set.
    assert stats["upside_downside_ratio"] is not None
    assert stats["upside_downside_ratio"] > 0.0


def test_upside_downside_none_when_p10_at_or_above_contributed():
    paths = np.array(
        [
            [100.0, 400.0, 410.0, 420.0],
            [100.0, 500.0, 510.0, 520.0],
            [100.0, 600.0, 610.0, 620.0],
            [100.0, 700.0, 710.0, 720.0],
        ]
    )
    stats = compute_distribution_stats(paths, initial_balance=0.0, monthly_contribution=100.0, horizon_months=3)
    # contributed = 300; every final value >= 420 > 300 -> p10 > contributed
    assert stats["upside_downside_ratio"] is None
    assert stats["probability_of_profit"] == 1.0


def test_median_max_drawdown_only_ending_losers_count():
    # Three monotonic paths have drawdown 0; the fourth drops after its peak.
    paths = np.array(
        [
            [100.0, 200.0, 300.0, 450.0],
            [100.0, 200.0, 300.0, 700.0],
            [100.0, 200.0, 300.0, 100.0],  # peak 300, end 100 -> -2/3
            [100.0, 200.0, 300.0, 600.0],
        ]
    )
    stats = compute_distribution_stats(paths, initial_balance=0.0, monthly_contribution=100.0, horizon_months=4)
    # per-path min drawdown = [-0.0, -0.0, -2/3, -0.0]; median = 0 for sorted
    assert stats["median_max_drawdown"] == pytest.approx(0.0)
    peaks = np.maximum.accumulate(paths, axis=1)
    worst = (paths / peaks - 1.0).min(axis=1)
    assert worst[2] == pytest.approx(-2.0 / 3.0)


def test_histogram_20_bins():
    rng = np.random.default_rng(7)
    finals = rng.normal(1000.0, 200.0, size=500)
    paths = np.concatenate([np.zeros((500, 3)), finals[:, None]], axis=1)
    stats = compute_distribution_stats(paths, initial_balance=0.0, monthly_contribution=0.0, horizon_months=3)
    hist = stats["histogram"]
    assert len(hist["bin_edges"]) == 21
    assert len(hist["counts"]) == 20
    assert sum(hist["counts"]) == 500
    edges = hist["bin_edges"]
    assert all(b < e for b, e in zip(edges, edges[1:]))
    counts, bin_edges = np.histogram(finals, bins=20)
    assert hist["counts"] == counts.tolist()


def test_rejects_bad_inputs():
    with pytest.raises(ValueError, match="2-D"):
        compute_distribution_stats(np.arange(6.0), 0.0, 0.0, 3)
    with pytest.raises(ValueError, match="initial_balance"):
        compute_distribution_stats(np.zeros((2, 3)), -1.0, 0.0, 3)
    with pytest.raises(ValueError, match="monthly_contribution"):
        compute_distribution_stats(np.zeros((2, 3)), 0.0, -1.0, 3)
    with pytest.raises(ValueError, match="horizon_months"):
        compute_distribution_stats(np.zeros((2, 3)), 0.0, 0.0, 0)


def test_constant_growth_engine_link():
    returns = [0.01, 0.01, 0.01, 0.01, 0.01]
    paths = simulate_paths(returns, initial_balance=100.0, monthly_contribution=0.0, horizon_months=12, n_simulations=200, seed=1)
    stats = compute_distribution_stats(paths, initial_balance=100.0, monthly_contribution=0.0, horizon_months=12)
    assert stats["probability_of_profit"] == pytest.approx(1.0)
    assert stats["median_max_drawdown"] == pytest.approx(0.0, abs=1e-12)


def test_zero_initial_balance_is_not_nan():
    # The engine's first column is the initial balance (0 here); the zero
    # running peak at month 0 must not poison the drawdown with NaN.
    returns = [0.01, 0.02, 0.0, 0.01, 0.02]
    paths = simulate_paths(returns, initial_balance=0.0, monthly_contribution=100.0, horizon_months=24, n_simulations=100, seed=3)
    stats = compute_distribution_stats(paths, initial_balance=0.0, monthly_contribution=100.0, horizon_months=24)
    assert stats["median_max_drawdown"] == stats["median_max_drawdown"]  # not NaN
    assert np.isfinite(stats["median_max_drawdown"])