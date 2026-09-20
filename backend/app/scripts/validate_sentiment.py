"""Standalone validation: does news sentiment correlate with realized volatility?

Usage (from backend/, after loading prices + sentiment):
    Make sure at least some prices exist:
        python -m app.scripts.ingest --no-scheduler      # full catalog (first run)
    Load + score + store a backfill of headlines:
        python -m app.scripts.sentiment_ingest --start 2024-01-01 --end 2026-09-17
    Then run the validation:
        python -m app.scripts.validate_sentiment
        python -m app.scripts.validate_sentiment --write-doc ../docs/sentiment_validation.md

Methodology (documented in docs/sentiment_validation.md):
- "Sentiment" = mean FinBERT score (sector category) per ticker per day, plus
  one market-wide series from all geopolitical headlines vs. SPY.
- "Realized volatility" = annualized std of daily returns:
    * trailing  <- std of the previous 21 trading days (contemporaneous)
    * forward   <- std of the next 21 trading days (sentiment -> next-month vol)
- Pearson (linear) and Spearman (monotonic) correlations over matched days.
"""
from __future__ import annotations

import argparse
import math
import sys
from typing import Any
import pandas as pd
from scipy import stats

from app.dao import news as news_dao
from app.dao import prices as price_dao
from app.dao import tickers as ticker_dao
from app.database import get_connection, init_db

WINDOW = 21
TRADING_DAYS = 252


def daily_returns(rows: list) -> pd.DataFrame:
    """Rows (date, close, volume) -> DataFrame(date, close) with returns."""
    clean = []
    for r in rows:
        if hasattr(r, "keys"):
            clean.append(tuple(r[k] for k in ("date", "close", "volume")))
        else:
            clean.append(tuple(r))
    df = pd.DataFrame(clean, columns=["date", "close", "volume"]).set_index("date")
    df.index = pd.to_datetime(df.index)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df[~df["close"].isna()]
    df["ret"] = df["close"].pct_change(fill_method=None)
    return df.dropna(subset=["ret"])


def realized_vol(returns: pd.Series, window: int = WINDOW) -> pd.Series:
    """Annualized std of returns over the trailing ``window`` trading days."""
    return returns.rolling(window).std() * math.sqrt(TRADING_DAYS)


def forward_vol(returns: pd.Series, window: int = WINDOW) -> pd.Series:
    """Annualized std of the NEXT ``window`` trading days (shifted into past)."""
    return returns.rolling(window).std().shift(-window) * math.sqrt(TRADING_DAYS)


def sentiment_daily(
    conn: Any,
    *,
    ticker_id: int | None = None,
    category: str = "sector",
) -> pd.Series:
    """Mean sentiment score per day for a ticker (or market-wide when None)."""
    rows = news_dao.list_sentiment(conn, category=category, ticker_id=ticker_id)
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(
        {"date": [r["published_at"] for r in rows], "score": [r["sentiment_score"] or 0.0 for r in rows]}
    )
    df["date"] = pd.to_datetime(df["date"])
    return df.groupby("date")["score"].mean()


def correlate(
    sentiment: pd.Series,
    forward: pd.Series,
    trailing: pd.Series,
) -> dict[str, Any]:
    """Pearson/Spearman for sentiment vs forward and trailing realized vol."""
    merged = pd.concat(
        {"sentiment": sentiment, "v_fwd": forward, "v_trail": trailing},
        axis=1,
        sort=False,
    ).dropna()
    if len(merged) < 10:
        return {
            "n": len(merged),
            "pearson_forward": float("nan"),
            "p_forward": float("nan"),
            "spearman_forward": float("nan"),
            "pearson_trailing": float("nan"),
            "p_trailing": float("nan"),
            "spearman_trailing": float("nan"),
        }
    r_f, p_f = stats.pearsonr(merged["sentiment"], merged["v_fwd"])
    r_t, p_t = stats.pearsonr(merged["sentiment"], merged["v_trail"])
    return {
        "n": len(merged),
        "pearson_forward": r_f,
        "p_forward": p_f,
        "spearman_forward": stats.spearmanr(merged["sentiment"], merged["v_fwd"]).statistic,
        "pearson_trailing": r_t,
        "p_trailing": p_t,
        "spearman_trailing": stats.spearmanr(merged["sentiment"], merged["v_trail"]).statistic,
    }


def analyze_ticker(
    conn: Any,
    symbol: str,
    *,
    ticker_id: int | None = None,
    category: str = "sector",
    market_wide: bool = False,
) -> dict[str, Any]:
    """Run the correlation suite for one ticker (or a market proxy).

    When ``market_wide`` is set the sentiment series is pulled from headlines
    with a NULL ticker (e.g. geopolitical) while prices still come from the
    given ``symbol``.
    """
    if ticker_id is None:
        row = ticker_dao.get_ticker(conn, symbol)
        if row is None:
            return {"symbol": symbol, "error": "ticker not in catalog"}
        ticker_id = row["id"]

    price_rows = price_dao.get_price_history(conn, ticker_id)
    if not price_rows:
        return {"symbol": symbol, "error": "no price data"}

    returns_df = daily_returns(price_rows)
    sent = sentiment_daily(
        conn,
        ticker_id=None if market_wide else ticker_id,
        category=category,
    )
    if sent.empty:
        return {"symbol": symbol, "error": "no sentiment data"}

    trailing = realized_vol(returns_df["ret"])
    forward = forward_vol(returns_df["ret"])

    result = correlate(sent, forward, trailing)
    result["symbol"] = symbol
    result["category"] = category
    result["sentiment_days"] = len(sent)
    result["price_days"] = len(returns_df)
    return result


def format_number(value: float) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    return f"{value:+.3f}"


def render_report(results: list[dict[str, Any]]) -> str:
    lines = [
        "# Sentiment vs. Volatility Validation",
        "",
        "FinBERT sentiment scores (P_positive - P_negative) compared with the",
        "annualized realized volatility of daily returns (21 trading-day window)",
        "for each ticker that has both price history and scored news in SQLite.",
        "",
        "| Ticker | Category | Days | Sentiment->Forward vol | Forward p | Sentiment->Trailing vol | Trailing p |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for r in results:
        if "error" in r:
            lines.append(
                f"| {r['symbol']} | {r.get('category', 'n/a')} | n/a | {r['error']} | n/a | n/a | n/a |"
            )
            continue
        lines.append(
            f"| {r['symbol']} | {r['category']} | {r['n']} | "
            f"{format_number(r['pearson_forward'])} | {format_number(r['p_forward'])} | "
            f"{format_number(r['pearson_trailing'])} | {format_number(r['p_trailing'])} |"
        )
    lines += [
        "",
        "*Pearson r (with p-value). \"Forward\" = sentiment on day *t* vs realized",
        "vol of the next 21 trading days; \"Trailing\" = sentiment vs the vol of the",
        "previous 21 trading days. n = matched trading days after date-merging.*",
    ]
    return "\n".join(lines)


def run_all(conn: Any, symbols: list[str] | None = None, include_macro: bool = True) -> list[dict[str, Any]]:
    """Validate every ticker with price data (plus a market-wide macro check)."""
    results: list[dict[str, Any]] = []
    tickers = ticker_dao.list_tickers(conn)
    for ticker in tickers:
        if symbols and ticker["symbol"] not in set(symbols):
            continue
        res = analyze_ticker(conn, ticker["symbol"], ticker_id=ticker["id"], category="sector")
        if "error" not in res or res["error"] != "no price data":
            results.append(res)

    if include_macro and (not symbols or "SPY" in set(symbols)):
        results.append(analyze_ticker(conn, "SPY", category="geopolitical", market_wide=True))
    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate sentiment vs realized volatility (Phase 5).")
    p.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Restrict per-ticker analysis to these symbols (default: all tickers).",
    )
    p.add_argument(
        "--no-macro",
        action="store_true",
        help="Skip the market-wide geopolitical-vs-SPY analysis.",
    )
    p.add_argument(
        "--write-doc",
        default=None,
        help="Also write the rendered markdown report to this path.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    init_db()
    conn = get_connection()
    try:
        results = run_all(conn, symbols=args.symbols, include_macro=not args.no_macro)
    finally:
        conn.close()

    report = render_report(results)
    print(report)

    if args.write_doc:
        from pathlib import Path

        target = Path(args.write_doc)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(report + "\n", encoding="utf-8")
        print(f"\nReport written to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())