# ---- Stage 1: build the SPA ----
FROM node:20-alpine AS frontend-builder
# Same-origin API calls: "" base + "/path" = "/path" (see frontend/src/api.js).
ARG VITE_API_BASE_URL=/
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: runtime (API + SPA + frozen data snapshot) ----
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 \
    ENABLE_SCHEDULER=0 \
    DATABASE_URL=sqlite:////app/simulator.db \
    FRONTEND_DIST=/app/frontend/dist
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/schema.sql ./
COPY --from=frontend-builder /build/dist ./frontend/dist
# Frozen snapshot produced by backend/scripts/prepare_deploy_db.py.
COPY backend/deploy.db ./simulator.db
# Drop root before serving. Root here would turn any RCE in the app into root
# on the host filesystem rather than a confined uid.
#
# The app writes only to its SQLite database, but SQLite in WAL mode
# (app/database.py sets it) creates simulator.db-wal and simulator.db-shm
# *inside the containing directory* while a connection is open -- so the appuser
# needs write access to /app itself, not just to simulator.db. Chowning only
# the file yields a container that boots and then fails on first query.
RUN useradd --create-home --uid 10001 appuser \
 && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
# --limit-concurrency bounds how many requests may be in flight at once. The
# engine allocates ~800 MB for the worst request MAX_PATH_STEPS permits, and
# the SIMULATION_SLOTS semaphore in app/deps.py sheds simulation load at 2; this
# is the outer belt so a burst of cheap non-simulation routes cannot occupy the
# whole thread pool either.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--limit-concurrency", "16", "--timeout-keep-alive", "10"]