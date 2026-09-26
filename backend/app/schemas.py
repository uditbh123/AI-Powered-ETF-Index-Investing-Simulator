"""Pydantic request/response models for the Phase 3 API."""
from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# --- Input bounds (Stage L4 hostile-input audit) ---------------------------
# Every bound below exists because an audit probe demonstrated a concrete
# failure without it, not as defensive decoration.

#: Longest accepted ticker symbol. Real symbols are <= ~10 chars; the cap stops
#: a multi-kilobyte symbol from being echoed back in a 404 detail message.
MAX_SYMBOL_LENGTH = 32

#: Largest single holding weight. The UI edits weights as percentages and the
#: demo seeder stores percent-scale values (100 = the whole sleeve), so 100 is
#: the natural ceiling. It also stops the weight sum from overflowing to inf:
#: two holdings at 1e308 sum to inf, every normalized weight becomes 0, and the
#: simulation silently returns a zero-variance (flat) fan chart.
MAX_HOLDING_WEIGHT = 100.0

#: Most holdings one portfolio may hold. Caps the request body and, with
#: MAX_HOLDING_WEIGHT, bounds the weight sum at 5000 (no overflow).
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


class HoldingIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=MAX_SYMBOL_LENGTH)
    weight: float = Field(gt=0, le=MAX_HOLDING_WEIGHT)

    @model_validator(mode="after")
    def _check_finite_weight(self) -> "HoldingIn":
        _reject_non_finite(self.weight, "weight")
        return self


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    monthly_contribution: float = Field(default=0.0, ge=0, le=MAX_MONTHLY_CONTRIBUTION)
    holdings: list[HoldingIn] = Field(min_length=1, max_length=MAX_HOLDINGS)

    @model_validator(mode="after")
    def _check_positive_weight_sum(self) -> "PortfolioCreate":
        _reject_non_finite(self.monthly_contribution, "monthly_contribution")
        if sum(h.weight for h in self.holdings) <= 0:
            raise ValueError("holding weights must sum to a positive amount")
        return self


class PortfolioUpdate(BaseModel):
    """Full replacement update: name, contribution, and holdings swap atomically.

    Mirrors create validation (>=1 holding, each weight > 0) and adds the
    production rule the simulator relies on: weights must sum to 1.0 within
    +/- 0.01. The simulation engine re-normalizes weights at read time, but
    enforcing the sum here keeps stored allocations honest for the UI.
    """

    name: str = Field(min_length=1, max_length=120)
    monthly_contribution: float = Field(default=0.0, ge=0, le=MAX_MONTHLY_CONTRIBUTION)
    holdings: list[HoldingIn] = Field(min_length=1, max_length=MAX_HOLDINGS)

    @model_validator(mode="after")
    def _check_weights_sum_to_one(self) -> "PortfolioUpdate":
        _reject_non_finite(self.monthly_contribution, "monthly_contribution")
        if abs(sum(h.weight for h in self.holdings) - 1.0) > 0.01:
            raise ValueError("holding weights must sum to 1.0 (within 0.01)")
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
    "MAX_INITIAL_BALANCE",
    "MAX_MONTHLY_CONTRIBUTION",
    "MAX_BLOCK_MONTHS",
    "MAX_PATH_STEPS",
]