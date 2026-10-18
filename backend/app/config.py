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

    # --- external intelligence providers (optional, key-gated) -------------
    # Grok/X and Perplexity are LLM+search APIs. They are inert until their key
    # is set: the provider functions call them only when the key is non-empty,
    # so a checkout with no keys behaves exactly as before. Trading Economics
    # is the exception -- its public country-list pages are readable without an
    # account, so a key is optional (it switches to the structured JSON API).
    # Everything here happens at *ingest* time (python -m app.scripts.intel_ingest),
    # never on the request path, so the deployed API never needs these keys.
    xai_api_key: str = ""
    xai_model: str = "grok-4.7"
    perplexity_api_key: str = ""
    trading_economics_api_key: str = ""
    # LLM/search calls are slower than an RSS pull; give them their own timeout.
    intel_http_timeout: int = 30
    intel_max_items: int = 10

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