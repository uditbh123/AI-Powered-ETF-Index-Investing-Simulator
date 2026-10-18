"""One-shot CLI: pull external intelligence, score it, store it (Phase 8).

Sibling of ``app.scripts.sentiment_ingest``. Where that script reads RSS feeds,
this one queries the three optional upstreams in ``services/external_intel`` --
Grok (X Search), Perplexity, and Trading Economics -- scores the resulting
headlines with the same FinBERT model, and stores them beside the RSS rows in
``news_sentiment`` so they surface in ``GET /news`` unchanged. Macro figures go
to ``macro_indicators`` and surface in ``GET /economy/indicators``.

Usage (from backend/):
    python -m app.scripts.intel_ingest                      # all configured providers
    python -m app.scripts.intel_ingest --providers xai perplexity
    python -m app.scripts.intel_ingest --symbols SPY QQQ --limit 15
    python -m app.scripts.intel_ingest --dry-run            # fetch + score, do not persist
    python -m app.scripts.intel_ingest --no-model           # store headlines unscored

Nothing here runs on the API request path; the deployed container never needs a
provider key to serve traffic. Idempotent: duplicate headlines from the same
source are skipped, and macro rows are UPSERTed on (country, indicator, source).
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence

from app.dao import macro as macro_dao
from app.dao import news as news_dao
from app.dao import tickers as ticker_dao
from app.database import get_connection, init_db
from app.services.external_intel import (
    enabled_provider_names,
    perplexity_search,
    provider_status,
    trading_economics_indicators,
    xai_search,
)
from app.services.news_fetch import NewsItem
from app.services.sentiment import score_texts

Scorer = Callable[[Sequence[str]], list[float]]

PROVIDER_CHOICES = ("xai", "perplexity", "tradingeconomics")


def symbol_query_x(symbol: str) -> str:
    return (
        f"What are investors and traders saying about {symbol} on X right now? "
        "Summarize the dominant sentiment, the specific catalysts people cite, "
        "and any macro risk being discussed. Be concise and factual."
    )


def macro_query_x() -> str:
    return (
        "What is the current market mood on X regarding US interest rates, "
        "inflation and recession risk? Summarize the dominant sentiment and the "
        "main drivers being discussed. Be concise and factual."
    )


def perplexity_queries(symbols: Sequence[str]) -> list[str]:
    queries = [f"{sym} ETF news and catalysts this week" for sym in symbols]
    queries.append("US inflation, interest rates and market outlook this week")
    return queries


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--providers",
        nargs="+",
        choices=PROVIDER_CHOICES,
        help="Providers to run (default: every configured provider).",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=[],
        help="Tickers to ask the X/Perplexity providers about (default: none).",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max items per provider.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and score but do not persist anything.",
    )
    parser.add_argument(
        "--no-model",
        action="store_true",
        help="Store headlines with a NULL sentiment score (skip the model).",
    )
    parser.add_argument("--quiet", action="store_true", help="Minimal output.")
    return parser.parse_args(argv)


def _dedupe(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[tuple[str, str | None, str]] = set()
    out: list[NewsItem] = []
    for item in items:
        key = (item["category"], item["symbol"], item["headline"])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def collect_items(
    providers: Sequence[str],
    symbols: Sequence[str],
    *,
    xai_fn: Callable[..., list[NewsItem]] = xai_search,
    perplexity_fn: Callable[..., list[NewsItem]] = perplexity_search,
    limit: int | None = None,
) -> list[NewsItem]:
    """Run the headline-producing providers and return de-duplicated items.

    Each provider call is individually try/except-guarded: a provider that blows
    up must not prevent the others (or the macro pull) from completing.
    """
    items: list[NewsItem] = []

    if "xai" in providers:
        for symbol in symbols:
            try:
                items += xai_fn(symbol_query_x(symbol), symbol=symbol, category="sector")
            except Exception as exc:  # noqa: BLE001
                logging.getLogger(__name__).warning("xai %s failed: %s", symbol, exc)
        try:
            items += xai_fn(macro_query_x(), symbol=None, category="geopolitical")
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).warning("xai macro failed: %s", exc)

    if "perplexity" in providers:
        try:
            items += perplexity_fn(
                perplexity_queries(symbols), symbol=None, category="geopolitical", limit=limit
            )
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).warning("perplexity failed: %s", exc)

    return _dedupe(items)


def run_intel(
    conn,
    providers: Sequence[str],
    symbols: Sequence[str] = (),
    *,
    scorer: Scorer = score_texts,
    xai_fn: Callable[..., list[NewsItem]] = xai_search,
    perplexity_fn: Callable[..., list[NewsItem]] = perplexity_search,
    te_fn: Callable[..., list[tuple]] = trading_economics_indicators,
    limit: int | None = None,
    persist: bool = True,
    use_model: bool = True,
) -> dict:
    """Collect, score and store from every requested provider. Returns a summary."""
    items = collect_items(
        providers, symbols, xai_fn=xai_fn, perplexity_fn=perplexity_fn, limit=limit
    )

    if use_model and items:
        scores = scorer([it["headline"] for it in items])
    else:
        scores = [None] * len(items)

    macro_rows: list[tuple] = []
    if "tradingeconomics" in providers:
        try:
            macro_rows = list(te_fn())
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).warning("trading economics failed: %s", exc)

    summary = {
        "fetched": len(items),
        "scored": sum(s is not None for s in scores),
        "inserted": 0,
        "indicators": 0,
    }
    if not persist:
        summary["indicators"] = len(macro_rows)
        return summary

    ticker_id_of: dict[str, int | None] = {}
    for item in items:
        symbol = item["symbol"]
        if symbol not in ticker_id_of:
            row = ticker_dao.get_ticker(conn, symbol) if symbol is not None else None
            ticker_id_of[symbol] = row["id"] if row is not None else None

    rows_to_insert = [
        (
            ticker_id_of[item["symbol"]],
            item["headline"],
            item["source"],
            item["published_at"],
            score,
            item["category"],
        )
        for item, score in zip(items, scores)
    ]
    summary["inserted"] = news_dao.insert_sentiment(conn, rows_to_insert)
    summary["indicators"] = macro_dao.upsert_indicators(conn, macro_rows)
    conn.commit()
    return summary


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO)

    providers = args.providers or enabled_provider_names()
    if not providers:
        print("No providers enabled. Set XAI_API_KEY / PERPLEXITY_API_KEY, or pass --providers.",
              file=sys.stderr)
        return 1

    if not args.quiet:
        status = {p.name: p.configured for p in provider_status()}
        selected = ", ".join(f"{name}({'on' if status.get(name) else 'off'})" for name in providers)
        print(f"Providers: {selected}")
        if "xai" in providers and not status.get("xai"):
            print("  note: xai selected but XAI_API_KEY is empty -- it will return nothing.")

    init_db()
    conn = get_connection()
    try:
        summary = run_intel(
            conn,
            providers,
            args.symbols,
            limit=args.limit,
            persist=not args.dry_run,
            use_model=not args.no_model,
        )
    finally:
        conn.close()

    if not args.quiet:
        mode = "dry-run (not persisted)" if args.dry_run else \
            "persisted without scores" if args.no_model else "persisted with scores"
        print(f"Fetched {summary['fetched']} headlines ({mode}).")
        print(f"Scored {summary['scored']} (FinBERT, -1..1).")
        print(f"Inserted {summary['inserted']} new rows.")
        print(f"Upserted {summary['indicators']} macro indicators.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
