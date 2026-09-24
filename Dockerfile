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
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]