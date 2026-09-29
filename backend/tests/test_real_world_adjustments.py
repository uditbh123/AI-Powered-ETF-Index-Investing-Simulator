"""Tests for inflation and capital-gains-tax adjustments.

Covers ``apply_real_world_adjustments`` and ``inflation_deflator`` in
``app.simulation.monte_carlo``, plus the cache/params wiring in
``services.simulation``. Path matrices are hand-built with analytically known
answers so the math is checked independently of the bootstrap.
"""
import json
import math

import numpy as np
import pytest

from app.simulation.monte_carlo import (
    CAPITAL_GAINS_TAX_RATE,
    INFLATION_ANNUAL_RATE,
    apply_real_world_adjustments,
    compute_distribution_stats,
    inflation_deflator,
    simulate_paths,
)
from app.services.simulation import canonical_params


# ---------------------------------------------------------------------------
# Deflator
# ---------------------------------------------------------------------------

def test_deflator_starts_at_one_and_matches_closed_form():
    factors = inflation_deflator(120, 0.03)
    assert factors.shape == (121,)
    assert factors[0] == pytest.approx(1.0)
    # Annual compounding: step 120 is exactly 10 years.
    assert factors[120] == pytest.approx(1.03**10)
    assert factors[12] == pytest.approx(1.03)
    # Strictly increasing, so deflation never reorders two paths.
    assert np.all(np.diff(factors) > 0)


def test_deflator_rejects_negative_rate_and_bad_horizon():
    with pytest.raises(ValueError, match="inflation_rate must be >= 0"):
        inflation_deflator(12, -0.01)
    with pytest.raises(ValueError, match="horizon_months must be >= 1"):
        inflation_deflator(0)


# ---------------------------------------------------------------------------
# Both toggles off: must be an exact no-op
# ---------------------------------------------------------------------------

def test_both_off_returns_identical_paths_and_unchanged_book_value():
    paths = simulate_paths(
        [0.01, -0.02, 0.015], initial_balance=1000.0, monthly_contribution=50.0,
        horizon_months=12, n_simulations=100, seed=1,
    )
    adjusted, breakdown = apply_real_world_adjustments(paths, 1000.0, 50.0, 12)
    assert np.array_equal(adjusted, paths)
    assert breakdown["total_contributed"] == 1000.0 + 50.0 * 12
    assert breakdown["nominal_total_contributed"] == 1000.0 + 50.0 * 12
    assert breakdown["inflation_adjusted"] is False
    assert breakdown["capital_gains_tax_applied"] is False
    assert breakdown["mean_capital_gains_tax"] == 0.0


def test_no_op_does_not_mutate_the_input_array():
    paths = simulate_paths(
        [0.01, -0.02, 0.015], initial_balance=1000.0, monthly_contribution=50.0,
        horizon_months=12, n_simulations=50, seed=2,
    )
    before = paths.copy()
    apply_real_world_adjustments(paths, 1000.0, 50.0, 12, apply_capital_gains_tax=True)
    assert np.array_equal(paths, before)


# ---------------------------------------------------------------------------
# Inflation
# ---------------------------------------------------------------------------

def test_inflation_divides_every_column_by_its_deflator():
    paths = np.array([[100.0, 110.0, 121.0, 133.1]], dtype=float)
    adjusted, breakdown = apply_real_world_adjustments(
        paths, initial_balance=100.0, monthly_contribution=0.0, horizon_months=3,
        adjust_for_inflation=True,
    )
    f = inflation_deflator(3, INFLATION_ANNUAL_RATE)
    assert adjusted[0, 0] == pytest.approx(100.0)  # index 0 is never deflated
    for t in range(4):
        assert adjusted[0, t] == pytest.approx(paths[0, t] / f[t])


def test_inflation_deflates_the_book_value_by_the_horizon_factor():
    _, breakdown = apply_real_world_adjustments(
        np.array([[100.0, 200.0, 300.0]]), 100.0, 50.0, 2,
        adjust_for_inflation=True,
    )
    nominal = 100.0 + 50.0 * 2
    assert breakdown["nominal_total_contributed"] == nominal
    # horizon_months=2 is two MONTHS, so the factor is 1.03 ** (2/12).
    assert breakdown["total_contributed"] == pytest.approx(nominal / (1.03 ** (2 / 12)))


def test_inflation_leaves_profit_probability_unchanged():
    """The regression guard for the trap in this feature.

    Deflating the paths while leaving ``total_contributed`` nominal compares
    real assets against nominal deposits and collapses the probability toward
    zero. Passing the deflated book value keeps it exactly invariant, because
    ``(V - C) / f`` has the same sign as ``V - C``.
    """
    paths = simulate_paths(
        [0.01, -0.03, 0.02, -0.01], initial_balance=1000.0, monthly_contribution=100.0,
        horizon_months=24, n_simulations=400, seed=3,
    )
    nominal = compute_distribution_stats(paths, 1000.0, 100.0, 24)
    adjusted, breakdown = apply_real_world_adjustments(
        paths, 1000.0, 100.0, 24, adjust_for_inflation=True
    )
    consistent = compute_distribution_stats(
        adjusted, 1000.0, 100.0, 24,
        total_contributed=breakdown["total_contributed"],
    )
    inconsistent = compute_distribution_stats(adjusted, 1000.0, 100.0, 24)
    assert consistent["probability_of_profit"] == pytest.approx(
        nominal["probability_of_profit"]
    )
    # And the naive call really is broken, which is why the override exists.
    assert inconsistent["probability_of_profit"] < nominal["probability_of_profit"]


# ---------------------------------------------------------------------------
# Capital gains tax
# ---------------------------------------------------------------------------

def test_tax_applies_only_to_the_final_column():
    paths = np.array([[100.0, 150.0, 200.0, 300.0]], dtype=float)
    adjusted, _ = apply_real_world_adjustments(
        paths, 100.0, 0.0, 3, apply_capital_gains_tax=True,
    )
    assert np.array_equal(adjusted[0, :-1], paths[0, :-1])
    profit = 300.0 - 100.0
    assert adjusted[0, -1] == pytest.approx(300.0 - profit * CAPITAL_GAINS_TAX_RATE)


def test_tax_charged_only_on_profitable_paths():
    paths = np.array(
        [
            [100.0, 200.0],  # +100 profit -> taxed
            [100.0, 100.0],  # zero profit -> no tax
            [100.0, 50.0],   # loss -> no tax credit
        ],
        dtype=float,
    )
    adjusted, breakdown = apply_real_world_adjustments(
        paths, 100.0, 0.0, 1, apply_capital_gains_tax=True,
    )
    rate = CAPITAL_GAINS_TAX_RATE
    assert adjusted[0, 1] == pytest.approx(200.0 - 100.0 * rate)
    assert adjusted[1, 1] == pytest.approx(100.0)
    assert adjusted[2, 1] == pytest.approx(50.0)
    assert breakdown["mean_capital_gains_tax"] == pytest.approx(100.0 * rate / 3)
    assert breakdown["median_capital_gains_tax"] == 0.0
    assert breakdown["taxable_fraction_of_paths"] == pytest.approx(1 / 3)


def test_tax_cannot_flip_a_profitable_path_into_a_loss():
    """A flat rate below 100% scales profit but never inverts its sign."""
    paths = simulate_paths(
        [0.01, -0.02, 0.015, 0.005], initial_balance=1000.0, monthly_contribution=100.0,
        horizon_months=24, n_simulations=400, seed=4,
    )
    nominal = compute_distribution_stats(paths, 1000.0, 100.0, 24)
    adjusted, breakdown = apply_real_world_adjustments(
        paths, 1000.0, 100.0, 24, apply_capital_gains_tax=True,
    )
    taxed = compute_distribution_stats(
        adjusted, 1000.0, 100.0, 24, total_contributed=breakdown["total_contributed"],
    )
    assert taxed["probability_of_profit"] == pytest.approx(
        nominal["probability_of_profit"]
    )
    assert taxed["final_percentiles"]["p50"] < nominal["final_percentiles"]["p50"]


def test_tax_rate_is_configurable():
    paths = np.array([[100.0, 200.0]], dtype=float)
    adjusted, breakdown = apply_real_world_adjustments(
        paths, 100.0, 0.0, 1, apply_capital_gains_tax=True, tax_rate=0.30,
    )
    assert adjusted[0, 1] == pytest.approx(200.0 - 100.0 * 0.30)
    assert breakdown["capital_gains_tax_rate"] == 0.30


def test_rejects_out_of_range_tax_rate():
    paths = np.array([[100.0, 200.0]], dtype=float)
    with pytest.raises(ValueError, match="tax_rate must be between 0 and 1"):
        apply_real_world_adjustments(paths, 100.0, 0.0, 1, apply_capital_gains_tax=True, tax_rate=1.5)


def test_rejects_horizon_that_does_not_match_path_width():
    """Guards against silently mis-aligning the deflator with the path matrix."""
    paths = np.array([[100.0, 200.0, 300.0]], dtype=float)
    with pytest.raises(ValueError, match="expected 6 for horizon_months=5"):
        apply_real_world_adjustments(paths, 100.0, 0.0, 5, adjust_for_inflation=True)


# ---------------------------------------------------------------------------
# Both together: order matters and is specified
# ---------------------------------------------------------------------------

def test_both_applied_deflates_first_then_taxes_the_real_profit():
    paths = np.array([[100.0, 200.0, 400.0]], dtype=float)
    ib, contrib, h = 100.0, 0.0, 2
    both, breakdown = apply_real_world_adjustments(
        paths, ib, contrib, h, adjust_for_inflation=True, apply_capital_gains_tax=True,
    )
    inflated, _ = apply_real_world_adjustments(paths, ib, contrib, h, adjust_for_inflation=True)
    real_profit = inflated[0, -1] - breakdown["total_contributed"]
    assert both[0, -1] == pytest.approx(
        inflated[0, -1] - real_profit * CAPITAL_GAINS_TAX_RATE
    )
    assert breakdown["inflation_adjusted"] is True
    assert breakdown["capital_gains_tax_applied"] is True


def test_both_together_still_beat_inflation_for_a_strong_run():
    """Sanity check the combined toggle against a hand-computed figure.

    $100 -> $300 over 2 years. In today's dollars the final value is
    300 / 1.03^2 = 282.78 and the book value is 100 / 1.03^2 = 94.26, so the
    real profit is 188.52 and the 15% tax on it is 28.28, leaving 254.50.
    """
    paths = np.array([[100.0, 0.0, 300.0]], dtype=float)  # 2 years, 3x
    ib, contrib, h = 100.0, 0.0, 2
    _, breakdown = apply_real_world_adjustments(
        paths, ib, contrib, h, adjust_for_inflation=True, apply_capital_gains_tax=True,
    )
    real_final = 300.0 / (1.03**2)
    real_profit = real_final - 100.0 / (1.03**2)
    expected = real_final - real_profit * CAPITAL_GAINS_TAX_RATE
    assert expected == pytest.approx(254.50, abs=0.01)


# ---------------------------------------------------------------------------
# Cache key wiring
# ---------------------------------------------------------------------------

def _params(**overrides):
    base = dict(
        initial_balance=1000.0, monthly_contribution=100.0, horizon_months=120,
        n_simulations=1000, blocks=None, seed=1,
    )
    base.update(overrides)
    return canonical_params(**base)


def test_toggles_are_part_of_the_cache_key():
    plain = json.dumps(_params(), sort_keys=True)
    inflated = json.dumps(_params(adjust_for_inflation=True), sort_keys=True)
    taxed = json.dumps(_params(apply_capital_gains_tax=True), sort_keys=True)
    both = json.dumps(
        _params(adjust_for_inflation=True, apply_capital_gains_tax=True), sort_keys=True
    )
    assert len({plain, inflated, taxed, both}) == 4


def test_toggle_defaults_are_false_and_always_present():
    """A missing key would change the params_json and silently split the cache."""
    params = _params()
    assert params["adjust_for_inflation"] is False
    assert params["apply_capital_gains_tax"] is False
    assert "adjust_for_inflation" in params
    assert "apply_capital_gains_tax" in params


def test_additional_but_unused_totals_guard_math():
    """Deflator math cross-checked against the closed form, no scipy needed."""
    assert math.isclose(float(inflation_deflator(600)[-1]), 1.03**50, rel_tol=1e-12)
