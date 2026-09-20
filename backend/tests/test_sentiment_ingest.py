"""End-to-end tests for the sentiment ingest pipeline (mocked fetch + scorer)."""
from app.dao import news as news_dao
from app.dao import tickers as ticker_dao
from app.scripts.sentiment_ingest import run_pipeline, select_sources


def make_items():
    return [
        {
            "category": "sector",
            "symbol": "SPY",
            "source": "Google News",
            "headline": "S&P 500 notches record high",
            "published_at": "2024-08-05",
            "url": "http://x/1",
            "summary": "Stocks rallied.",
        },
        {
            "category": "geopolitical",
            "symbol": None,
            "source": "MarketWatch",
            "headline": "Fed signals patience on rates",
            "published_at": "2024-08-05",
            "url": "http://x/2",
            "summary": "Central bank held.",
        },
    ]


def fake_fetcher(items):
    def fetcher(sources, max_items_per_feed=None):
        return items
    return fetcher


def fake_scorer(texts):
    return [round(len(t) / 100, 2) for t in texts]


def test_run_pipeline_persists_scored_headlines(db):
    ticker_dao.get_or_create_ticker(db, "SPY", "SPDR S&P 500 ETF", "Equity")
    summary = run_pipeline(
        db,
        [{}],
        fetcher=fake_fetcher(make_items()),
        scorer=fake_scorer,
    )
    assert summary["fetched"] == 2
    assert summary["scored"] == 2
    assert summary["inserted"] == 2
    assert news_dao.count_sentiment(db) == 2

    spy = news_dao.list_sentiment(db, category="sector")
    assert spy[0]["ticker_id_or_null"] is not None
    assert 0 <= spy[0]["sentiment_score"] <= 1


def test_run_pipeline_is_idempotent(db):
    ticker_dao.get_or_create_ticker(db, "SPY")
    first = run_pipeline(
        db,
        [{}],
        fetcher=fake_fetcher(make_items()),
        scorer=fake_scorer,
    )
    assert first["inserted"] == 2
    second = run_pipeline(
        db,
        [{}],
        fetcher=fake_fetcher(make_items()),
        scorer=fake_scorer,
    )
    assert second["fetched"] == 2
    assert second["inserted"] == 0
    assert news_dao.count_sentiment(db) == 2


def test_run_pipeline_dry_run_persists_nothing(db):
    summary = run_pipeline(
        db,
        [{}],
        fetcher=fake_fetcher(make_items()),
        scorer=fake_scorer,
        persist=False,
    )
    assert summary["fetched"] == 2
    assert summary["inserted"] == 0
    assert news_dao.count_sentiment(db) == 0


def test_run_pipeline_no_model_stores_null_scores(db):
    ticker_dao.get_or_create_ticker(db, "SPY")
    summary = run_pipeline(
        db,
        [{}],
        fetcher=fake_fetcher(make_items()),
        scorer=fake_scorer,
        use_model=False,
    )
    assert summary["scored"] == 0
    rows = news_dao.list_sentiment(db)
    assert all(r["sentiment_score"] is None for r in rows)


def test_select_sources_filters_by_category_and_symbols():
    sector = select_sources("sector", symbols=["SPY", "QQQ"])
    assert sector
    assert all(s["category"] == "sector" for s in sector)
    assert {s["symbol"] for s in sector} == {"SPY", "QQQ"}

    macro = select_sources("geopolitical")
    assert all(s["category"] == "geopolitical" for s in macro)


def test_select_sources_backfill_expands_windows():
    sources = select_sources(
        "sector",
        symbols=["SPY"],
        start="2024-01-01",
        end="2024-02-28",
        step_days=30,
    )
    # 2 windows (Jan, Feb) -> 2 dated SPY sources
    assert len(sources) == 2
    assert all(s["symbol"] == "SPY" for s in sources)
    assert all("after%3A" in s["url"] for s in sources)