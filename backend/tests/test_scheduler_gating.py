"""Scheduler gating: ENABLE_SCHEDULER controls lifespan start/stop.

The real scheduler imports APScheduler (ingest-only dependency), so both
states are exercised by faking app.main.create_scheduler / shutdown_scheduler
and asserting the lifespan calls them exactly as configured.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import main
from app.config import settings


def _swap_db(tmp_path, enable_scheduler: bool):
    original_url = settings.database_url
    original_sched = settings.enable_scheduler
    settings.database_url = f"sqlite:///{(tmp_path / 'sched.db').as_posix()}"
    settings.enable_scheduler = enable_scheduler
    return original_url, original_sched


def test_scheduler_starts_and_stops_when_enabled(monkeypatch, tmp_path):
    log: list[str] = []

    def fake_create():
        log.append("start")
        return object()

    def fake_shutdown(_scheduler):
        log.append("shutdown")

    monkeypatch.setattr(main, "create_scheduler", fake_create)
    monkeypatch.setattr(main, "shutdown_scheduler", fake_shutdown)
    original_url, original_sched = _swap_db(tmp_path, enable_scheduler=True)
    try:
        with TestClient(main.app) as client:
            assert client.get("/health").status_code == 200
            assert log == ["start"]
        assert log == ["start", "shutdown"]
    finally:
        settings.database_url = original_url
        settings.enable_scheduler = original_sched


def test_scheduler_not_started_when_disabled(monkeypatch, tmp_path):
    log: list[str] = []

    def fake_create():
        log.append("start")
        return object()

    monkeypatch.setattr(main, "create_scheduler", fake_create)
    monkeypatch.setattr(main, "shutdown_scheduler", lambda _scheduler: log.append("shutdown"))
    original_url, original_sched = _swap_db(tmp_path, enable_scheduler=False)
    try:
        with TestClient(main.app) as client:
            client.get("/health")
            assert log == []
        assert log == []
    finally:
        settings.database_url = original_url
        settings.enable_scheduler = original_sched