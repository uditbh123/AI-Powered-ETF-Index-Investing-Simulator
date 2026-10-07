"""Application configuration loaded from environment variables / .env file."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'simulator.db').as_posix()}"
    market_data_api_key: str = ""
    news_api_key: str = ""

    # Built SPA directory. When present (set or the default frontend/dist
    # exists), the API additionally serves the SPA at "/" with a client-side
    # fallback; otherwise the API keeps its JSON root. None disables serving.
    frontend_dist: str | None = None

    # --- sentiment pipeline (Phase 5) ------------------------------------
    sentiment_model: str = "ProsusAI/finbert"
    sentiment_batch_size: int = 8
    news_http_timeout: int = 15
    news_max_items_per_feed: int = 20

    # --- scheduler (daily data refresh) -----------------------------------
    enable_scheduler: bool = True
    scheduler_timezone: str = "UTC"
    refresh_hour: int = 6
    refresh_minute: int = 30

    # --- HTTP surface -----------------------------------------------------
    # Serving the interactive API docs is a convenience for development, and it
    # publishes the full route and parameter schema to any client that can
    # reach the port -- including every internal bound (MAX_PATH_STEPS and
    # friends), which is reconnaissance for someone looking for the workload
    # ceiling. Default off; opt in with EXPOSE_API_DOCS=true. /openapi.json
    # follows the same flag, since it is the machine-readable form of the same
    # disclosure.
    expose_api_docs: bool = False


settings = Settings()