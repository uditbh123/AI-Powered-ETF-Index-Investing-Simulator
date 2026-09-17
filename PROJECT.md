# AI-Powered ETF & Index Investing Simulator — Project Spec

**Team:** Udit Bhattarai, Lotus Nyaupane, Dipen Gaihre
**Timeline:** 8 weeks, ~135h/person (405h total)

This document is the source of truth for architecture and scope decisions. Read
this in full before generating any code. Build in the phases below, one at a
time — do not attempt to scaffold the entire application in a single pass.

## 1. Goal

An AI-powered web application that simulates and analyzes long-term ETF and
index investing strategies using historical market data, Monte Carlo
simulation, and financial/geopolitical news sentiment analysis.

- **Example 1:** User enters current portfolio balance, monthly investment
  amount, and investment period. System runs a Monte Carlo simulation over
  historical index returns and generates best-case, median, and worst-case
  growth trajectories.
- **Example 2:** System analyzes recent financial *and geopolitical/macro*
  news related to the user's selected ETF or sector via an NLP sentiment
  model, producing a sentiment score that adjusts the simulation's short-term
  volatility parameter.

## 2. Tech stack (decided)

| Layer | Choice | Reasoning |
|---|---|---|
| Backend | Python, FastAPI | async-friendly, lightweight, good for a data API |
| Data processing | pandas, NumPy | standard, vectorized Monte Carlo |
| ML/stats | scikit-learn | regression pieces, validation |
| NLP | Hugging Face `transformers`, FinBERT (pretrained) | no time to train from scratch |
| Database | **SQLite** (not Postgres) | data is effectively read-only (daily closes); no server to deploy; single file; low concurrency needs. Access must go through a DAO/repository layer so a future Postgres migration is a config change, not a rewrite. |
| Market data | `yfinance` (free, ~15-min delayed) | "real-time" for daily-frequency data means a daily scheduled refresh + on-demand current-price fetch, not tick streaming |
| News data | NewsAPI free tier and/or RSS feeds (Reuters, Yahoo Finance — verify ToS) | both sector/company news AND geopolitical/macro headlines, scored by the same FinBERT pipeline |
| Frontend | React.js | stronger portfolio piece than Streamlit |
| Charts | Recharts (or D3.js if more control needed) | confidence-interval fan charts |
| Scheduling | APScheduler or simple cron | daily data refresh job |
| Version control | Git/GitHub | phase-by-phase commits |

## 3. Explicit scope boundaries

- No real brokerage/account linking. Portfolios are hypothetical/simulated
  only. Do not build anything that handles real financial credentials.
- Geopolitical risk is **not** a separate subsystem. It is additional input
  to the existing sentiment pipeline (broaden the news sources fetched, not
  a new architecture). If it doesn't produce sensible/validatable results by
  week 6, fall back to sector-only sentiment and document the limitation.
- The app is an educational simulator, not investment advice. This must be
  visibly disclaimed in the UI.
- MVP first: a working end-to-end simulation (no sentiment) is the priority
  before any NLP work begins.

## 4. Data model (SQLite, initial draft)

```
tickers(id, symbol, name, sector)
prices(id, ticker_id, date, close, volume)
users(id, name, created_at)                 -- simple, no real auth needed for MVP
portfolios(id, user_id, name, monthly_contribution, start_date)
portfolio_holdings(id, portfolio_id, ticker_id, weight)
simulation_runs(id, portfolio_id, params_json, created_at)
simulation_results(id, run_id, percentile, path_json)
news_sentiment(id, ticker_id_or_null, headline, source, published_at, sentiment_score, category)
  -- category: 'sector' | 'geopolitical'
```
Adjust freely once you start building — this is a starting point, not a
contract.

## 5. Build phases (prompt opencode one phase at a time)

Each phase below is one unit of work: prompt it, review the diff, run it,
commit, THEN move to the next phase in a new prompt. Do not chain multiple
phases into a single request.

### Phase 0 — Scaffolding (Week 1)
- FastAPI project structure, SQLite connection + migrations (e.g. via
  `alembic` or a simple schema.sql), basic health-check endpoint.
- React app scaffold (Vite), routing skeleton, disclaimer banner component.
- `.env` handling for API keys, `.gitignore`, README.

### Phase 1 — Data ingestion (Week 2)
- `yfinance`-based script to pull historical daily closes for a fixed list
  of ETFs/indices into SQLite.
- DAO layer for reading/writing price data (no raw SQL in route handlers).
- Scheduled daily refresh job.

### Phase 2 — Monte Carlo engine (Week 3)
- Vectorized (NumPy, no Python-level loops over simulated paths) bootstrap
  simulation over historical returns.
- Validate against a naive baseline (e.g. does the simulated distribution's
  mean/variance roughly match historical realized returns?).
- Expose as a pure function/module, independent of the API, so it's testable.

### Phase 3 — Backend API for simulations (Week 3–4)
- Endpoints: create portfolio config, trigger simulation, fetch cached
  results, list available tickers.
- Cache simulation results in SQLite (don't recompute on every page load).

### Phase 4 — Frontend: input + basic results (Week 4)
- Portfolio input form (monthly contribution, ticker selection, horizon).
- Basic result table/chart (median trajectory only — confidence bands come
  in Phase 6).

### Phase 5 — Sentiment pipeline (Week 4–5)
- News fetching for both sector/company headlines and geopolitical/macro
  headlines.
- FinBERT scoring, stored in `news_sentiment`.
- Validate: does the sentiment score show any historical correlation with
  realized volatility in your data? Document findings either way.

### Phase 6 — Sentiment-adjusted simulation + fan charts (Week 5–6)
- Wire sentiment score into the Monte Carlo volatility parameter.
- Frontend: confidence-interval fan chart (best/worst/median bands),
  toggle to compare with/without sentiment adjustment.

### Phase 7 — Hardening (Week 6–7)
- Error handling for flaky/rate-limited APIs, DB indexing, integration
  testing end-to-end, deploy to a staging environment.

### Phase 8 — Polish & submission (Week 8)
- UI polish, disclaimers, final documentation of methodology and
  limitations (especially around the sentiment/geopolitical model),
  presentation and demo prep.

## 6. Risks (carried into the final report)

- Free data/news API reliability (rate limits, gaps) — mitigate with
  aggressive SQLite caching from Phase 1 onward.
- Sentiment→volatility mapping may not validate — have the sector-only
  fallback ready.
- Geopolitical scope creep — bounded explicitly to "extra headlines into
  the existing pipeline," not a new subsystem.
- Overall project complexity (data + ML + NLP + DB + frontend) — MVP-first
  ordering above exists specifically to manage this.

