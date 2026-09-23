"""Tests for the daily market-data scheduler.

The scheduled refresh must always pull FULL price history (no start bound).
``auto_adjust=True`` re-scales the entire adjusted-close series at each dividend
or split, so an incremental refresh from a start date would join an old
adjustment basis to a new one and fabricate jumps at the boundary.
"""
from app.scheduler import _scheduled_refresh, create_scheduler


def test_scheduled_refresh_uses_full_history(monkeypatch):
    captured = {}

    def fake_refresh_catalog(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {}

    monkeypatch.setattr("app.scheduler.refresh_catalog", fake_refresh_catalog)
    _scheduled_refresh()

    # No start/end passed -> refresh_ticker falls through to the full-history
    # code path (period="max" / sentinel start).
    assert captured["args"] == ()
    assert captured["kwargs"] == {}


def test_create_scheduler_registers_daily_job(monkeypatch):
    calls = {}

    class FakeScheduler:
        def __init__(self, **kwargs):
            calls["kwargs"] = kwargs

        def add_job(self, func, **kwargs):
            calls["add_job"] = kwargs

        def start(self):
            calls["started"] = True

    monkeypatch.setattr(
        "apscheduler.schedulers.background.BackgroundScheduler", FakeScheduler
    )
    create_scheduler()
    assert calls["add_job"]["id"] == "daily_market_refresh"