"""Pydantic request/response models for the Phase 3 API."""
from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# --- Input bounds (Stage L4 hostile-input audit) ---------------------------
# Every bound below exists because an audit probe demonstrated a concrete
# failure without it, not as defensive decoration.

#: Longest accepted ticker symbol. Real symbols are <= ~10 chars; the cap stops
#: a multi-kilobyte symbol from being echoed back in a 404 detail message.
MAX_SYMBOL_LENGTH = 32

#: Largest single holding weight. The weight convention is FRACTIONS: a whole
#: sleeve is 1.0, so 1.0 is the ceiling and the floor is 0 (exclusive). This
#: supersedes the interim ``<= 100`` cap from the Stage L4 audit, which only
#: existed to accommodate percent-scale seeds.
#:
#: The bound is also the overflow guard the 100 cap was invented for: two
#: holdings at 1e308 used to sum to inf, every normalized weight became 0, and
#: the simulation silently returned a zero-variance (flat) fan chart. With
#: ``le=1.0`` the sum is bounded by MAX_HOLDINGS, so inf is unreachable.
MAX_HOLDING_WEIGHT = 1.0

#: How far a portfolio's holding weights may drift from summing to exactly 1.0.
#: Absorbs float drift (0.1 + 0.2 + 0.7) without letting a genuinely
#: unbalanced portfolio through.
WEIGHT_SUM_TOLERANCE = 0.01

#: Most holdings one portfolio may hold. Caps the request body and, with
#: MAX_HOLDING_WEIGHT, bounds the weight sum at 50 (no overflow).
MAX_HOLDINGS = 50

#: Largest starting balance / monthly contribution accepted, in dollars. The UI
#: allows at most 500,000 and 2,000 respectively. Without a ceiling a
#: near-float-max balance compounds to inf mid-simulation and the client
#: receives a raw numpy message ("autodetected range of [...] is not finite")
#: instead of a validation error.
MAX_INITIAL_BALANCE = 1e12
MAX_MONTHLY_CONTRIBUTION = 1e9

#: Longest block-bootstrap block, in months (60 months = 5 years). The block
#: branch of ``monte_carlo._draw_returns`` materializes an
#: (n_simulations, ceil(steps / blocks), blocks) index matrix, so an unbounded
#: ``blocks`` is a memory-exhaustion vector: blocks=1e9 asked for an 800 GB
#: allocation and returned a 500 after 75 seconds. A block longer than the
#: horizon is also meaningless -- it degenerates to the i.i.d. resample.
MAX_BLOCK_MONTHS = 60

#: Ceiling on n_simulations * horizon_months, the engine's real work factor.
#: Measured on this machine: 3e7 path-steps took 3.7s and 6e7 took 18.4s (well
#: past the 5s per-request budget) at several hundred MB of peak RSS. 2e7 keeps
#: the worst case near 2.5s while still allowing every combination the UI can
#: produce (it never sends n_simulations, so the 1000 default applies: the
#: largest UI run is 1000 x 600 = 6e5).
MAX_PATH_STEPS = 20_000_000


def _reject_non_finite(value: float, field: str) -> None:
    """Raise if a float is NaN/inf.

    Pydantic's ``gt``/``le`` constraints already reject both (every comparison
    against NaN is False), but stating it explicitly keeps the rule readable
    and survives a future loosening of the numeric bounds.
    """
    if not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number")


def _check_weight_convention(holdings: Sequence["HoldingIn"]) -> None:
    """Enforce the single weight convention: fractions in (0, 1] summing to 1.0.

    Per-holding bounds (finite, ``0 < w <= 1``) are declared on
    ``HoldingIn.weight``; this checks the aggregate. Both ``PortfolioCreate`` and
    ``PortfolioUpdate`` call it, so the two endpoints cannot drift apart again.

    Why the sum matters as well as the per-weight ceiling: a percent-scale
    payload such as ``[{"SPY": 60}, {"QQQ": 40}]`` passes any per-weight check
    on its own and looks like a plausible request, but the engine renormalizes,
    so it silently becomes a 50/50 portfolio instead of the 60/40 that was
    asked for. Rejecting it is the only way the caller finds out.

    ``math.fsum`` is used rather than ``sum`` so the tolerance compares against
    an exactly-rounded total.
    """
    total = math.fsum(h.weight for h in holdings)
    if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise ValueError(
            "holding weights must be fractions in (0, 1] that sum to 1.0 "
            f"(within {WEIGHT_SUM_TOLERANCE}); got a total of {total:.6g} from "
            f"{len(holdings)} holding(s) -- send 0.6 for 60%, not 60"
        )


def _reject_non_finite_contribution(contribution: float) -> None:
    _reject_non_finite(contribution, "monthly_contribution")


class HoldingIn(BaseModel):
    """One holding. ``weight`` is a FRACTION: 0.6 means 60% of the sleeve.

    The bound is ``(0, MAX_HOLDING_WEIGHT]`` = ``(0, 1.0]``. A 0 weight is
    rejected because the holding would be stored but contribute nothing.
    """

    symbol: str = Field(min_length=1, max_length=MAX_SYMBOL_LENGTH)
    weight: float = Field(gt=0, le=MAX_HOLDING_WEIGHT)

    @field_validator("weight", mode="before")
    @classmethod
    def _explain_percent_scale(cls, value: object) -> object:
        """Name the percent-scale mistake instead of just tripping ``le``.

        ``le=1.0`` alone rejects 60.0 with "Input should be less than or equal
        to 1" -- true, but it leaves the caller guessing whether they sent the
        wrong number or the wrong unit. Since the contract is fractions, say
        which fraction they probably meant.
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return value
        if math.isfinite(value) and value > MAX_HOLDING_WEIGHT:
            scaled = value / 100.0
            hint = (
                f"; {scaled:g} (i.e. {value:g}%) looks right if you meant a percentage"
                if 0.0 < scaled <= 1.0
                else ""
            )
            raise ValueError(
                f"weight must be a fraction in (0, {MAX_HOLDING_WEIGHT:g}]{hint}"
            )
        return value

    @model_validator(mode="after")
    def _check_finite_weight(self) -> "HoldingIn":
        _reject_non_finite(self.weight, "weight")
        return self


class PortfolioCreate(BaseModel):
    """A new portfolio. Holding weights are fractions summing to 1.0.

    Validation is identical to :class:`PortfolioUpdate` by construction: both
    call ``_check_weight_convention``, so a portfolio that creates cleanly can
    always be re-PATCHed with its own stored weights, and vice versa.
    """

    name: str = Field(min_length=1, max_length=120)
    monthly_contribution: float = Field(default=0.0, ge=0, le=MAX_MONTHLY_CONTRIBUTION)
    holdings: list[HoldingIn] = Field(min_length=1, max_length=MAX_HOLDINGS)

    @model_validator(mode="after")
    def _check_weights(self) -> "PortfolioCreate":
        _reject_non_finite_contribution(self.monthly_contribution)
        _check_weight_convention(self.holdings)
        return self


class PortfolioUpdate(BaseModel):
    """Full replacement update: name, contribution, and holdings swap atomically.

    Mirrors create validation exactly (>=1 holding, each weight a fraction in
    (0, 1], weights summing to 1.0 within 0.01). The simulation engine still
    re-normalizes weights at read time, but that is defense-in-depth: nothing
    should reach it unvalidated.
    """

    name: str = Field(min_length=1, max_length=120)
    monthly_contribution: float = Field(default=0.0, ge=0, le=MAX_MONTHLY_CONTRIBUTION)
    holdings: list[HoldingIn] = Field(min_length=1, max_length=MAX_HOLDINGS)

    @model_validator(mode="after")
    def _check_weights(self) -> "PortfolioUpdate":
        _reject_non_finite_contribution(self.monthly_contribution)
        _check_weight_convention(self.holdings)
        return self


class TickerOut(BaseModel):
    symbol: str
    name: str | None
    sector: str | None
    price_rows: int
    first_date: str | None
    last_date: str | None


class PricePoint(BaseModel):
    date: str
    close: float
    volume: int | None


class TickerPricesOut(BaseModel):
    symbol: str
    name: str | None
    sector: str | None
    prices: list[PricePoint]


class PortfolioOut(BaseModel):
    id: int
    name: str
    monthly_contribution: float
    holdings: list[dict]
    created_at: str | None = None


class SimulationRequest(BaseModel):
    initial_balance: float = Field(gt=0, le=MAX_INITIAL_BALANCE)
    horizon_months: int = Field(default=120, ge=1, le=600)
    n_simulations: int = Field(default=1000, ge=50, le=100_000)
    # seed is bounded rather than left to numpy: a negative seed surfaced the
    # raw ValueError text ("expected non-negative integer") as the 400 detail.
    seed: int | None = Field(default=None, ge=0)
    blocks: int | None = Field(default=None, ge=1, le=MAX_BLOCK_MONTHS)
    use_sentiment: bool = False

    @model_validator(mode="after")
    def _check_workload(self) -> "SimulationRequest":
        _reject_non_finite(self.initial_balance, "initial_balance")
        steps = self.n_simulations * self.horizon_months
        if steps > MAX_PATH_STEPS:
            raise ValueError(
                f"n_simulations * horizon_months must be <= {MAX_PATH_STEPS:,} "
                f"(got {steps:,}: {self.n_simulations:,} paths x "
                f"{self.horizon_months} months); lower n_simulations or the horizon"
            )
        return self


class HeadlineOut(BaseModel):
    published_at: str | None
    source: str | None
    headline: str
    sentiment_score: float | None


class NewsFeedOut(BaseModel):
    category: str
    days: int
    n_headlines: int
    aggregate_score: float | None
    headlines: list[HeadlineOut]


class ScreenerOut(BaseModel):
    symbol: str
    name: str | None
    sector: str | None
    latest_close: float
    prev_close: float | None
    one_day_change_pct: float | None
    one_year_total_return_pct: float | None
    annualized_volatility_pct: float | None
    max_drawdown_pct: float


class CrisisReplayRequest(BaseModel):
    crisis: Literal["dot_com_2000", "gfc_2008", "covid_2020"]
    initial_balance: float = Field(gt=0, le=MAX_INITIAL_BALANCE)

    @model_validator(mode="after")
    def _check_finite_balance(self) -> "CrisisReplayRequest":
        _reject_non_finite(self.initial_balance, "initial_balance")
        return self


__all__ = [
    "HoldingIn",
    "PortfolioCreate",
    "PortfolioUpdate",
    "TickerOut",
    "PricePoint",
    "TickerPricesOut",
    "PortfolioOut",
    "SimulationRequest",
    "HeadlineOut",
    "NewsFeedOut",
    "ScreenerOut",
    "CrisisReplayRequest",
    "MAX_SYMBOL_LENGTH",
    "MAX_HOLDING_WEIGHT",
    "MAX_HOLDINGS",
    "WEIGHT_SUM_TOLERANCE",
    "MAX_INITIAL_BALANCE",
    "MAX_MONTHLY_CONTRIBUTION",
    "MAX_BLOCK_MONTHS",
    "MAX_PATH_STEPS",
]