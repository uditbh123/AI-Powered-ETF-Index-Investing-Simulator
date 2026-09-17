"""One-shot CLI tool: pull historical daily closes for the default tickers.

Usage (from backend/):
    python -m app.scripts.ingest
    python -m app.scripts.ingest --symbols SPY QQQ --start 2020-01-01
    python -m app.scripts.ingest --no-scheduler   # just refresh once, don't start APScheduler
"""
from __future__ import annotations

import argparse
import logging
import sys

from app.config import settings
from app.database import init_db
from app.services.market_data import refresh_catalog, seed_catalog
from app.data.ticker_catalog import DEFAULT_TICKERS, SYMBOLS


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest historical daily closes into SQLite.")
    p.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Yfinance symbols to fetch (default: full catalog).",
    )
    p.add_argument("--start", default=None, help="Start date YYYY-MM-DD (default: full history).")
    p.add_argument("--end", default=None, help="End date YYYY-MM-DD (default: today).")
    p.add_argument(
        "--quiet", action="store_true", help="Minimal output (just errors + summary)."
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO)

    init_db()
    seed_catalog()

    catalog = DEFAULT_TICKERS
    if args.symbols:
        requested = set(args.symbols)
        catalog = [t for t in DEFAULT_TICKERS if t["symbol"] in requested]
        missing = requested - set(SYMBOLS)
        if missing:
            logging.warning(
                "Symbols not in default catalog (will still fetch): %s",
                ", ".join(sorted(missing)),
            )
            for sym in sorted(missing):
                catalog.append({"symbol": sym, "name": None, "sector": None})

    results = refresh_catalog(catalog, start=args.start, end=args.end)

    errors = []
    ok_count = 0
    for sym, info in results.items():
        if "error" in info:
            errors.append(sym)
            if not args.quiet:
                print(f"  {sym:6s}  FAILED  {info['error']}")
        else:
            ok_count += 1
            if not args.quiet:
                print(
                    f"  {sym:6s}  rows={info['rows']}  "
                    f"inserted={info['inserted']}  "
                    f"{info['first']} -> {info['last']}"
                )

    print(f"\nDone: {ok_count} succeeded, {len(errors)} failed out of {len(results)} tickers.")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())