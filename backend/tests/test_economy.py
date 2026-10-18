"""API + DAO tests for the macro economy surface (Phase 8).

Read-only endpoints over ``macro_indicators``; a temp SQLite file seeded through
the DAO, scheduler disabled. No network, no keys.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.dao import macro as macro_dao
from app.database import init_db
from app.main import app

SAMPLE_ROWS = [
    ("United States", "inflation-rate", "Inflation Rate", 3.2, "%", "Jan/2026", "tradingeconomics"),
    ("China", "inflation-rate", "Inflation Rate", 0.5, "%", "Jan/2026", "tradingeconomics"),
    ("United States", "unemployment-rate", "Unemployment Rate", 4.1, "%", "Jan/2026", "tradingeconomics"),
]


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "economy.db"
    original_url = settings.database_url
    original_sched = settings.enable_scheduler
    settings.database_url = f"sqlite:///{db_path.as_posix()}"
    settings.enable_scheduler = False
    init_db()
    with TestClient(app) as c:
        yield c
    settings.enable_scheduler = original_sched
    settings.database_url = original_url


def _seed() -> None:
    from app.database import get_connection

    conn = get_connection()
    try:
        macro_dao.upsert_indicators(conn, SAMPLE_ROWS)
        conn.commit()
    finally:
        conn.close()


# --- DAO ---------------------------------------------------------------------


def test_upsert_is_idempotent_and_updates_value(db):
    macro_dao.upsert_indicators(db, SAMPLE_ROWS)
    db.commit()
    assert macro_dao.count_indicators(db) == 3

    macro_dao.upsert_indicators(
        db,
        [("United States", "inflation-rate", "Inflation Rate", 3.5, "%", "Feb/2026", "tradingeconomics")],
    )
    db.commit()
    # same (country, indicator, source) key -> update, not a new row
    assert macro_dao.count_indicators(db) == 3
    rows = macro_dao.list_indicators(db, indicator="inflation-rate", country="United States")
    assert len(rows) == 1
    assert rows[0]["value"] == 3.5
    assert macro_dao.latest_fetch_time(db) is not None


def test_list_indicators_filters(db):
    macro_dao.upsert_indicators(db, SAMPLE_ROWS)
    db.commit()
    assert len(macro_dao.list_indicators(db)) == 3
    assert len(macro_dao.list_indicators(db, indicator="inflation-rate")) == 2
    assert len(macro_dao.list_indicators(db, country="United States")) == 2
    assert macro_dao.count_indicators(db, indicator="unemployment-rate") == 1


# --- providers endpoint ------------------------------------------------------


def test_providers_endpoint_default_keyless(client):
    resp = client.get("/economy/providers")
    assert resp.status_code == 200
    body = resp.json()
    names = {p["name"]: p["configured"] for p in body["providers"]}
    assert names == {"xai": False, "perplexity": False, "tradingeconomics": True}


def test_providers_never_leaks_key_material(client):
    body = client.get("/economy/providers").text
    assert "api_key" not in body and "Bearer" not in body


# --- indicators endpoint -----------------------------------------------------


def test_indicators_empty_snapshot(client):
    resp = client.get("/economy/indicators")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["indicators"] == []
    assert body["as_of"] is None


def test_indicators_returns_seeded_rows(client):
    _seed()
    resp = client.get("/economy/indicators")
    body = resp.json()
    assert body["count"] == 3
    assert body["as_of"] is not None
    assert {r["indicator"] for r in body["indicators"]} == {"inflation-rate", "unemployment-rate"}
    row = next(r for r in body["indicators"] if r["country"] == "United States" and r["indicator"] == "inflation-rate")
    assert row["value"] == 3.2
    assert row["unit"] == "%"
    assert row["period"] == "Jan/2026"
    assert row["source"] == "tradingeconomics"


def test_indicators_filter_by_indicator_and_country(client):
    _seed()
    body = client.get("/economy/indicators", params={"indicator": "inflation-rate"}).json()
    assert body["count"] == 2

    body = client.get(
        "/economy/indicators",
        params={"indicator": "inflation-rate", "country": "China"},
    ).json()
    assert body["count"] == 1
    assert body["indicators"][0]["country"] == "China"
