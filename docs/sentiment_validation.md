# Sentiment vs. Volatility Validation

FinBERT sentiment scores (P_positive - P_negative) compared with the
annualized realized volatility of daily returns (21 trading-day window)
for each ticker that has both price history and scored news in SQLite.

| Ticker | Category | Days | Sentiment->Forward vol | Forward p | Sentiment->Trailing vol | Trailing p |
|---|---|---|---:|---:|---:|---:|
| QQQ | sector | 35 | +0.105 | +0.550 | +0.106 | +0.546 |
| SPY | sector | 33 | +0.274 | +0.123 | +0.367 | +0.035 |
| SPY | geopolitical | 50 | +0.140 | +0.333 | -0.099 | +0.493 |

*Pearson r (with p-value). "Forward" = sentiment on day *t* vs realized
vol of the next 21 trading days; "Trailing" = sentiment vs the vol of the
previous 21 trading days. n = matched trading days after date-merging.*

## Methodology (reproduce)

1. **Ingest** — `python -m app.scripts.sentiment_ingest` fetches headlines for
   the sector sources (one Google News search per ticker) and the geopolitical
   sources (CNBC/MarketWatch RSS plus macro Google News searches). With
   `--start/--end`, dated `after:`/`before:` Google News searches slice the
   coverage window (default 30-day slices).
2. **Score** — each unique headline is run through `ProsusAI/finbert`
   (`app/services/sentiment.py`, lazy-loaded, batched). Score =
   P(positive) - P(negative), in [-1, +1].
3. **Persist** — `app/dao/news.py` upserts scored headlines into the
   `news_sentiment` table, deduplicating on (headline, source, category).
4. **Analyze** — `python -m app.scripts.validate_sentiment` builds a daily mean
   sentiment series per (ticker, category), computes annualized realized
   volatility of daily returns on a 21 trading-day window (trailing and
   forward-shifted), then reports Pearson r and p-values on the date-merged
   series. Summary doc: `python -m app.scripts.validate_sentiment --write-doc ../docs/sentiment_validation.md`.

## Data snapshot (2026-09-20)

- News scored: 594 headlines across 101 distinct dates (2026-06-01 .. 2026-09-20),
  395 geopolitical / 199 sector. Mean score: geopolitical -0.069, sector +0.016.
- Prices: SPY 8,466 rows (1993-01-29 .. 2026-09-17), QQQ 6,924 rows
  (1999-03-10 .. 2026-09-17).
- Overlap available for validation is therefore only the last ~3.5 months.

## Interpretation

- **Weak evidence at best.** Only one series is remotely significant: SPY sector
  trailing vol, r = +0.367 (p = 0.035). Everything else is well below the usual
  0.05 bar, and none survive a simple multiple-comparison correction.
- **Direction is (weakly) positive for sector news:** more sanguine headlines on
  a given day coincide with slightly higher realized vol around that day. That is
  consistent with *event-driven* news: stories cluster on active/turbulent days
  and tend not to be the calmest equilibrium. It is not evidence that positive
  news forecasts future turbulence in a tradable way (the forward signal is
  effectively noise: p = 0.12-0.55).
- **Geopolitical hedging is flat-to-negative** (trailing -0.10, n.s.): macro
  headline sentiment does not line up with SPY variance, which is expected —
  market vol is largely driven by rate/surprise dynamics, not averaged day-news
  tone.

## Limitations

- **Short overlap.** Google News RSS only serves roughly the most recent ~90
  days of coverage, and the price series effectively ended 2026-09-17, so the
  matched window spans only two to three months. n = 33-50 matched days is small
  for correlation work.
- **Daily-mean aggregation** washes out intraday signal and mixes multiple
  headlines per day; the per-headline scores are themselves noisy at the edges
  (sector min -0.96 / max +0.91).
- **Only two tickers have price history** in this install (SPY, QQQ), so
  per-ticker results are anecdotal, and multiple testing inflates false positives.
- **Volatility is fat-tailed and driven by macro regimes**; a linear daily
  correlation is a weak instrument against it.

## Verdict & next steps

The pipeline (fetch -> FinBERT score -> SQLite -> correlation report) is
operational and tests green, but the current evidence does **not** support using
daily news sentiment as a standalone realized-volatility predictor. To get a
credible number you would need: (a) a longer news backfill than Google News RSS
provides (e.g. NewsAPI `everything` or an archived feed), (b) more tickers with
complete price history, and (c) scoring at higher frequency / per-symbol event
filters. Recommended next phase: wire the sentiment table into a volatility
regime overlay used by the Monte Carlo engine only after the above yields
significant, stable correlations.