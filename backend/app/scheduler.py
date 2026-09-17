"""Daily market-data refresh via APScheduler.

The scheduler starts during the FastAPI app lifespan when
``settings.enable_scheduler`` is True.  The job itself lives in
``app.services.market_data.refresh_catalog``.
"""
from __future__ import annotations

import logging
from typing import Any

from .config import settings
from .services.market_data import refresh_catalog

log = logging.getLogger(__name__)

_SCHEDULER_JOB_ID = "daily_market_refresh"


def _scheduled_refresh() -> None:
    """Wrapper so APScheduler calls the refresh and logs on failure."""
    log.info("Scheduled daily market-data refresh started.")
    try:
        results = refresh_catalog()
        ok = sum(1 for r in results.values() if "error" not in r)
        log.info(
            "Scheduled refresh complete: %d/%d tickers updated successfully.",
            ok,
            len(results),
        )
    except Exception:  # noqa: BLE001 - scheduler must not die
        log.exception("Scheduled refresh failed unexpectedly.")


def create_scheduler() -> Any:
    """Create and start a background scheduler with the daily job.

    Returns the scheduler instance; the caller is responsible for shutting
    it down on app exit.
    """
    from apscheduler.schedulers.background import BackgroundScheduler

    sched = BackgroundScheduler(timezone=settings.scheduler_timezone)
    sched.add_job(
        _scheduled_refresh,
        trigger="cron",
        hour=settings.refresh_hour,
        minute=settings.refresh_minute,
        id=_SCHEDULER_JOB_ID,
        replace_existing=True,
    )
    sched.start()
    log.info(
        "Scheduler started — daily refresh at %02d:%02d %s.",
        settings.refresh_hour,
        settings.refresh_minute,
        settings.scheduler_timezone,
    )
    return sched


def shutdown_scheduler(scheduler: Any) -> None:
    if scheduler is None:
        return
    try:
        scheduler.shutdown(wait=False)
    except Exception:  # noqa: BLE001
        log.debug("Scheduler shutdown raised an exception (ignored).")


__all__ = ["create_scheduler", "shutdown_scheduler"]