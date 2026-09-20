"""Sources of news headlines for the Phase 5 sentiment pipeline.

Split into two logical categories (matching the ``category`` column of
``news_sentiment``):

- **sector** — headline feeds scoped to a single ticker/ETF. We use Google
  News RSS search results per symbol because they are free, keyless, and map
  cleanly to a ``ticker_id_or_null`` value.
- **geopolitical** — macro/geopolitical feeds that are not tied to one
  ticker. A Geo/ macro story (Fed hikes, tariffs, geopolitics) affects the
  whole market, so these are stored with ``ticker_id_or_null = NULL``.

All sources here are public RSS endpoints. Google News RSS search is a public
product; CNBC and MarketWatch publish RSS feeds for non-commercial use.
NewsAPI is not required — if ``settings.news_api_key`` is set the fetch layer
tries NewsAPI first and silently falls back to RSS, so the free tier is
optional. Anyone repurposing these sources for production should re-verify
their respective Terms of Service.
"""
from __future__ import annotations

from typing import TypedDict

# Per-ticker Google News RSS search queries (sector category).
# Queries are keyed by the ticker symbol used elsewhere in the catalog.
SECTOR_SEARCH_QUERIES: dict[str, str] = {
    "SPY": '"SPY ETF" OR "S&P 500"',
    "VOO": '"VOO ETF" OR "Vanguard S&P 500"',
    "VTI": '"VTI ETF" OR "Vanguard Total Stock Market"',
    "QQQ": '"QQQ ETF" OR "Invesco QQQ" OR "NASDAQ 100"',
    "IWM": '"IWM ETF" OR "Russell 2000"',
    "VXUS": '"VXUS ETF" OR "Vanguard Total International"',
    "EEM": '"EEM ETF" OR "iShares MSCI Emerging Markets"',
    "BND": '"BND ETF" OR "Vanguard Total Bond Market"',
    "TLT": '"TLT ETF" OR "20+ Year Treasury"',
    "GLD": '"GLD ETF" OR "SPDR Gold Shares"',
    "^GSPC": '"S&P 500" index',
    "^IXIC": '"NASDAQ Composite" index',
    "^DJI": '"Dow Jones Industrial Average"',
}

# Macro/geopolitical feeds that are not tied to a single ticker.
# Each entry is (source_label, feed_url).
MACRO_RSS_FEEDS: list[tuple[str, str]] = [
    (
        "MarketWatch Top Stories",
        "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    ),
    (
        "CNBC Top News",
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    ),
    (
        "CNBC Markets",
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
    ),
]

# Additional macro/geopolitical coverage via Google News RSS search so the
# pipeline still works even if a niche feed disappears. Search terms are
# coloured "geopolitical" news: central banks, inflation, geopolitics.
MACRO_SEARCH_QUERIES: list[str] = [
    '"Federal Reserve" AND (rate OR inflation)',
    '"monetary policy" OR "interest rates"',
    '"inflation" AND (economy OR prices)',
    'geopolitical risk OR "trade war" OR tariffs',
]


class NewsSource(TypedDict):
    category: str
    label: str
    url: str
    symbol: str | None


def sector_sources() -> list[NewsSource]:
    """Map the sector search catalog to concrete Google News RSS URLs."""
    return [
        {
            "category": "sector",
            "label": "Google News",
            "symbol": symbol,
            "url": google_news_rss(query),
        }
        for symbol, query in SECTOR_SEARCH_QUERIES.items()
    ]


def sector_sources_windowed(
    *,
    start: str | None = None,
    end: str | None = None,
    step_days: int = 30,
    lang: str = "en-US",
) -> list[NewsSource]:
    """Create dated Google News sources per ticker across [start, end].

    Google News RSS exposes at most ~100 results per query, so coverage of a
    long horizon requires slicing the range into windows. Only Google News
    sources support date bounds; direct RSS feeds (CNBC, MarketWatch) only
    surface recent items and are left unwindowed.
    """
    from datetime import date, timedelta

    def _parse(value: str) -> date:
        return date.fromisoformat(value)

    start_d = _parse(start) if start else date.today()
    end_d = _parse(end) if end else date.today()
    if end_d < start_d:
        start_d, end_d = end_d, start_d

    step = timedelta(days=max(1, step_days))
    sources: list[NewsSource] = []
    cursor = start_d
    # one window at a time; something like week-boundaries so batches stay small
    while cursor < end_d:
        window_end = min(cursor + step - timedelta(days=1), end_d)
        for symbol, query in SECTOR_SEARCH_QUERIES.items():
            sources.append(
                {
                    "category": "sector",
                    "label": "Google News",
                    "symbol": symbol,
                    "url": google_news_rss(
                        query,
                        lang=lang,
                        after=cursor.isoformat(),
                        before=window_end.isoformat(),
                    ),
                }
            )
        cursor = window_end + timedelta(days=1)
    return sources


def macro_sources() -> list[NewsSource]:
    """Combine direct macro RSS feeds and Google News macro searches."""
    sources: list[NewsSource] = [
        {
            "category": "geopolitical",
            "label": label,
            "symbol": None,
            "url": url,
        }
        for label, url in MACRO_RSS_FEEDS
    ]
    sources.extend(
        {
            "category": "geopolitical",
            "label": "Google News",
            "symbol": None,
            "url": google_news_rss(query),
        }
        for query in MACRO_SEARCH_QUERIES
    )
    return sources


def macro_sources_windowed(
    *,
    start: str | None = None,
    end: str | None = None,
    step_days: int = 30,
    lang: str = "en-US",
) -> list[NewsSource]:
    """Macro sources with dated windows on the Google News queries only."""
    from datetime import date, timedelta

    def _parse(value: str) -> date:
        return date.fromisoformat(value)

    sources = [
        {
            "category": "geopolitical",
            "label": label,
            "symbol": None,
            "url": url,
        }
        for label, url in MACRO_RSS_FEEDS
    ]

    start_d = _parse(start) if start else date.today()
    end_d = _parse(end) if end else date.today()
    if end_d < start_d:
        start_d, end_d = end_d, start_d

    step = timedelta(days=max(1, step_days))
    cursor = start_d
    while cursor < end_d:
        window_end = min(cursor + step - timedelta(days=1), end_d)
        for query in MACRO_SEARCH_QUERIES:
            sources.append(
                {
                    "category": "geopolitical",
                    "label": "Google News",
                    "symbol": None,
                    "url": google_news_rss(
                        query,
                        lang=lang,
                        after=cursor.isoformat(),
                        before=window_end.isoformat(),
                    ),
                }
            )
        cursor = window_end + timedelta(days=1)
    return sources


def all_sources() -> list[NewsSource]:
    return sector_sources() + macro_sources()


def google_news_rss(
    query: str,
    lang: str = "en-US",
    after: str | None = None,
    before: str | None = None,
) -> str:
    """Build a Google News RSS search URL for a query.

    ``after``/``before`` are ISO ``YYYY-MM-DD`` bounds pushed into the query
    (Google News search operators) so historical backfills can be built by
    looping over windows — live feeds alone only expose recent headlines,
    which is far too little to correlate against years of price history.
    """
    from urllib.parse import quote

    full_query = query
    if after:
        full_query += f" after:{after}"
    if before:
        full_query += f" before:{before}"
    return (
        "https://news.google.com/rss/search?"
        f"q={quote(full_query)}&hl=en-US&gl=US&ceid=US:en"
    )


__all__ = [
    "NewsSource",
    "SECTOR_SEARCH_QUERIES",
    "MACRO_RSS_FEEDS",
    "MACRO_SEARCH_QUERIES",
    "sector_sources",
    "sector_sources_windowed",
    "macro_sources",
    "macro_sources_windowed",
    "all_sources",
    "google_news_rss",
]