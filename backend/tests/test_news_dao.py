"""Tests for the news_sentiment DAO layer."""
from app.dao import news as news_dao
from app.dao import tickers as ticker_dao


def test_insert_and_count_sentiment(db):
    ticker = ticker_dao.get_or_create_ticker(db, "SPY", "SPDR S&P 500 ETF", "Equity")
    rows = [
        (ticker["id"], "Stocks rally hard", "Google News", "2024-08-05", 0.8, "sector"),
        (None, "Fed holds rates steady", "MarketWatch", "2024-08-06", -0.2, "geopolitical"),
    ]
    assert news_dao.insert_sentiment(db, rows) == 2
    assert news_dao.count_sentiment(db) == 2
    assert news_dao.count_sentiment(db, category="sector") == 1
    assert news_dao.count_sentiment(db, category="geopolitical") == 1
    assert news_dao.count_sentiment(db, ticker_id=ticker["id"]) == 1


def test_insert_skips_exact_duplicate(db):
    ticker = ticker_dao.get_or_create_ticker(db, "SPY")
    rows = [
        (ticker["id"], "Same headline", "Google News", "2024-08-05", 0.5, "sector"),
        (ticker["id"], "Same headline", "Google News", "2024-08-05", 0.9, "sector"),
        (ticker["id"], "Same headline", "Different Source", "2024-08-05", 0.4, "sector"),
    ]
    assert news_dao.insert_sentiment(db, rows) == 2  # third row: different source -> kept


def test_insert_geopolitical_allows_null_ticker(db):
    rows = [
        (None, "Geopolitics news", "Reuters", "2024-08-05", -0.7, "geopolitical"),
    ]
    assert news_dao.insert_sentiment(db, rows) == 1
    rows_back = news_dao.list_sentiment(db, category="geopolitical")
    assert rows_back[0]["ticker_id_or_null"] is None
    assert rows_back[0]["sentiment_score"] == -0.7


def test_list_sentiment_filters_and_orders(db):
    ticker = ticker_dao.get_or_create_ticker(db, "QQQ")
    rows = [
        (ticker["id"], "H1", "S1", "2024-08-01", 0.1, "sector"),
        (ticker["id"], "H2", "S2", "2024-08-03", 0.2, "sector"),
        (ticker["id"], "H3", "S3", "2024-08-02", 0.3, "sector"),
        (None, "Geo", "S4", "2024-08-01", 0.5, "geopolitical"),
    ]
    news_dao.insert_sentiment(db, rows)

    sector = news_dao.list_sentiment(db, category="sector", ticker_id=ticker["id"])
    assert [r["headline"] for r in sector] == ["H1", "H3", "H2"]  # date ordered

    window = news_dao.list_sentiment(db, start="2024-08-02")
    assert all(r["published_at"] >= "2024-08-02" for r in window)
    assert len(window) == 2  # H2, H3; Geo (2024-08-01) is excluded