"""Pydantic request/response models for the Phase 3 API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class HoldingIn(BaseModel):
    symbol: str = Field(min_length=1)
    weight: float = Field(gt=0)


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    monthly_contribution: float = Field(default=0.0, ge=0)
    holdings: list[HoldingIn] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_positive_weight_sum(self) -> "PortfolioCreate":
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
    monthly_contribution: float = Field(default=0.0, ge=0)
    holdings: list[HoldingIn] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_weights_sum_to_one(self) -> "PortfolioUpdate":
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
    initial_balance: float = Field(gt=0)
    horizon_months: int = Field(default=120, ge=1, le=600)
    n_simulations: int = Field(default=1000, ge=50, le=100_000)
    seed: int | None = None
    blocks: int | None = Field(default=None, gt=0)
    use_sentiment: bool = False


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
    initial_balance: float = Field(gt=0)


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
]