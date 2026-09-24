# Deployment

The whole app — React SPA, FastAPI backend, and the SQLite database — ships as
one container image (`etf-simulator`). Everything that the API needs at
runtime is in the image: mount volumes are not required.

## How it works

The image is built in two stages (`Dockerfile` at the repository root):

1. **frontend-builder** (`node:20-alpine`): `npm ci` + `npm run build`. The
   build injects `VITE_API_BASE_URL=/` so the SPA calls the API on the same
   origin (`/tickers`, not `/api/tickers`; see `frontend/src/api.js`, which
   tolerates both `''` and `'/'`).
2. **runtime** (`python:3.13-slim`): installs `backend/requirements.txt` only
   (no torch/transformers/yfinance/APScheduler/feedparser/scipy), copies the
   API (`backend/app`), the schema (`backend/schema.sql`), the built SPA
   (`frontend/dist`), and the frozen data snapshot (`deploy.db`).

The backend serves the SPA at `/` with a client-side fallback
(`app/main.py::spa_fallback`): hashed assets are served from disk, unknown
paths return `index.html`, all API routes stay at their normal paths.

## The data snapshot is frozen

Unlike the local dev environment — where market data, news sentiment, and the
daily refresh scheduler keep `backend/simulator.db` live — the container
boots from a **frozen snapshot** created locally with:

```bash
cd backend
python scripts/prepare_deploy_db.py    # folds the WAL, ANALYZE, copies simulator.db -> deploy.db
```

`prepare_deploy_db.py` runs a `PRAGMA wal_checkpoint(TRUNCATE)` so the copy is
a single self-contained `deploy.db` (no `-wal`/`-shm` sidecars), then `ANALYZE`
so the deployed query planner has fresh statistics. Because the runtime stage
does not install the ingestion stack, **live market-data ingestion happens
only on your machine**; the deployed simulator replays the snapshot. Rebuild
the image whenever you want newer data.

## Building and running locally

```bash
docker build -t etf-simulator:latest .
docker run -d --name etf-sim -p 8000:8000 etf-simulator:latest
curl http://localhost:8000/health     # {"status":"ok",...}
curl http://localhost:8000/tickers
```

The container defaults (set via `ENV` in the `Dockerfile`):

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:////app/simulator.db` | absolute path to the snapshot inside the image |
| `FRONTEND_DIST` | `/app/frontend/dist` | where the built SPA lives |
| `ENABLE_SCHEDULER` | `0` | the daily refresh scheduler is off (frozen snapshot) |

A `HEALTHCHECK` polls `/health` every 30s (15s start period); the container
reports `healthy` once the API is up.

## `docker compose` / orchestrators

No external state or secrets are needed, so the image works as-is with
Docker Compose, Kubernetes, or any container runtime. To keep a *live* (not
frozen) database across restarts you would mount a volume:

```yaml
services:
  app:
    image: etf-simulator:latest
    ports: ["8000:8000"]
    volumes:
      - simdata:/app/data
```

> If you mount over `simulator.db` you must provide an initialized database
> (the runtime image does not install the ingestion tooling that creates one).

## Deploying to Fly.io

```bash
fly launch --name etf-simulator --no-deploy
fly deploy
# single container, no volume; the frozen snapshot ships inside the image
```

## Deploying to Railway

Connect the repo, set the start command to `uvicorn app.main:app --host
0.0.0.0 --port 8000`, and create the image from the repository `Dockerfile`:

```bash
railway up
```

All default variables come from the `Dockerfile`; override `FRONTEND_DIST` /
`DATABASE_URL` only if you deliberately serve the SPA from a different path.

## Verifying a deployment

```bash
curl -i https://<host>/                     # 200, text/html, <title>ETF Simulator…
curl https://<host>/tickers                 # JSON list of the 13 catalog tickers
curl -X POST https://<host>/portfolios \
     -H 'Content-Type: application/json' \
     -d '{"name":"smoke","monthly_contribution":100,"holdings":[{"symbol":"VTI","weight":100}]}'
curl -X POST https://<host>/portfolios/<id>/simulate \
     -H 'Content-Type: application/json' \
     -d '{"initial_balance":10000,"horizon_months":120,"n_simulations":1000,"seed":42}'
```