from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from .config import BACKEND_DIR, settings
from .database import check_db_connected, init_db
from .errors import install_error_handlers
from .routers import crisis, health, news, portfolios, screener, simulations, tickers
from .scheduler import create_scheduler, shutdown_scheduler
from .services.market_data import seed_catalog


def _frontend_dist() -> Path | None:
    """Resolve the built SPA directory, or None when it should not be served.

    Prefers the ``FRONTEND_DIST`` env override; falls back to the repository
    layout ``<repo>/frontend/dist`` (which matches the container layout where
    the backend runs from ``/app`` with the SPA at ``/app/frontend/dist``).
    """
    configured = settings.frontend_dist
    candidate = Path(configured) if configured else BACKEND_DIR.parent / "frontend" / "dist"
    return candidate if candidate.is_dir() else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_catalog()
    scheduler = create_scheduler() if settings.enable_scheduler else None
    try:
        yield
    finally:
        if scheduler is not None:
            shutdown_scheduler(scheduler)


app = FastAPI(
    title="AI-Powered ETF & Index Investing Simulator",
    description="Educational simulation backend. Not financial advice.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(tickers.router)
app.include_router(portfolios.router)
app.include_router(simulations.router)
app.include_router(news.router)
app.include_router(screener.router)
app.include_router(crisis.router)

# Registered after the routers so API routes keep priority; see app/errors.py
# for why every error body must go through these.
install_error_handlers(app)


@app.get("/")
def root():
    # SPA present -> serve it at "/"; absent -> keep the API info JSON
    # (the default behavior of a fresh checkout with no frontend build).
    dist = _frontend_dist()
    if dist is not None:
        return FileResponse(dist / "index.html")
    return {
        "message": "ETF Simulator API",
        "docs": "/docs",
        "health": "/health",
        "db_connected": check_db_connected(),
    }


# Registered last so every API route above wins the match; serves hashed SPA
# assets from disk and falls back to index.html for client-side routes.
@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    dist = _frontend_dist()
    if dist is None:
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    candidate = (dist / full_path).resolve()
    root = dist.resolve()
    if candidate != root and root in candidate.parents and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(dist / "index.html")