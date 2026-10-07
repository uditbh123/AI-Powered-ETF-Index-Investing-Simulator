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


#: Escapes that defeat a naive ``startswith(root)`` check: a plain "../",
#: a traversal that resolves back inside dist after crossing a subdirectory, a
#: doubled-dot segment that some normalizers collapse, and a percent-encoded
#: form that only decodes after the path is joined.
TRAVERSAL_PROBES = (
    "../secret.env",
    "../../secret.env",
    "assets/../../secret.env",
    "....//....//secret.env",
    "%2e%2e%2fsecret.env",
    "..%2fsecret.env",
    "assets/./../../secret.env",
)


@pytest.mark.parametrize("probe", TRAVERSAL_PROBES)
def test_spa_fallback_rejects_path_traversal(client, tmp_path, probe):
    """A file outside dist must never be served, whatever the URL says.

    ``spa_fallback``'s ``root in candidate.parents`` check is the only thing
    between a request and /etc/passwd or a mounted .env. The control works, but
    nothing in the suite pinned it -- dropping that clause during a refactor
    would leave every other test green. This writes a canary outside dist and
    asserts its contents never come back, whether the response is a 200
    fallback or a 404; both are acceptable, leaking is not.
    """
    dist = _make_dist(tmp_path)
    settings.frontend_dist = str(dist)
    canary = tmp_path / "secret.env"
    canary.write_text("NEWS_API_KEY=leaked-canary-value")

    response = client.get("/" + probe)

    assert "leaked-canary-value" not in response.text


def test_spa_fallback_does_not_serve_a_sibling_directory(tmp_path):
    """The traversal guard is about the resolved path, not the URL string.

    A sibling directory whose name *starts with* the dist directory name is the
    case a ``str(candidate).startswith(str(root))`` prefix check gets wrong
    (``/app/frontend/dist-secrets`` vs ``/app/frontend/dist``).
    """
    dist = _make_dist(tmp_path)
    sibling = tmp_path / "dist-secrets"
    sibling.mkdir()
    (sibling / "env").write_text("HF_TOKEN=leaked-canary-value")

    original_dist = settings.frontend_dist
    original_sched = settings.enable_scheduler
    settings.frontend_dist = str(dist)
    settings.enable_scheduler = False
    try:
        with TestClient(app) as test_client:
            response = test_client.get("/../dist-secrets/env")
            assert "leaked-canary-value" not in response.text
    finally:
        settings.frontend_dist = original_dist
        settings.enable_scheduler = original_sched