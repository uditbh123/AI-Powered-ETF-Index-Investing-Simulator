# AGENTS.md — AI-Powered ETF & Index Investing Simulator

Guidance for AI coding agents working in this repository.

## Stack & layout

- `backend/` — FastAPI app (Phases 0–3, 5–7). Python 3.11+ (developed on 3.14).
- `frontend/` — React + Vite SPA (Phases 0, 4, 6, 8), oxlint, built to `frontend/dist`.
- `docs/` — `PROJECT.md` (spec/phase plan), `deployment.md`, `ai_usage_log.md`.

Read `PROJECT.md` before implementing a phase. Stages are developed one at a
time, verified, and committed as a single commit; never sweep unrelated
changes into a commit.

## Commands

- Backend suite: from `backend/` run `python -m pytest` (dev venv `.venv`, or
  install `requirements-dev.txt`). Expected: 181 passing.
- Lint/typecheck: frontend `npm run lint` (oxlint) — backend has no linter.
- Frontend build: `npm run build`.
- Ingest CLI: `backend` → `python -m app.scripts.ingest` (dev only).

## Dependency sets (important)

Three requirement files exist in `backend/`:

- `requirements.txt` — runtime only (FastAPI, uvicorn, pydantic, numpy,
  pandas). This is all the deployed Docker image installs.
- `requirements-ingest.txt` — adds yfinance, APScheduler, feedparser, scipy,
  torch, transformers for local ingestion/sentiment.
- `requirements-dev.txt` — adds pytest, httpx for the test suite.

The live API NEVER imports the ingest stack at boot: `torch`/`transformers`
are lazy in `app/services/sentiment.py:L` and `yfinance` in
`app/services/market_data.py:L`. Keep it that way — the deployed container has
no torch. Do not add an ingest dependency to `app/` boot-path imports.

`app/scripts/` (ingest, sentiment_ingest, validate_sentiment, seed_demo) and
any test that imports them are allowed to use ingest deps; tests that do must
guard with `pytest.importorskip(...)` so they skip on a runtime-only venv.

## Tests

- Run from `backend/`. `tests/test_api.py` swaps `settings.database_url` to a
  temp SQLite file and sets `settings.enable_scheduler=False`; the fixture
  pattern in `conftest.py` (db) is the template for DB-backed tests.
- Guarded modules: `test_sentiment` (torch), `test_market_data` (yfinance ×3),
  `test_news_fetch` + `test_sentiment_ingest` (feedparser),
  `test_validate_sentiment` (scipy), `test_scheduler::test_create_scheduler...`
  (apscheduler).

## Config & environment

`backend/app/config.py` reads `backend/.env`. Key settings: `DATABASE_URL`,
`ENABLE_SCHEDULER` (scheduler is gated behind it in the `app/main.py`
lifespan), `FRONTEND_DIST` (built SPA dir; when present the API serves the SPA
at `/` with an `index.html` fallback — `app/main.py::spa_fallback`).

## Frontend API base

`frontend/src/api.js` builds each call as `API_BASE + path`. Default
`'/api'` (the Vite dev proxy forwards `/api/*` → `127.0.0.1:8000`). The
Docker build overrides `VITE_API_BASE_URL=/`; trailing slashes are trimmed,
so `'/' + '/tickers'` never double-slashes. When changing API calls, keep the
leading-slash path convention.

## Deployment

Single container: `Dockerfile` (node build stage → python:3.13-slim runtime
with `backend/requirements.txt` only). `backend/deploy.db` is the frozen data
snapshot (produced by `backend/scripts/prepare_deploy_db.py`) copied into the
image. `ENABLE_SCHEDULER=0`. See `docs/deployment.md`.

## Git hygiene

- `git status` noise that must never be committed: `D tree.txt`,
  `?? project-tree.txt`.
- Windows + PowerShell 5.1: pytest output is UTF-16 when redirected — set
  `$env:PYTHONUTF8=1`; single-quoted JSON is passed literally to `curl.exe`
  (use `--data-binary "@file"` with a temp payload file).
- Never commit `*.db`, `.env`, `.env.local`, logs, or secrets.