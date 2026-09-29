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


def test_insert_in_batch_duplicate_keeps_first_score(db):
    """Within one call the first occurrence wins, not the last."""
    ticker = ticker_dao.get_or_create_ticker(db, "SPY")
    rows = [
        (ticker["id"], "Same headline", "Google News", "2024-08-05", 0.11, "sector"),
        (ticker["id"], "Same headline", "Google News", "2024-08-05", 0.99, "sector"),
    ]
    assert news_dao.insert_sentiment(db, rows) == 1
    stored = news_dao.list_sentiment(db, category="sector")
    assert len(stored) == 1
    assert stored[0]["sentiment_score"] == 0.11


def test_insert_null_source_rows_are_never_deduped(db):
    """NULL source is not equal to NULL source, so each row is kept.

    Pins the SQL three-valued-logic behavior: a row-value ``IN (VALUES ...)``
    comparison must not accidentally start treating NULL sources as dupes.
    """
    rows = [
        (None, "Unattributed", None, "2024-08-05", 0.3, "geopolitical"),
        (None, "Unattributed", None, "2024-08-05", 0.3, "geopolitical"),
    ]
    assert news_dao.insert_sentiment(db, rows) == 2
    assert news_dao.count_sentiment(db) == 2


def test_insert_dedupes_across_calls(db):
    """Re-running ingestion stays idempotent: nothing new on the second pass."""
    ticker = ticker_dao.get_or_create_ticker(db, "SPY")
    rows = [
        (ticker["id"], "H1", "S1", "2024-08-05", 0.5, "sector"),
        (ticker["id"], "H2", "S1", "2024-08-05", 0.5, "sector"),
    ]
    assert news_dao.insert_sentiment(db, rows) == 2
    assert news_dao.insert_sentiment(db, rows) == 0
    assert news_dao.count_sentiment(db) == 2


def test_insert_batches_across_chunk_boundary(db):
    """More rows than one dedupe lookup holds, with a duplicate spanning chunks.

    The lookup is chunked to stay under SQLite's bound-variable limit. A
    headline repeated just past the boundary must still be caught, and all rows
    must land in one call.
    """
    ticker = ticker_dao.get_or_create_ticker(db, "SPY")
    total = 700
    rows = [
        (ticker["id"], f"H{i}", "S1", "2024-08-05", 0.1, "sector")
        for i in range(total)
    ]
    rows.append((ticker["id"], "H699", "S1", "2024-08-05", 0.9, "sector"))
    assert news_dao.insert_sentiment(db, rows) == total
    assert news_dao.count_sentiment(db) == total
    assert news_dao.insert_sentiment(db, rows) == 0


def test_insert_empty_and_fully_duplicate_batches_return_zero(db):
    assert news_dao.insert_sentiment(db, []) == 0
    ticker = ticker_dao.get_or_create_ticker(db, "SPY")
    rows = [(ticker["id"], "H1", "S1", "2024-08-05", 0.5, "sector")]
    assert news_dao.insert_sentiment(db, rows) == 1
    assert news_dao.insert_sentiment(db, rows) == 0


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