"""Regression tests for the Stage L4 error-handling audit.

Every error the API returns must be structured JSON with a safe message, and
nothing internal (traceback, file path, exception text) may reach the client.

The NaN/Infinity cases are the load-bearing ones: Python's ``json`` parser
accepts the non-standard ``NaN`` / ``Infinity`` tokens, and Starlette renders
422 bodies with ``allow_nan=False``. Before ``app/errors.py`` a request body
carrying one of those tokens raised ``ValueError`` *inside the validation error
handler*, escaping it and turning a 422 into a plain-text 500.
"""
import json
import math
import sqlite3

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.dao import prices as price_dao
from app.dao import tickers as ticker_dao
from app.database import init_db
from app.errors import INTERNAL_ERROR_DETAIL, _safe
from app.main import app

MONTHS = 120


def _seed_market_data() -> None:
    conn = sqlite3.connect(settings.database_url[10:])
    conn.row_factory = sqlite3.Row
    dates = pd.date_range("2021-01-31", periods=MONTHS, freq="ME")
    rows = [
        (d.strftime("%Y-%m-%d"), round(100.0 * (1.004**i), 4), 1_000_000)
        for i, d in enumerate(dates)
    ]
    for symbol in ("SPY", "QQQ"):
        ticker_dao.get_or_create_ticker(
            conn, symbol, name=f"{symbol} fund", sector="Equity"
        )
        price_dao.upsert_daily_prices(conn, ticker_dao.get_ticker(conn, symbol)["id"], rows)
    conn.commit()
    conn.close()


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "errors.db"
    original_url = settings.database_url
    original_sched = settings.enable_scheduler
    settings.database_url = f"sqlite:///{db_path.as_posix()}"
    settings.enable_scheduler = False
    init_db()
    _seed_market_data()
    with TestClient(app) as c:
        yield c
    settings.enable_scheduler = original_sched
    settings.database_url = original_url


def _strict_json(response) -> object:
    """Parse a body, rejecting the non-standard NaN/Infinity tokens."""
    return json.loads(
        response.text,
        parse_constant=lambda c: pytest.fail(f"body contains non-JSON token {c!r}"),
    )


def _no_leaks(response) -> None:
    body = response.text
    for leak in (
        "Traceback",
        "site-packages",
        ".py\"",
        "app\\",
        "app/services",
        "app\\services",
        "File \"",
    ):
        assert leak not in body, f"response leaked {leak!r}: {body[:200]}"


# ---------------------------------------------------------------------------
# NaN / Infinity in a request body -> 422 JSON, not a plain-text 500
# ---------------------------------------------------------------------------

def test_nan_in_simulate_body_returns_422_json(client):
    response = client.post(
        "/portfolios/1/simulate",
        content=b'{"initial_balance": NaN, "horizon_months": 12, "n_simulations": 100}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    detail = _strict_json(response)["detail"]
    assert any("initial_balance" in d["loc"] for d in detail)
    _no_leaks(response)


def test_nan_weight_in_portfolio_body_returns_422_json(client):
    response = client.post(
        "/portfolios",
        content=b'{"name": "x", "holdings": [{"symbol": "SPY", "weight": NaN}]}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    detail = _strict_json(response)["detail"]
    assert any("weight" in d["loc"] for d in detail)
    _no_leaks(response)


def test_infinity_in_simulate_body_returns_422_json(client):
    response = client.post(
        "/portfolios/1/simulate",
        content=b'{"initial_balance": Infinity, "horizon_months": 12}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    _strict_json(response)


def test_nan_monthly_contribution_returns_422_json(client):
    response = client.post(
        "/portfolios",
        content=b'{"name": "x", "monthly_contribution": NaN,'
        b' "holdings": [{"symbol": "SPY", "weight": 1.0}]}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    _strict_json(response)


def test_non_finite_input_is_rendered_as_a_string_not_a_float(client):
    """The offending value is echoed back as "nan"/"inf" so it can be encoded."""
    response = client.post(
        "/portfolios",
        content=b'{"name": "x", "holdings": [{"symbol": "SPY", "weight": NaN}]}',
        headers={"content-type": "application/json"},
    )
    detail = _strict_json(response)["detail"]
    assert detail[0]["input"] == "nan"


# ---------------------------------------------------------------------------
# Unhandled exceptions -> JSON 500, traceback to the log only
# ---------------------------------------------------------------------------

def test_unhandled_exception_returns_json_500_without_internals(client, monkeypatch, caplog):
    def _boom():
        raise RuntimeError("secret internal detail")

    # get_db() resolves get_connection from its own module globals at call time,
    # so this makes every DB-backed route fail the way an I/O error would.
    monkeypatch.setattr("app.deps.get_connection", _boom)

    # Starlette's ServerErrorMiddleware sends the handler's response and then
    # re-raises so the server can log it; raise_server_exceptions=False is what
    # a real client sees (uvicorn logs the re-raise, the client gets the body).
    with TestClient(app, raise_server_exceptions=False) as live:
        with caplog.at_level("ERROR"):
            response = live.get("/tickers")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert _strict_json(response) == {"detail": INTERNAL_ERROR_DETAIL}

    for leak in ("Traceback", "secret internal detail", "RuntimeError", "get_connection"):
        assert leak not in response.text
    assert "unhandled error while serving a request" in caplog.text
    # The traceback itself is only in the log.
    assert "RuntimeError: secret internal detail" in caplog.text


# ---------------------------------------------------------------------------
# Ordinary error shapes are preserved (the SPA reads body.detail)
# ---------------------------------------------------------------------------

def test_http_exception_detail_shape_is_unchanged(client):
    response = client.get("/tickers/NOPE/prices")
    assert response.status_code == 404
    assert _strict_json(response) == {"detail": "ticker 'NOPE' not found"}


def test_validation_error_detail_shape_is_unchanged(client):
    response = client.post(
        "/portfolios", json={"name": "x", "holdings": [{"symbol": "SPY", "weight": -1.0}]}
    )
    assert response.status_code == 422
    detail = _strict_json(response)["detail"]
    assert isinstance(detail, list)
    assert {"type", "loc", "msg"} <= set(detail[0])


def test_method_not_allowed_keeps_its_allow_header(client):
    response = client.post("/tickers")
    assert response.status_code == 405
    assert "GET" in response.headers.get("allow", "")
    assert _strict_json(response)["detail"] == "Method Not Allowed"


def test_malformed_json_body_returns_422_json(client):
    response = client.post(
        "/portfolios", content=b"{not json", headers={"content-type": "application/json"}
    )
    assert response.status_code == 422
    _strict_json(response)


def test_every_audited_endpoint_returns_json_on_error(client):
    """A 4xx from any endpoint is JSON, never Starlette's plain-text default."""
    cases = [
        ("GET", "/tickers/NOPE/prices", None),
        ("GET", "/portfolios/999999", None),
        ("GET", "/simulation-runs/999999", None),
        ("GET", "/news", None),
        ("GET", "/news?category=bogus", None),
        ("GET", "/tickers/SPY/prices?limit=999999", None),
        ("POST", "/portfolios/999999/simulate", {"initial_balance": 1000}),
        ("POST", "/portfolios/999999/crisis-replay", {"crisis": "gfc_2008", "initial_balance": 1000}),
    ]
    for method, path, payload in cases:
        response = client.request(method, path, json=payload)
        assert response.status_code >= 400, f"{path} unexpectedly succeeded"
        assert response.headers["content-type"].startswith("application/json"), path
        _strict_json(response)
        _no_leaks(response)


# ---------------------------------------------------------------------------
# Bounded inputs keep every number in a response finite
# ---------------------------------------------------------------------------

def test_huge_balance_is_rejected_by_validation_not_by_the_engine(client):
    """A near-float-max balance used to surface a raw numpy message."""
    pid = client.post(
        "/portfolios", json={"name": "B", "holdings": [{"symbol": "SPY", "weight": 1.0}]}
    ).json()["id"]
    response = client.post(
        f"/portfolios/{pid}/simulate", json={"initial_balance": 1e308, "horizon_months": 12}
    )
    assert response.status_code == 422
    body = json.dumps(_strict_json(response))
    assert "numpy" not in body
    assert "autodetected range" not in body


def test_maximum_accepted_balance_produces_a_finite_response(client):
    """1e12 over 600 months stays inside float64 -- no Infinity in the body."""
    pid = client.post(
        "/portfolios", json={"name": "B", "holdings": [{"symbol": "SPY", "weight": 1.0}]}
    ).json()["id"]
    response = client.post(
        f"/portfolios/{pid}/simulate",
        json={"initial_balance": 1e12, "horizon_months": 600, "seed": 1},
    )
    assert response.status_code == 200
    assert "Infinity" not in response.text
    assert "NaN" not in response.text
    body = _strict_json(response)
    for band in body["percentiles"]:
        assert all(math.isfinite(v) for v in band["path"])
    assert all(math.isfinite(v) for v in body["stats"]["final_percentiles"].values())


# ---------------------------------------------------------------------------
# _safe(): the sanitizer itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value,expected",
    [
        (float("nan"), "nan"),
        (float("inf"), "inf"),
        (float("-inf"), "-inf"),
        (1.5, 1.5),
        (0.1, 0.1),
        (7, 7),
        (True, True),
        (None, None),
    ],
)
def test_safe_scalar_coercion(value, expected):
    assert _safe(value) == expected


def test_safe_truncates_long_strings():
    out = _safe("x" * 5000)
    assert len(out) < 5000
    assert out.endswith("...")


def test_safe_bounds_containers():
    out = _safe(list(range(100)))
    assert len(out) == 21
    assert out[-1] == "...(+80 more)"


def test_safe_survives_non_serializable_values():
    class Boom:
        def __repr__(self):
            return "<boom>"

    assert _safe({"error": Boom()}) == {"error": "<boom>"}
    # A self-referential structure must not recurse forever.
    cyclic: dict = {}
    cyclic["self"] = cyclic
    assert isinstance(_safe(cyclic), dict)


def test_safe_result_is_always_json_serializable():
    payload = _safe(
        {"a": float("nan"), "b": [float("inf"), {"c": float("-inf")}], "d": "y" * 1000}
    )
    assert json.loads(json.dumps(payload, allow_nan=False)) is not None
