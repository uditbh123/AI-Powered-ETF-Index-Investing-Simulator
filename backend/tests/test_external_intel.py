"""Tests for the external intelligence providers and the intel ingest CLI.

No network and no model. HTTP is stubbed at the module-level transport helpers
``_http_post_json`` / ``_http_get_text``, the Trading Economics HTML is a fixed
fixture, and the scorer is a fake. Because ``external_intel`` is stdlib-only,
none of this needs ``importorskip`` and it runs on a runtime-only venv.
"""
from __future__ import annotations

import pytest

from app.config import settings
from app.dao import macro as macro_dao
from app.dao import news as news_dao
from app.dao import tickers as ticker_dao
from app.scripts import intel_ingest
from app.services import external_intel

XAI_PAYLOAD = {
    "output": [
        {
            "type": "message",
            "content": [
                {
                    "type": "output_text",
                    "text": "Bullish on SPY.\nRates cooling, breadth improving.",
                    "annotations": [{"url": "https://x.com/one"}],
                }
            ],
        }
    ]
}

PERPLEXITY_PAYLOAD = {
    "results": [
        {"title": "Fed holds rates steady", "url": "https://p1", "snippet": "No change."},
        {"title": "Fed holds rates steady", "url": "https://p2", "snippet": "dupe title"},
        {
            "title": "Inflation cools further",
            "url": "https://p3",
            "date": "2026-01-02T00:00:00Z",
            "snippet": "CPI eased.",
        },
    ]
}

COUNTRY_LIST_HTML = """
<html><body>
<table>
<tr><th>Country▼≡</th><th>Last▼</th><th>Previous▼</th><th>Reference▼≡</th><th>Unit</th><th>Next Release▼≡</th></tr>
</table>
<table>
<tr><td>Argentina</td><td>33.4</td><td>33.5</td><td>Sep/26</td><td>%</td><td>Nov/26</td></tr>
<tr><td>United States</td><td>2.9</td><td>3.1</td><td>Sep/26</td><td>%</td><td>Nov/26</td></tr>
<tr><td>Canada</td><td>2.0</td><td>2.1</td><td>Sep/26</td><td>%</td><td>Nov/26</td></tr>
<tr><td>China</td><td>0.5</td><td>0.6</td><td>Sep/26</td><td>%</td><td>Nov/26</td></tr>
</table>
</body></html>
"""

# The site's original layout: header and data rows in one table, no sort glyphs.
LEGACY_SINGLE_TABLE_HTML = """
<table>
<tr><th>Country</th><th>Last</th><th>Previous</th><th>Unit</th><th>Date</th></tr>
<tr><td>United States</td><td>3.2%</td><td>3.1%</td><td>percent</td><td>Jan/2026</td></tr>
<tr><td>Canada</td><td>2.0</td><td>2.1</td><td>percent</td><td>Jan/2026</td></tr>
<tr><td>China</td><td>0.5</td><td>0.6</td><td>percent</td><td>Jan/2026</td></tr>
</table>
"""

KEYED_JSON = (
    '[{"Country": "United States", "LatestValue": 3.2, "Unit": "percent", '
    '"LatestValueDate": "2026-01-31T00:00:00"}]'
)


@pytest.fixture(autouse=True)
def _no_keys(monkeypatch):
    """Clear every provider key so tests opt in explicitly."""
    monkeypatch.setattr(settings, "xai_api_key", "")
    monkeypatch.setattr(settings, "perplexity_api_key", "")
    monkeypatch.setattr(settings, "trading_economics_api_key", "")


# --- provider registry -------------------------------------------------------


def test_provider_status_keyless():
    status = {p.name: p.configured for p in external_intel.provider_status()}
    assert status == {"xai": False, "perplexity": False, "tradingeconomics": True}


def test_provider_status_reflects_keys(monkeypatch):
    monkeypatch.setattr(settings, "xai_api_key", "k1")
    monkeypatch.setattr(settings, "perplexity_api_key", "k2")
    status = {p.name: p.configured for p in external_intel.provider_status()}
    assert status["xai"] and status["perplexity"]


def test_enabled_provider_names_keyless_is_only_tradingeconomics():
    assert external_intel.enabled_provider_names() == ["tradingeconomics"]


# --- xAI / Grok X Search -----------------------------------------------------


def test_xai_returns_empty_without_key():
    assert external_intel.xai_search("anything", symbol="SPY") == []


def test_xai_parses_responses(monkeypatch):
    monkeypatch.setattr(settings, "xai_api_key", "k")
    captured = {}

    def fake_post(url, payload, headers, timeout):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        return XAI_PAYLOAD

    monkeypatch.setattr(external_intel, "_http_post_json", fake_post)
    items = external_intel.xai_search("SPY mood?", symbol="SPY", category="sector")

    assert len(items) == 1
    item = items[0]
    assert item["source"] == "Grok (X)"
    assert item["symbol"] == "SPY"
    assert item["category"] == "sector"
    assert item["headline"] == "Bullish on SPY."
    assert item["url"] == "https://x.com/one"
    assert "Rates cooling" in item["summary"]
    assert captured["payload"]["tools"] == [{"type": "x_search"}]
    assert captured["headers"]["Authorization"] == "Bearer k"
    assert captured["url"] == external_intel.XAI_RESPONSES_URL


def test_xai_returns_empty_on_empty_output(monkeypatch):
    monkeypatch.setattr(settings, "xai_api_key", "k")
    monkeypatch.setattr(external_intel, "_http_post_json", lambda *a, **k: {"output": []})
    assert external_intel.xai_search("q") == []


def test_xai_swallows_transport_error(monkeypatch):
    monkeypatch.setattr(settings, "xai_api_key", "k")

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(external_intel, "_http_post_json", boom)
    assert external_intel.xai_search("q") == []


# --- Perplexity --------------------------------------------------------------


def test_perplexity_returns_empty_without_key():
    assert external_intel.perplexity_search(["q"]) == []


def test_perplexity_normalizes_and_dedupes(monkeypatch):
    monkeypatch.setattr(settings, "perplexity_api_key", "k")
    monkeypatch.setattr(external_intel, "_http_post_json", lambda *a, **k: PERPLEXITY_PAYLOAD)

    items = external_intel.perplexity_search(["economics"], category="geopolitical")
    assert [i["headline"] for i in items] == [
        "Fed holds rates steady",
        "Inflation cools further",
    ]
    assert items[0]["source"] == "Perplexity"
    assert items[0]["symbol"] is None
    assert items[1]["published_at"] == "2026-01-02"


def test_perplexity_respects_limit(monkeypatch):
    monkeypatch.setattr(settings, "perplexity_api_key", "k")
    monkeypatch.setattr(external_intel, "_http_post_json", lambda *a, **k: PERPLEXITY_PAYLOAD)
    assert len(external_intel.perplexity_search(["q"], limit=1)) == 1


def test_perplexity_swallows_transport_error(monkeypatch):
    monkeypatch.setattr(settings, "perplexity_api_key", "k")

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(external_intel, "_http_post_json", boom)
    assert external_intel.perplexity_search(["q"]) == []


# --- Trading Economics -------------------------------------------------------


def test_to_float_variants():
    assert external_intel._to_float(None) is None
    assert external_intel._to_float(3) == 3.0
    assert external_intel._to_float("1,234.5%") == 1234.5
    assert external_intel._to_float("n/a") is None


def test_parse_country_list_keeps_only_configured_countries():
    rows = external_intel._parse_country_list(COUNTRY_LIST_HTML, "inflation-rate", "Inflation Rate")
    assert [row[0] for row in rows] == ["United States", "China"]
    assert rows[0] == (
        "United States",
        "inflation-rate",
        "Inflation Rate",
        2.9,
        "%",
        "Sep/26",
        "tradingeconomics",
    )


def test_parse_country_list_handles_legacy_single_table_layout():
    rows = external_intel._parse_country_list(
        LEGACY_SINGLE_TABLE_HTML, "inflation-rate", "Inflation Rate"
    )
    assert [row[0] for row in rows] == ["United States", "China"]
    assert rows[0][3] == 3.2
    assert rows[0][4] == "percent"
    assert rows[0][5] == "Jan/2026"


def test_parse_country_list_ignores_unrelated_tables():
    html = "<table><tr><th>Foo</th><th>Bar</th></tr><tr><td>1</td><td>2</td></tr></table>"
    assert external_intel._parse_country_list(html, "inflation-rate", "Inflation Rate") == []


def test_keyless_indicators_via_public_pages(monkeypatch):
    monkeypatch.setattr(
        external_intel, "_http_get_text", lambda url, headers, timeout: COUNTRY_LIST_HTML
    )
    rows = external_intel.trading_economics_indicators(indicators=["inflation-rate"])
    assert len(rows) == 2
    assert all(row[1] == "inflation-rate" for row in rows)
    assert all(row[6] == "tradingeconomics" for row in rows)


def test_keyed_indicators_use_json_api(monkeypatch):
    monkeypatch.setattr(settings, "trading_economics_api_key", "secret")
    monkeypatch.setattr(
        external_intel, "_http_get_text", lambda url, headers, timeout: KEYED_JSON
    )
    rows = external_intel.trading_economics_indicators(
        countries=["united states"], indicators=["inflation-rate"]
    )
    assert len(rows) == 1
    assert rows[0][0] == "United States"
    assert rows[0][3] == 3.2
    assert rows[0][5] == "2026-01-31"


def test_keyless_swallows_transport_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("404")

    monkeypatch.setattr(external_intel, "_http_get_text", boom)
    assert external_intel.trading_economics_indicators(indicators=["inflation-rate"]) == []


# --- intel_ingest pipeline ---------------------------------------------------


def _fake_xai(*args, **kwargs):
    return [
        {
            "category": kwargs.get("category", "sector"),
            "symbol": kwargs.get("symbol"),
            "source": "Grok (X)",
            "headline": "Grok says risk-on",
            "published_at": "2026-01-05",
            "url": "https://x.com/one",
            "summary": "risk-on",
        }
    ]


def _fake_perplexity(queries, **kwargs):
    return [
        {
            "category": kwargs.get("category", "geopolitical"),
            "symbol": None,
            "source": "Perplexity",
            "headline": "Perplexity headline",
            "published_at": "2026-01-05",
            "url": "https://p1",
            "summary": "s",
        }
    ]


def _fake_te(**kwargs):
    return [
        ("United States", "inflation-rate", "Inflation Rate", 3.2, "%", "Jan/2026", "tradingeconomics"),
        ("China", "inflation-rate", "Inflation Rate", 0.5, "%", "Jan/2026", "tradingeconomics"),
    ]


def test_collect_items_dedupes_and_respects_providers():
    items = intel_ingest.collect_items(
        ["xai", "perplexity"],
        ["SPY"],
        xai_fn=_fake_xai,
        perplexity_fn=_fake_perplexity,
    )
    # xai produces a sector item for SPY + a macro one; perplexity one macro item
    assert len(items) == 3
    sources = {i["source"] for i in items}
    assert sources == {"Grok (X)", "Perplexity"}


def test_collect_items_skips_disabled_provider():
    items = intel_ingest.collect_items(
        ["perplexity"], ["SPY"], xai_fn=_fake_xai, perplexity_fn=_fake_perplexity
    )
    assert [i["source"] for i in items] == ["Perplexity"]


def test_run_intel_persists_news_and_indicators(db):
    ticker = ticker_dao.get_or_create_ticker(db, "SPY", name="SPY fund", sector="Equity")
    db.commit()

    summary = intel_ingest.run_intel(
        db,
        ["xai", "perplexity", "tradingeconomics"],
        ["SPY"],
        scorer=lambda texts: [0.42] * len(texts),
        xai_fn=_fake_xai,
        perplexity_fn=_fake_perplexity,
        te_fn=_fake_te,
    )
    assert summary == {"fetched": 3, "scored": 3, "inserted": 3, "indicators": 2}

    rows = news_dao.list_sentiment(db)
    assert len(rows) == 3
    assert all(abs(r["sentiment_score"] - 0.42) < 1e-9 for r in rows)
    # the SPY sector headline resolved to the ticker; the macro ones did not.
    sector = [r for r in rows if r["category"] == "sector"]
    assert len(sector) == 1 and sector[0]["ticker_id_or_null"] == ticker["id"]
    assert macro_dao.count_indicators(db) == 2


def test_run_intel_dry_run_persists_nothing(db):
    summary = intel_ingest.run_intel(
        db,
        ["xai", "perplexity", "tradingeconomics"],
        ["SPY"],
        scorer=lambda texts: [0.0] * len(texts),
        xai_fn=_fake_xai,
        perplexity_fn=_fake_perplexity,
        te_fn=_fake_te,
        persist=False,
    )
    assert summary["inserted"] == 0
    assert summary["indicators"] == 2
    assert news_dao.count_sentiment(db) == 0
    assert macro_dao.count_indicators(db) == 0


def test_run_intel_no_model_leaves_scores_null(db):
    summary = intel_ingest.run_intel(
        db,
        ["perplexity"],
        xai_fn=_fake_xai,
        perplexity_fn=_fake_perplexity,
        te_fn=_fake_te,
        use_model=False,
    )
    assert summary["scored"] == 0
    rows = news_dao.list_sentiment(db)
    assert rows and all(r["sentiment_score"] is None for r in rows)
