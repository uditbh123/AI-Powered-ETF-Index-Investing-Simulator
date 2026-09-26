"""Tests for compute_distribution_stats (app.simulation.monte_carlo).

These use small hand-built path matrices with analytically known summary
statistics so the function is validated independently of the bootstrap.
"""
import math

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
    # Two paths, two steps: one gains 100% then flat, the other loses 50% then
    # flat. Four step returns in total: [+1.0, 0.0, -0.5, 0.0].
    #   mean gain         = (1.0 + 0) / 4 = 0.25
    #   downside deviation= sqrt((0 + 0.25) / 4) = 0.25
    #   ratio             = 1.0
    paths = np.array(
        [
            [100.0, 200.0, 200.0],
            [100.0, 50.0, 50.0],
        ]
    )
    stats = compute_distribution_stats(
        paths, initial_balance=0.0, monthly_contribution=0.0, horizon_months=2
    )
    assert stats["upside_downside_ratio"] == pytest.approx(1.0)


def test_upside_downside_ratio_defined_when_p10_above_contributed():
    # Regression case for the metric that read as blank in the UI. Every final
    # value sits above the book value, which made the old final-value formula's
    # denominator (contributed - p10) negative and the stat null. Each path
    # also dips once, so the monthly-return form has a downside to divide by.
    paths = np.array(
        [
            [100.0, 400.0, 350.0, 420.0],
            [100.0, 500.0, 460.0, 520.0],
            [100.0, 600.0, 570.0, 640.0],
            [100.0, 700.0, 690.0, 760.0],
        ]
    )
    stats = compute_distribution_stats(
        paths, initial_balance=0.0, monthly_contribution=100.0, horizon_months=3
    )
    # contributed = 300 and every final value is >= 420.
    assert stats["probability_of_profit"] == 1.0
    assert stats["upside_downside_ratio"] is not None
    assert stats["upside_downside_ratio"] > 0.0


def test_upside_downside_ratio_is_zero_when_no_gains():
    # Only losing months: the ratio is a defined 0.0, not None and not inf.
    paths = np.array(
        [
            [100.0, 90.0, 80.0, 70.0],
            [100.0, 95.0, 85.0, 75.0],
        ]
    )
    stats = compute_distribution_stats(
        paths, initial_balance=0.0, monthly_contribution=0.0, horizon_months=3
    )
    assert stats["upside_downside_ratio"] == 0.0


def test_upside_downside_ratio_none_when_no_losses():
    # Only gaining months leaves downside deviation at zero, so the ratio is
    # genuinely undefined. This is the one remaining null case.
    paths = np.array(
        [
            [100.0, 110.0, 120.0, 130.0],
            [100.0, 120.0, 140.0, 160.0],
        ]
    )
    stats = compute_distribution_stats(
        paths, initial_balance=0.0, monthly_contribution=0.0, horizon_months=3
    )
    assert stats["upside_downside_ratio"] is None


def test_upside_downside_ratio_handles_zero_opening_balance():
    # initial_balance 0 means step 0 opens on zero and has no defined return;
    # it must be treated neutrally rather than poisoning the mean with NaN.
    paths = np.array(
        [
            [0.0, 100.0, 90.0, 110.0],
            [0.0, 100.0, 120.0, 80.0],
        ]
    )
    stats = compute_distribution_stats(
        paths, initial_balance=0.0, monthly_contribution=100.0, horizon_months=3
    )
    ratio = stats["upside_downside_ratio"]
    assert ratio is not None
    assert not math.isnan(ratio)
    assert ratio > 0.0


def test_upside_downside_ratio_none_for_single_column_matrix():
    # One column means no step returns at all; nothing to divide.
    paths = np.array([[100.0], [120.0], [80.0]])
    stats = compute_distribution_stats(
        paths, initial_balance=0.0, monthly_contribution=0.0, horizon_months=1
    )
    assert stats["upside_downside_ratio"] is None


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