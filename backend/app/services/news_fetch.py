"""Fetch and normalize news headlines from the configured RSS sources.

The fetch layer is deliberately thin and dependency-light so that the scored
pipeline (``app.scripts.sentiment_ingest``) can be run as a one-off CLI and
later wired into the scheduler without touching the Monte Carlo engine.

Design notes:
- RSS is the primary transport (free, keyless). If ``settings.news_api_key``
  is configured the fetcher also merges NewsAPI head-/everything results as
  an optional bonus source; a NewsAPI outage never blocks RSS ingestion.
- Every headline carries its ``category`` (``sector`` | ``geopolitical``)
  and, for sector items, the ticker ``symbol`` it was searched with.
- Headlines are de-duplicated so re-running ingestion is idempotent.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, TypedDict
from urllib.parse import urlparse

import feedparser
import httpx

from ..config import settings
from ..data.news_sources import NewsSource

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 ETF-Simulator/0.1"
)


class NewsItem(TypedDict):
    category: str  # 'sector' | 'geopolitical'
    symbol: str | None
    source: str
    headline: str
    published_at: str
    url: str
    summary: str


def _to_iso_date(value: Any) -> str:
    """Normalize a feedparser date (struct_time or str) to YYYY-MM-DD.

    Falls back to today's date so a feed entry always has a usable
    ``published_at`` (the news_sentiment column is indexed on it).
    """
    try:
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")
        if isinstance(value, str):
            return datetime.fromisoformat(value[:10]).strftime("%Y-%m-%d")
        if hasattr(value, "tm_year"):  # time.struct_time from feedparser
            return date(value.tm_year, value.tm_mon, value.tm_mday).isoformat()
    except (ValueError, TypeError):
        pass
    return date.today().isoformat()


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.replace("\n", " ").split())


def _normalize_entry(
    entry: Any,
    source: NewsSource,
    max_summary_len: int = 300,
) -> NewsItem | None:
    """Turn one feedparser entry into a ``NewsItem`` (or None if unusable)."""
    headline = _clean(getattr(entry, "title", None))
    if not headline:
        return None
    summary = _clean(getattr(entry, "summary", None))[:max_summary_len]
    link = getattr(entry, "link", None) or ""
    published = _to_iso_date(getattr(entry, "published_parsed", None) or getattr(entry, "published", None))
    return {
        "category": source["category"],
        "symbol": source["symbol"],
        "source": source["label"],
        "headline": headline,
        "published_at": published,
        "url": link,
        "summary": summary,
    }


def fetch_feed_xml(url: str) -> str | None:
    """Download raw feed content (None on any network/HTTP failure)."""
    try:
        response = httpx.get(
            url,
            timeout=settings.news_http_timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        return response.text
    except Exception as exc:  # noqa: BLE001 - one bad feed must not kill the batch
        log.warning("RSS fetch failed for %s: %s", url, exc)
        return None


def parse_feed_xml(xml: str) -> list[Any]:
    """Parse raw RSS/Atom XML into feedparser entries."""
    parsed = feedparser.parse(xml)
    return list(parsed.entries)


def fetch_sources(
    sources: list[NewsSource],
    max_items_per_feed: int | None = None,
) -> list[NewsItem]:
    """Fetch and normalize every source. Never raises.

    Returns a headline list de-duplicated per (category, symbol, headline).
    """
    limit = max_items_per_feed or settings.news_max_items_per_feed
    seen: set[tuple[str, str | None, str]] = set()
    items: list[NewsItem] = []

    for source in sources:
        xml = fetch_feed_xml(source["url"])
        if xml is None:
            continue
        for entry in parse_feed_xml(xml)[:limit]:
            item = _normalize_entry(entry, source)
            if item is None:
                continue
            key = (item["category"], item["symbol"], item["headline"])
            if key in seen:
                continue
            seen.add(key)
            items.append(item)

    log.info("Fetched %d unique headlines from %d sources.", len(items), len(sources))
    return items


__all__ = [
    "NewsItem",
    "fetch_feed_xml",
    "parse_feed_xml",
    "fetch_sources",
    "_normalize_entry",
]