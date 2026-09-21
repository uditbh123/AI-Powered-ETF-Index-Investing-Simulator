"""Tests for the tickers and prices DAO layers."""
import pytest

from app.dao import prices as price_dao
from app.dao import tickers as ticker_dao
from app.data.ticker_catalog import DEFAULT_TICKERS
from app.database import get_connection


def test_get_or_create_ticker_is_idempotent(db):
    first = ticker_dao.get_or_create_ticker(
        db, symbol="SPY", name="SPDR S&P 500 ETF", sector="US Large-Cap Equity"
    )
    second = ticker_dao.get_or_create_ticker(db, symbol="SPY")
    assert first["id"] == second["id"]
    assert first["symbol"] == "SPY"
    assert first["name"] == "SPDR S&P 500 ETF"


def test_list_tickers_orders_by_symbol(db):
    ticker_dao.get_or_create_ticker(db, symbol="QQQ")
    ticker_dao.get_or_create_ticker(db, symbol="SPY")
    symbols = [row["symbol"] for row in ticker_dao.list_tickers(db)]
    assert symbols == ["QQQ", "SPY"]


def test_upsert_catalog_seeds_and_is_idempotent(db):
    result = ticker_dao.upsert_catalog(db, DEFAULT_TICKERS)
    assert result == {"created": len(DEFAULT_TICKERS), "existing": 0}
    again = ticker_dao.upsert_catalog(db, DEFAULT_TICKERS)
    assert again == {"created": 0, "existing": len(DEFAULT_TICKERS)}


def test_upsert_daily_prices_skips_existing_dates(db):
    ticker = ticker_dao.get_or_create_ticker(db, "SPY")
    rows = [("2024-01-02", 100.0, 1_000_000), ("2024-01-03", 101.5, 1_200_000)]

    first = price_dao.upsert_daily_prices(db, ticker["id"], rows)
    assert first == 2

    dup = price_dao.upsert_daily_prices(db, ticker["id"], rows + [("2024-01-04", 102.0, 900_000)])
    assert dup == 1  # both existing dates ignored, only the new date inserted


def test_get_price_history_range_and_order(db):
    ticker = ticker_dao.get_or_create_ticker(db, "QQQ")
    rows = [
        ("2024-01-02", 400.0, 50_000),
        ("2024-01-03", 405.0, 60_000),
        ("2024-01-04", 402.0, 55_000),
    ]
    price_dao.upsert_daily_prices(db, ticker["id"], rows)

    all_rows = price_dao.get_price_history(db, ticker["id"])
    assert [r["date"] for r in all_rows] == ["2024-01-02", "2024-01-03", "2024-01-04"]

    subset = price_dao.get_price_history(db, ticker["id"], start="2024-01-03")
    assert [r["date"] for r in subset] == ["2024-01-03", "2024-01-04"]

    recent = price_dao.get_price_history(db, ticker["id"], limit=2)
    assert [r["date"] for r in recent] == ["2024-01-03", "2024-01-04"]


def test_count_prices(db):
    ticker = ticker_dao.get_or_create_ticker(db, "GLD")
    other = ticker_dao.get_or_create_ticker(db, "TLT")
    price_dao.upsert_daily_prices(db, ticker["id"], [("2024-01-02", 200.0, 1_000_000)])
    price_dao.upsert_daily_prices(db, other["id"], [("2024-01-02", 90.0, 5_000_000)])

    assert price_dao.count_prices(db) == 2
    assert price_dao.count_prices(db, ticker_id=ticker["id"]) == 1