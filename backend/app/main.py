from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .database import check_db_connected, init_db
from .routers import health, news, portfolios, screener, simulations, tickers
from .scheduler import create_scheduler, shutdown_scheduler
from .services.market_data import seed_catalog


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


@app.get("/")
def root() -> dict:
    return {
        "message": "ETF Simulator API",
        "docs": "/docs",
        "health": "/health",
        "db_connected": check_db_connected(),
    }