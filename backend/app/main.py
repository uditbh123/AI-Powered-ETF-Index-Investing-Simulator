from contextlib import asynccontextmanager

from fastapi import FastAPI

from .database import check_db_connected, init_db
from .routers import health


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AI-Powered ETF & Index Investing Simulator",
    description="Educational simulation backend. Not financial advice.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)


@app.get("/")
def root() -> dict:
    return {
        "message": "ETF Simulator API",
        "docs": "/docs",
        "health": "/health",
        "db_connected": check_db_connected(),
    }