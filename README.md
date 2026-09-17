# AI-Powered ETF & Index Investing Simulator

An educational web application that simulates long-term ETF and index
investing strategies using historical market data, Monte Carlo simulation,
and financial/geopolitical news sentiment analysis. See
[PROJECT.md](PROJECT.md) for the full project spec, architecture decisions,
and phase plan.

> **Educational simulator only.** This project does not provide financial
> advice. Simulated results are hypothetical and not a guarantee of future
> performance.

## Repository layout

```
backend/   FastAPI application, SQLite schema, DAO layer (Phases 0-3, 5-7)
frontend/  React (Vite) single-page app, routing, disclaimer banner (Phases 0, 4, 6, 8)
```

## Prerequisites

- Python 3.11+ (developed against 3.14)
- Node.js 20+ and npm

## Backend setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # PowerShell on Windows
pip install -r requirements.txt
copy .env.example .env            # fill in API keys when you add them
```

Run the API server (defaults to http://127.0.0.1:8000):

```bash
uvicorn app.main:app --reload
```

- OpenAPI docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

On startup the app creates the SQLite database (`backend/simulator.db`) by
applying `backend/schema.sql`. The schema is idempotent (`CREATE TABLE IF NOT
EXISTS`), so restarting is safe.

## Market data ingestion (Phase 1)

A fixed catalog of ETFs/indices lives in
`backend/app/data/ticker_catalog.py`. To pull (or refresh) their full daily
close history into SQLite:

```bash
cd backend
python -m app.scripts.ingest                  # all tickers, full history
python -m app.scripts.ingest --symbols SPY QQQ --start 2020-01-01
```

Fetching is idempotent — re-running only inserts new trading days, never
duplicates. The API server also seeds the catalog on startup and (when
`ENABLE_SCHEDULER=true`) refreshes every day at `REFRESH_HOUR:REFRESH_MINUTE`
(see `.env.example`). One-off refreshes can be run at any time via the CLI.

## Backend tests

The simulation engine (Phase 2) is a pure, API-independent module validated
against analytically solvable baselines. The DAO and ingestion layers
(Phase 1) are tested against a temp SQLite file with mocked fetch output, so
tests never touch the network. Run everything from `backend/`:

```bash
cd backend
.venv\Scripts\activate        # or: python -m venv .venv once on first setup
pytest
```

## Frontend setup

```bash
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

Vite proxies `/api/*` to the backend at `http://127.0.0.1:8000` (see
`frontend/vite.config.js`), so API calls from the browser can use relative
`/api/...` URLs with no CORS setup. Backend routes are exposed under `/api` in
dev; adjust `VITE_API_BASE_URL` in `frontend/.env.local` if you need a
different target.

Other commands:

```bash
npm run lint    # oxlint
npm run build   # production build to dist/
```

## Environment files

- `backend/.env` — backend settings (`DATABASE_URL`, API keys). Never commit.
- `frontend/.env.local` — Vite variables, `VITE_` prefixed only. Never commit.

Both have committed `.env.example` templates.

## Development workflow

- Build one phase at a time (see [PROJECT.md](PROJECT.md) section 5), commit,
  then move to the next.
- From Phase 1 on, SQLite access goes through a DAO/repository layer, never
  raw SQL in route handlers, so a future Postgres migration is a config
  change.