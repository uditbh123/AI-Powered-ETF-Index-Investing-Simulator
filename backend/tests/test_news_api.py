"""API tests for GET /news (Phase 7 news sentiment feed)."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.dao import news as news_dao
from app.dao import tickers as ticker_dao
from app.database import get_connection, init_db
from app.main import app

TODAY = date.today()


def _seed_ticker(conn, symbol, name=None):
    return ticker_dao.get_or_create_ticker(
        conn, symbol, name=name or f"{symbol} fund", sector="Equity"
    )


def _seed_headlines(client, rows):
    """Insert (ticker_symbol_or_None, headline, source, date_offset_days, score, category)."""
    conn = get_connection()
    try:
        for symbol, headline, source, offset, score, category in rows:
            ticker_id = None
            if symbol is not None:
                ticker_id = _seed_ticker(conn, symbol)["id"]
            news_dao.insert_sentiment(
                conn,
                [
                    (
                        ticker_id,
                        headline,
                        source,
                        (TODAY - timedelta(days=offset)).isoformat(),
                        score,
                        category,
                    )
                ],
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "news.db"
    original_url = settings.database_url
    original_sched = settings.enable_scheduler
    settings.database_url = f"sqlite:///{db_path.as_posix()}"
    settings.enable_scheduler = False
    init_db()
    with TestClient(app) as c:
        yield c
    settings.enable_scheduler = original_sched
    settings.database_url = original_url


def test_category_filter_returns_only_requested_category(client):
    _seed_headlines(
        client,
        [
            ("SPY", "Sector headline", "src", 0, 0.4, "sector"),
            (None, "Geo headline", "src", 0, -0.3, "geopolitical"),
        ],
    )

    sector = client.get("/news", params={"category": "sector"}).json()
    assert sector["category"] == "sector"
    assert [h["headline"] for h in sector["headlines"]] == ["Sector headline"]

    geo = client.get("/news", params={"category": "geopolitical"}).json()
    assert [h["headline"] for h in geo["headlines"]] == ["Geo headline"]


def test_days_window_excludes_old_headlines(client):
    _seed_headlines(
        client,
        [
            ("SPY", "Recent", "src", 1, 0.5, "sector"),
            ("SPY", "Inside window", "src", 29, 0.1, "sector"),
            (None, "Too old", "src", 45, -0.9, "geopolitical"),
            (None, "Empty window", "src", 200, 0.9, "geopolitical"),
        ],
    )

    body = client.get("/news", params={"category": "sector", "days": 30}).json()
    assert {h["headline"] for h in body["headlines"]} == {"Recent", "Inside window"}

    geo = client.get("/news", params={"category": "geopolitical", "days": 30}).json()
    assert geo["n_headlines"] == 0  # only rows older than the window exist
    assert geo["aggregate_score"] is None


def test_days_clamped_to_1_and_90(client):
    _seed_headlines(
        client,
        [
            ("SPY", "Today", "src", 0, 0.5, "sector"),
            ("SPY", "Two days old", "src", 2, 0.5, "sector"),
        ],
    )

    tiny = client.get("/news", params={"category": "sector", "days": 0}).json()
    assert tiny["days"] == 1
    assert [h["headline"] for h in tiny["headlines"]] == ["Today"]

    huge = client.get("/news", params={"category": "sector", "days": 5000}).json()
    assert huge["days"] == 90
    assert huge["n_headlines"] == 2


def test_ticker_id_filters_sector_rows_and_is_ignored_for_geopolitical(client):
    _seed_headlines(
        client,
        [
            ("SPY", "SPY sector", "src", 0, 0.4, "sector"),
            ("QQQ", "QQQ sector", "src", 0, 0.6, "sector"),
            (None, "Geo one", "src", 0, -0.2, "geopolitical"),
            (None, "Geo two", "src", 0, -0.4, "geopolitical"),
        ],
    )
    conn = get_connection()
    spy_id = ticker_dao.get_ticker(conn, "SPY")["id"]
    conn.close()

    spector = client.get("/news", params={"category": "sector", "ticker_id": spy_id}).json()
    assert [h["headline"] for h in spector["headlines"]] == ["SPY sector"]

    geo = client.get(
        "/news", params={"category": "geopolitical", "ticker_id": spy_id}
    ).json()
    assert {h["headline"] for h in geo["headlines"]} == {"Geo one", "Geo two"}


def test_aggregate_score_mean_of_non_null(client):
    _seed_headlines(
        client,
        [
            (None, "Scored A", "src", 0, 1.0, "geopolitical"),
            (None, "Scored B", "src", 0, -0.5, "geopolitical"),
            (None, "Null score", "src", 0, None, "geopolitical"),
        ],
    )

    body = client.get("/news", params={"category": "geopolitical"}).json()
    assert body["aggregate_score"] == pytest.approx(0.25)
    assert body["n_headlines"] == 3


def test_aggregate_score_is_null_when_all_scores_null(client):
    _seed_headlines(
        client,
        [
            ("SPY", "No score A", "src", 0, None, "sector"),
            ("SPY", "No score B", "src", 0, None, "sector"),
        ],
    )

    body = client.get("/news", params={"category": "sector"}).json()
    assert body["aggregate_score"] is None
    assert body["n_headlines"] == 2


def test_headlines_newest_first(client):
    _seed_headlines(
        client,
        [
            ("SPY", "Oldest", "src", 3, 0.1, "sector"),
            ("SPY", "Middle", "src", 1, 0.2, "sector"),
            ("SPY", "Newest", "src", 0, 0.3, "sector"),
        ],
    )

    body = client.get("/news", params={"category": "sector"}).json()
    assert [h["headline"] for h in body["headlines"]] == ["Newest", "Middle", "Oldest"]


def test_headlines_capped_at_100(client):
    rows = [("SPY", f"headline {i}", "src", 0, 0.1, "sector") for i in range(105)]
    _seed_headlines(client, rows)

    body = client.get("/news", params={"category": "sector"}).json()
    assert body["n_headlines"] == 100
    assert len(body["headlines"]) == 100


def test_invalid_category_returns_422(client):
    response = client.get("/news", params={"category": "bogus"})
    assert response.status_code == 422
    response = client.get("/news")
    assert response.status_code == 422


def test_empty_feed_returns_no_headlines_and_null_score(client):
    body = client.get("/news", params={"category": "sector"}).json()
    assert body == {
        "category": "sector",
        "days": 30,
        "n_headlines": 0,
        "aggregate_score": None,
        "headlines": [],
    }