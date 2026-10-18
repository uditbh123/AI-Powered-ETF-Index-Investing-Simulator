"""External intelligence providers: Grok (X Search), Perplexity, Trading Economics.

This is the Phase-8 answer to "the news/sentiment layer only sees RSS feeds".
It adds three *optional* upstreams, and it deliberately adds **no dependency**:
every network call goes through the standard library's ``urllib`` and the HTML
fallback is parsed with ``html.parser``. That keeps ``requirements.txt`` (the
only file the deployed image installs) untouched and keeps
``tests/test_import_hygiene.py`` green -- unlike ``services/news_fetch.py``,
nothing here needs feedparser or httpx.

Providers, and what each is good for:

- **xai** -- Grok's server-side ``x_search`` tool (Responses API). Reads what is
  being said *on X* about a ticker or the macro picture right now, and returns a
  cited synthesis. Key-gated on ``XAI_API_KEY``.
- **perplexity** -- Perplexity's ``/search`` endpoint. Discrete, ranked, very
  fresh web results (economics/finance heavy). Key-gated on
  ``PERPLEXITY_API_KEY``.
- **tradingeconomics** -- macro indicators (inflation, policy rate,
  unemployment, GDP). The public country-list pages are readable with no account,
  so this provider works keyless; a key switches it to the structured JSON API.

All three run only at *ingest* time (``python -m app.scripts.intel_ingest``).
None of this is on the request path, so the deployed API needs no keys and
makes no outbound calls to serve a response.

Failure policy mirrors ``news_fetch``: a provider never raises. A missing key,
an HTTP error, a timeout, or a malformed body all collapse to "no items" with a
warning logged, so one dead upstream cannot take down an ingestion run.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.request
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from typing import Any

from ..config import settings
from .news_fetch import NewsItem

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 ETF-Simulator/0.1"
)

XAI_RESPONSES_URL = "https://api.x.ai/v1/responses"
PERPLEXITY_SEARCH_URL = "https://api.perplexity.ai/search"
TRADING_ECONOMICS_API = "https://api.tradingeconomics.com"
TRADING_ECONOMICS_COUNTRY_LIST = "https://tradingeconomics.com/country-list"

#: Trading Economics indicators we pull, as ``slug -> display label``. The slug
#: is the public country-list path segment; the label is what the UI shows.
TE_INDICATORS: dict[str, str] = {
    "inflation-rate": "Inflation Rate",
    "interest-rate": "Interest Rate",
    "unemployment-rate": "Unemployment Rate",
    "gdp-growth-rate": "GDP Growth Rate",
}

#: Slug -> the keyed API's category wording (they use spaces, not hyphens).
_TE_API_CATEGORY: dict[str, str] = {
    "inflation-rate": "inflation rate",
    "interest-rate": "interest rate",
    "unemployment-rate": "unemployment rate",
    "gdp-growth-rate": "gdp growth rate",
}

#: Countries kept from a keyless country-list pull (the page lists all of them).
TE_COUNTRIES: tuple[str, ...] = (
    "United States",
    "Euro Area",
    "China",
    "Japan",
    "United Kingdom",
)

TE_SOURCE = "tradingeconomics"


# --- provider registry -------------------------------------------------------


@dataclass(frozen=True)
class ProviderInfo:
    """One provider's identity and whether it is usable right now."""

    name: str
    configured: bool
    description: str


def provider_status() -> list[ProviderInfo]:
    """Which providers can run, given the current settings.

    Trading Economics reports as configured unconditionally because its public
    pages need no key; the others are configured iff their key is non-empty.
    """
    return [
        ProviderInfo(
            name="xai",
            configured=bool(settings.xai_api_key),
            description="Grok X Search -- live sentiment from posts on X.",
        ),
        ProviderInfo(
            name="perplexity",
            configured=bool(settings.perplexity_api_key),
            description="Perplexity Search -- fresh, ranked web results.",
        ),
        ProviderInfo(
            name="tradingeconomics",
            configured=True,
            description="Trading Economics -- macro indicators (public data).",
        ),
    ]


def enabled_provider_names() -> list[str]:
    return [p.name for p in provider_status() if p.configured]


# --- HTTP helpers (monkeypatched in tests; never import httpx) ---------------


def _http_post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: int,
) -> Any:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", USER_AGENT)
    for key, value in headers.items():
        request.add_header(key, value)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_get_text(url: str, headers: dict[str, str], timeout: int) -> str:
    request = urllib.request.Request(url, method="GET")
    request.add_header("User-Agent", USER_AGENT)
    for key, value in headers.items():
        request.add_header(key, value)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.replace("\n", " ").split())


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _clean(str(value)).replace(",", "").replace("%", "")
    try:
        return float(text)
    except ValueError:
        return None


# --- xAI / Grok X Search -----------------------------------------------------


def _parse_responses(payload: dict[str, Any]) -> tuple[str, list[str]]:
    """Pull ``(text, citation_urls)`` out of an xAI Responses API object."""
    texts: list[str] = []
    urls: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if not isinstance(part, dict) or part.get("type") != "output_text":
                continue
            text = part.get("text")
            if text:
                texts.append(text)
            for annotation in part.get("annotations") or []:
                if isinstance(annotation, dict) and annotation.get("url"):
                    urls.append(annotation["url"])
    # Some responses surface citations at the top level instead.
    for citation in payload.get("citations") or []:
        if isinstance(citation, str):
            urls.append(citation)
        elif isinstance(citation, dict) and citation.get("url"):
            urls.append(citation["url"])
    return "\n".join(texts).strip(), urls


def xai_search(
    query: str,
    *,
    symbol: str | None = None,
    category: str = "sector",
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[NewsItem]:
    """Run one Grok ``x_search`` query and return it as a single cited item.

    The model returns a synthesis rather than discrete posts, so the whole
    answer becomes one ``NewsItem`` (``source="Grok (X)"``) with the first
    citation as its URL and the rest appended to the summary.
    """
    if not settings.xai_api_key:
        return []

    tool: dict[str, Any] = {"type": "x_search"}
    if from_date:
        tool["from_date"] = from_date
    if to_date:
        tool["to_date"] = to_date

    payload: dict[str, Any] = {
        "model": settings.xai_model,
        "input": [{"role": "user", "content": query}],
        "tools": [tool],
    }
    headers = {"Authorization": f"Bearer {settings.xai_api_key}"}

    try:
        data = _http_post_json(XAI_RESPONSES_URL, payload, headers, settings.intel_http_timeout)
    except Exception as exc:  # noqa: BLE001 - one dead provider must not kill the run
        log.warning("xAI x_search failed for %r: %s", query, exc)
        return []

    if not isinstance(data, dict):
        return []
    text, urls = _parse_responses(data)
    if not text:
        return []

    lines = text.splitlines()
    headline = _clean(lines[0] if lines else text)[:200]
    return [
        {
            "category": category,
            "symbol": symbol,
            "source": "Grok (X)",
            "headline": headline,
            "published_at": date.today().isoformat(),
            "url": urls[0] if urls else "",
            "summary": _clean(text)[:600],
        }
    ]


# --- Perplexity Search -------------------------------------------------------


def perplexity_search(
    queries: list[str],
    *,
    symbol: str | None = None,
    category: str = "geopolitical",
    limit: int | None = None,
) -> list[NewsItem]:
    """Run each query through Perplexity's ``/search`` and normalize the hits."""
    if not settings.perplexity_api_key:
        return []

    cap = limit if limit is not None else settings.intel_max_items
    headers = {"Authorization": f"Bearer {settings.perplexity_api_key}"}
    items: list[NewsItem] = []
    seen: set[str] = set()

    for query in queries:
        try:
            data = _http_post_json(
                PERPLEXITY_SEARCH_URL,
                {"query": [query]},
                headers,
                settings.intel_http_timeout,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Perplexity search failed for %r: %s", query, exc)
            continue

        results = data.get("results") if isinstance(data, dict) else None
        for result in results or []:
            if not isinstance(result, dict):
                continue
            title = _clean(result.get("title") or result.get("snippet"))
            url = result.get("url") or ""
            if not title or title in seen:
                continue
            seen.add(title)
            items.append(
                {
                    "category": category,
                    "symbol": symbol,
                    "source": "Perplexity",
                    "headline": title[:200],
                    "published_at": _clean(result.get("date"))[:10]
                    or date.today().isoformat(),
                    "url": url,
                    "summary": _clean(result.get("snippet"))[:600],
                }
            )
            if len(items) >= cap:
                return items
    return items


# --- Trading Economics -------------------------------------------------------


class _TableParser(HTMLParser):
    """Collect every HTML table as a list of rows of cleaned cell strings."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(_clean("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


# Header-cell labels, compared after sort glyphs are stripped (``Last▼`` -> ``last``).
_LAST_HEADER = "last"
_UNIT_HEADER = "unit"
_DATE_HEADERS = ("date", "reference")


def _header_key(cell: str) -> str:
    """Normalize a header cell: lower-case and drop sort markers.

    The live pages render sortable headers with trailing glyphs, e.g.
    ``Last▼`` or ``Country▼≡``; reducing to letters only turns those back into
    ``last`` / ``country``.
    """
    return re.sub(r"[^a-z]+", "", cell.lower())


def _parse_country_list(html: str, indicator: str, label: str) -> list[tuple[Any, ...]]:
    """Best-effort parse of a Trading Economics ``country-list`` page.

    Returns ``(country, indicator, label, value, unit, period, source)`` rows for
    the countries in ``TE_COUNTRIES``.

    The page layout is outside our control and has changed once already: the
    site originally put the header row and the data rows in one ``<table>``, and
    now emits the header in its own ``<table>`` followed by a separate table of
    data rows (and stamps sort glyphs onto the header text). To survive both, the
    parser walks every row of every table in document order, identifies the
    header by its cell names (a country column plus a "Last" column), and then
    treats every following row as data. Columns are looked up by name, never by
    fixed position, and anything it cannot find is simply skipped.
    """
    parser = _TableParser()
    parser.feed(html)

    wanted = {c.lower() for c in TE_COUNTRIES}
    rows: list[tuple[Any, ...]] = []

    header: list[str] | None = None
    country_idx = last_idx = unit_idx = period_idx = None
    for table in parser.tables:
        for cells in table:
            if header is None:
                keys = [_header_key(cell) for cell in cells]
                if not any("country" in key for key in keys):
                    continue
                last_idx = next((i for i, key in enumerate(keys) if key == _LAST_HEADER), None)
                if last_idx is None:
                    continue
                header = keys
                country_idx = next(i for i, key in enumerate(keys) if "country" in key)
                unit_idx = next((i for i, key in enumerate(keys) if key == _UNIT_HEADER), None)
                period_idx = next((i for i, key in enumerate(keys) if key in _DATE_HEADERS), None)
                continue

            if len(cells) <= last_idx:
                continue
            country = cells[country_idx] if len(cells) > country_idx else cells[0]
            if country.lower() not in wanted:
                continue
            rows.append(
                (
                    country,
                    indicator,
                    label,
                    _to_float(cells[last_idx]),
                    cells[unit_idx] if unit_idx is not None and len(cells) > unit_idx else None,
                    cells[period_idx] if period_idx is not None and len(cells) > period_idx else None,
                    TE_SOURCE,
                )
            )
    return rows


def _keyed_indicators(countries: list[str], indicators: list[str]) -> list[tuple[Any, ...]]:
    """Structured Trading Economics API pull (requires a key)."""
    rows: list[tuple[Any, ...]] = []
    for country in countries:
        for slug in indicators:
            api_category = _TE_API_CATEGORY.get(slug, slug.replace("-", " "))
            url = (
                f"{TRADING_ECONOMICS_API}/country/{country}/{api_category}"
                f"?c={settings.trading_economics_api_key}&f=json"
            )
            try:
                text = _http_get_text(url, {}, settings.intel_http_timeout)
                payload = json.loads(text)
            except Exception as exc:  # noqa: BLE001
                log.warning("Trading Economics (keyed) failed for %s/%s: %s", country, slug, exc)
                continue
            if not isinstance(payload, list):
                continue
            for item in payload:
                if not isinstance(item, dict):
                    continue
                rows.append(
                    (
                        _clean(item.get("Country")) or country,
                        slug,
                        TE_INDICATORS.get(slug, slug),
                        _to_float(item.get("LatestValue")),
                        item.get("Unit"),
                        _clean(item.get("LatestValueDate") or item.get("LastUpdate"))[:10] or None,
                        TE_SOURCE,
                    )
                )
    return rows


def trading_economics_indicators(
    *,
    countries: list[str] | None = None,
    indicators: list[str] | None = None,
) -> list[tuple[Any, ...]]:
    """Fetch macro indicators, keyed API when a key is set, public pages otherwise.

    Keyless is the default path (the teacher's point: the pages are viewable
    without a subscription). A key just upgrades the transport to JSON, which is
    less brittle than scraping, so both paths return the same row shape.
    """
    chosen_indicators = indicators or list(TE_INDICATORS)

    if settings.trading_economics_api_key:
        chosen_countries = countries or ["united states", "euro area"]
        return _keyed_indicators(chosen_countries, chosen_indicators)

    rows: list[tuple[Any, ...]] = []
    for slug in chosen_indicators:
        label = TE_INDICATORS.get(slug, slug)
        url = f"{TRADING_ECONOMICS_COUNTRY_LIST}/{slug}"
        try:
            html = _http_get_text(url, {}, settings.intel_http_timeout)
        except Exception as exc:  # noqa: BLE001
            log.warning("Trading Economics (public) failed for %s: %s", slug, exc)
            continue
        rows.extend(_parse_country_list(html, slug, label))
    return rows


__all__ = [
    "ProviderInfo",
    "provider_status",
    "enabled_provider_names",
    "xai_search",
    "perplexity_search",
    "trading_economics_indicators",
    "TE_INDICATORS",
    "TE_COUNTRIES",
    "TE_SOURCE",
]
