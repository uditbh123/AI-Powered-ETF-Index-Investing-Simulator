"""Fixed catalog of ETFs and indices used by the simulator.

This is the "fixed list" the Phase 1 ingestion pulls. Symbols map exactly to
yfinance tickers (indices use the caret prefix, e.g. ^GSPC).
"""
from __future__ import annotations

from typing import TypedDict


class TickerInfo(TypedDict):
    symbol: str
    name: str
    sector: str


DEFAULT_TICKERS: list[TickerInfo] = [
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "sector": "US Large-Cap Equity"},
    {"symbol": "VOO", "name": "Vanguard S&P 500 ETF", "sector": "US Large-Cap Equity"},
    {"symbol": "VTI", "name": "Vanguard Total Stock Market ETF", "sector": "US Total Market"},
    {"symbol": "QQQ", "name": "Invesco QQQ Trust", "sector": "US Large-Cap Growth"},
    {"symbol": "IWM", "name": "iShares Russell 2000 ETF", "sector": "US Small-Cap Equity"},
    {"symbol": "VXUS", "name": "Vanguard Total International Stock ETF", "sector": "International Equity"},
    {"symbol": "EEM", "name": "iShares MSCI Emerging Markets ETF", "sector": "Emerging Markets Equity"},
    {"symbol": "BND", "name": "Vanguard Total Bond Market ETF", "sector": "US Bonds"},
    {"symbol": "TLT", "name": "iShares 20+ Year Treasury Bond ETF", "sector": "US Long-Term Treasuries"},
    {"symbol": "GLD", "name": "SPDR Gold Shares", "sector": "Commodities"},
    {"symbol": "^GSPC", "name": "S&P 500 Index", "sector": "Index - US Large-Cap"},
    {"symbol": "^IXIC", "name": "NASDAQ Composite Index", "sector": "Index - US Broad Tech"},
    {"symbol": "^DJI", "name": "Dow Jones Industrial Average", "sector": "Index - US Large-Cap"},
]

SYMBOLS = [t["symbol"] for t in DEFAULT_TICKERS]


def catalog_by_symbol() -> dict[str, TickerInfo]:
    return {t["symbol"]: t for t in DEFAULT_TICKERS}


__all__ = ["DEFAULT_TICKERS", "TickerInfo", "SYMBOLS", "catalog_by_symbol"]