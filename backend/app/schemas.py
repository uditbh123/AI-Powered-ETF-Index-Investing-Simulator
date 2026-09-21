"""Pydantic request/response models for the Phase 3 API."""
from __future__ import annotations

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


class SimulationRequest(BaseModel):
    initial_balance: float = Field(gt=0)
    horizon_months: int = Field(default=120, ge=1, le=600)
    n_simulations: int = Field(default=1000, ge=50, le=100_000)
    seed: int | None = None
    blocks: int | None = Field(default=None, gt=0)
    use_sentiment: bool = False


__all__ = [
    "HoldingIn",
    "PortfolioCreate",
    "TickerOut",
    "PricePoint",
    "TickerPricesOut",
    "PortfolioOut",
    "SimulationRequest",
]