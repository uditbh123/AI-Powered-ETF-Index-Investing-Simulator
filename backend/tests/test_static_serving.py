"""Static serving: when a built frontend/dist exists the API serves the SPA.

The SPA is mounted below/after every API route, so all JSON endpoints keep
working while "/" returns index.html and unknown paths fall back to it
(client-side routing). With no dist present the API keeps its JSON root and
FastAPI's default 404 behaviour.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings

SPA_HTML = (
    "<!doctype html><html><head><title>ETFSIM</title></head>"
    "<body><div id='root'></div></body></html>"
)


def _make_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(SPA_HTML)
    (dist / "assets" / "app.js").write_text("console.log('spa')")
    (dist / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    return dist


@pytest.fixture
def client(tmp_path):
    original_url = settings.database_url
    original_sched = settings.enable_scheduler
    original_dist = settings.frontend_dist
    settings.database_url = f"sqlite:///{(tmp_path / 'api.db').as_posix()}"
    settings.enable_scheduler = False
    with TestClient(app) as test_client:
        yield test_client
    settings.frontend_dist = original_dist
    settings.enable_scheduler = original_sched
    settings.database_url = original_url


def test_root_serves_spa_index_when_dist_present(client, tmp_path):
    settings.frontend_dist = str(_make_dist(tmp_path))
    response = client.get("/")
    assert response.status_code == 200
    assert "ETFSIM" in response.text
    assert response.headers["content-type"].startswith("text/html")


def test_api_endpoints_still_json_with_dist_present(client, tmp_path):
    settings.frontend_dist = str(_make_dist(tmp_path))
    response = client.get("/tickers")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")


def test_spa_fallback_serves_index_for_client_route(client, tmp_path):
    settings.frontend_dist = str(_make_dist(tmp_path))
    response = client.get("/strategies")
    assert response.status_code == 200
    assert "ETFSIM" in response.text


def test_static_asset_served_directly(client, tmp_path):
    settings.frontend_dist = str(_make_dist(tmp_path))
    response = client.get("/assets/app.js")
    assert response.status_code == 200
    assert "console.log('spa')" in response.text


def test_no_dist_keeps_json_root(client):
    settings.frontend_dist = "C:/does/not/exist"
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"] == "ETF Simulator API"


def test_no_dist_unknown_path_is_404(client):
    settings.frontend_dist = "C:/does/not/exist"
    response = client.get("/nope")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}