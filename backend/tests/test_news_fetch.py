"""Tests for the news fetch/normalization layer (no network, no model)."""
from __future__ import annotations

import time

import pytest

feedparser = pytest.importorskip("feedparser")  # ingest-only dep, absent in the runtime venv

from app.data.news_sources import (
    google_news_rss,
    sector_sources,
    sector_sources_windowed,
)
from app.services.news_fetch import (
    parse_feed_xml,
    fetch_sources,
    _normalize_entry,
)

RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>Test feed</title><link>http://example.test</link><description>d</description>
<item>
  <title>Markets Rally on Fresh Data</title>
  <link>http://example.test/1</link>
  <description>Stocks jumped as traders digested the numbers.</description>
  <pubDate>Mon, 05 Aug 2024 12:00:00 GMT</pubDate>
</item>
<item>
  <title>Markets Rally on Fresh Data</title>
  <link>http://example.test/2</link>
  <description>Dup headline, different link.</description>
  <pubDate>Mon, 05 Aug 2024 13:00:00 GMT</pubDate>
</item>
<item>
  <title></title>
  <link>http://example.test/3</link>
  <description>No title - should be dropped.</description>
  <pubDate>Mon, 05 Aug 2024 14:00:00 GMT</pubDate>
</item>
</channel></rss>
"""


def fake_sector_source(symbol="SPY"):
    return {
        "category": "sector",
        "label": "Google News",
        "symbol": symbol,
        "url": google_news_rss("SPY"),
    }


def test_parse_feed_xml_extracts_entries():
    entries = parse_feed_xml(RSS_XML)
    assert len(entries) == 3
    assert entries[0].title == "Markets Rally on Fresh Data"


def test_normalize_entry_builds_news_item():
    entries = parse_feed_xml(RSS_XML)
    item = _normalize_entry(entries[0], fake_sector_source("SPY"))
    assert item is not None
    assert item["category"] == "sector"
    assert item["symbol"] == "SPY"
    assert item["source"] == "Google News"
    assert item["headline"] == "Markets Rally on Fresh Data"
    assert item["published_at"] == "2024-08-05"
    assert item["url"] == "http://example.test/1"
    assert "Stocks jumped" in item["summary"]


def test_normalize_entry_drops_empty_title():
    entries = parse_feed_xml(RSS_XML)
    assert _normalize_entry(entries[2], fake_sector_source()) is None


def test_normalize_entry_falls_back_to_today_when_date_missing():
    entry = parse_feed_xml(RSS_XML)[0]
    # strip pubDate so published_parsed is absent
    entry.published = None  # type: ignore[attr-defined]
    entry.published_parsed = None  # type: ignore[attr-defined]
    item = _normalize_entry(entry, fake_sector_source())
    assert item["published_at"]  # non-empty fallback


def test_normalize_entry_normalizes_struct_time_like_feedparser():
    entry = parse_feed_xml(RSS_XML)[0]
    entry.published_parsed = time.struct_time((2024, 8, 6, 9, 0, 0, 1, 218, 0))  # type: ignore[attr-defined]
    item = _normalize_entry(entry, fake_sector_source())
    assert item["published_at"] == "2024-08-06"


def test_fetch_sources_deduplicates_within_feed(monkeypatch):
    calls = {}

    def fake_fetch(url):
        calls[url] = calls.get(url, 0) + 1
        return RSS_XML

    monkeypatch.setattr("app.services.news_fetch.fetch_feed_xml", fake_fetch)
    # same (category, symbol, headline) twice in one feed -> only one survives
    items = fetch_sources([fake_sector_source("SPY")], max_items_per_feed=10)
    headlines = [i["headline"] for i in items if i["headline"]]
    assert headlines == ["Markets Rally on Fresh Data"]
    assert len(items) == 1


def test_fetch_sources_keeps_headline_per_symbol(monkeypatch):
    def fake_fetch(url):
        return RSS_XML

    monkeypatch.setattr("app.services.news_fetch.fetch_feed_xml", fake_fetch)
    # same headline under different symbols is kept for each ticker
    items = fetch_sources(
        [fake_sector_source("SPY"), fake_sector_source("QQQ")],
        max_items_per_feed=10,
    )
    assert {i["symbol"] for i in items} == {"SPY", "QQQ"}


def test_fetch_sources_survives_broken_feed(monkeypatch):
    def fake_fetch(url):
        return None

    monkeypatch.setattr("app.services.news_fetch.fetch_feed_xml", fake_fetch)
    assert fetch_sources([fake_sector_source("SPY")]) == []


def test_sector_sources_builds_one_url_per_symbol():
    sources = sector_sources()
    assert len(sources) == len({s["symbol"] for s in sources})
    assert all(s["category"] == "sector" for s in sources)
    assert any(s["symbol"] == "SPY" for s in sources)


def test_windowed_sector_sources_add_dates():
    sources = sector_sources_windowed(start="2024-01-01", end="2024-02-29", step_days=30)
    urls = {s["url"] for s in sources}
    assert len(urls) == len(sources)  # all unique
    assert all("after%3A2024-01-01" in u or "after%3A2024-01-02" in u or "after%3A2024-01-31" in u for u in urls)
    assert all("before%3A" in u for u in urls)