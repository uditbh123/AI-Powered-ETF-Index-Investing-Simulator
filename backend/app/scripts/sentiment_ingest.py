"""One-shot CLI: fetch news headlines, score with FinBERT, store results.

Usage (from backend/):
    python -m app.scripts.sentiment_ingest                 # sector + geopolitical
    python -m app.scripts.sentiment_ingest --category sector --symbols SPY QQQ
    python -m app.scripts.sentiment_ingest --limit 25
    python -m app.scripts.sentiment_ingest --dry-run       # fetch + score, do not persist
    python -m app.scripts.sentiment_ingest --no-model      # persist headlines without scores

Idempotent: exact duplicate headlines from the same source are skipped.
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence

from app.config import settings
from app.dao import news as news_dao
from app.dao import tickers as ticker_dao
from app.data.news_sources import (
    macro_sources,
    macro_sources_windowed,
    sector_sources,
    sector_sources_windowed,
)
from app.database import get_connection, init_db
from app.services.news_fetch import NewsItem, fetch_sources
from app.services.sentiment import score_texts

Scorer = Callable[[Sequence[str]], list[float]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Fetch and score news headlines into SQLite (Phase 5)."
    )
    p.add_argument(
        "--category",
        choices=("sector", "geopolitical", "all"),
        default="all",
        help="Which source category to ingest.",
    )
    p.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Restrict sector sources to these ticker symbols.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max headlines kept per feed (default: %(default)s -> settings).",
    )
    p.add_argument(
        "--start",
        default=None,
        help="Backfill start date YYYY-MM-DD (drives dated Google News searches).",
    )
    p.add_argument(
        "--end",
        default=None,
        help="Backfill end date YYYY-MM-DD (default: today).",
    )
    p.add_argument(
        "--step-days",
        type=int,
        default=30,
        help="Backfill window slice in days (Google News paginates on dates).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and score but do not persist anything.",
    )
    p.add_argument(
        "--no-model",
        action="store_true",
        help="Store headlines with a NULL sentiment score (skip the model).",
    )
    p.add_argument("--quiet", action="store_true", help="Minimal output.")
    return p.parse_args(argv)


def select_sources(
    category: str,
    symbols: Sequence[str] | None = None,
    *,
    start: str | None = None,
    end: str | None = None,
    step_days: int = 30,
):
    """Choose sector/macro sources, windowed when a backfill range is given."""
    use_backfill = start is not None or end is not None

    if category in ("sector", "all"):
        if use_backfill:
            sector = sector_sources_windowed(start=start, end=end, step_days=step_days)
        else:
            sector = sector_sources()
        if symbols:
            wanted = set(symbols)
            sector = [s for s in sector if s["symbol"] in wanted]
    else:
        sector = []

    if category in ("geopolitical", "all"):
        if use_backfill:
            macro = macro_sources_windowed(start=start, end=end, step_days=step_days)
        else:
            macro = macro_sources()
    else:
        macro = []
    return sector + macro


def run_pipeline(
    conn,
    sources,
    *,
    fetcher: Callable[[list, dict | int | None], list[NewsItem]] = fetch_sources,
    scorer: Scorer = score_texts,
    max_items_per_feed: int | None = None,
    persist: bool = True,
    use_model: bool = True,
) -> dict:
    """Fetch, score, and (optionally) persist headlines. Returns a summary."""
    items = fetcher(list(sources), max_items_per_feed=max_items_per_feed)

    if use_model and items:
        scores = scorer([it["headline"] for it in items])
    else:
        scores = [None] * len(items)

    summary = {"fetched": len(items), "scored": sum(s is not None for s in scores), "inserted": 0}
    if not persist:
        return summary

    inserted = 0
    for item, score in zip(items, scores):
        ticker_id = None
        if item["symbol"] is not None:
            row = ticker_dao.get_ticker(conn, item["symbol"])
            if row is not None:
                ticker_id = row["id"]
        inserted += news_dao.insert_sentiment(
            conn,
            [
                (
                    ticker_id,
                    item["headline"],
                    item["source"],
                    item["published_at"],
                    score,
                    item["category"],
                )
            ],
        )
    conn.commit()
    summary["inserted"] = inserted
    return summary


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO)

    init_db()
    sources = select_sources(
        args.category,
        args.symbols,
        start=args.start,
        end=args.end,
        step_days=args.step_days,
    )
    if not sources:
        print(f"No sources selected for category='{args.category}'.", file=sys.stderr)
        return 1

    conn = get_connection()
    try:
        summary = run_pipeline(
            conn,
            sources,
            max_items_per_feed=args.limit,
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
    return 0


if __name__ == "__main__":
    sys.exit(main())