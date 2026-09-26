"""Uniform, leak-free JSON error responses.

Two properties the API guarantees for every error, established by the Stage L4
hostile-input audit:

* **Every error body is JSON.** Starlette's default 500 is ``text/plain
  "Internal Server Error"``, and its 422 handler renders pydantic's error
  payload with ``allow_nan=False``. Python's ``json`` module happily *parses*
  the non-standard ``NaN`` / ``Infinity`` tokens, so a body containing one
  produces a validation error whose ``input`` field is ``NaN``; serializing
  that raises ``ValueError: Out of range float values are not JSON
  compliant``, escapes the validation handler, and degrades a would-be 422 into
  a plain-text 500. :func:`install_error_handlers` sanitizes the payload first
  so the answer stays a 422 JSON body.

* **No internal detail reaches the client.** Unhandled exceptions are logged
  with their traceback via ``logger.exception`` (server logs only) and the
  client receives a fixed, safe message.

The 4xx shapes are unchanged from FastAPI's defaults -- ``{"detail": "..."}``
for raised ``HTTPException``s and ``{"detail": [{...}]}`` for validation
errors -- because the SPA reads ``body.detail`` in ``frontend/src/api.js``.
"""
from __future__ import annotations

import logging
import math
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")

# Longest rendered value kept in a 422 payload. Pydantic echoes the offending
# input verbatim, which is unbounded (a 1000-element holdings array, a
# multi-kilobyte symbol), so responses are trimmed to keep error bodies small.
MAX_VALUE_CHARS = 200

#: Fixed client-facing message for an unexpected server-side failure.
INTERNAL_ERROR_DETAIL = "internal server error"


def _safe_float(value: float) -> float | str:
    """Return a JSON-safe float, spelling out the non-finite ones.

    ``NaN``/``Infinity`` have no JSON representation, so they are returned as
    their ``repr`` string. This is what keeps a ``NaN`` request body on the 422
    path instead of blowing up the error handler itself.
    """
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return value


def _safe(value: Any, *, depth: int = 0) -> Any:
    """Coerce an arbitrary pydantic error payload into JSON-safe primitives.

    Recursion and container size are both bounded: pydantic errors nest
    (``ctx.error`` holds an exception) and echo caller-controlled collections,
    so an unbounded walk would risk a circular reference or a huge body.
    """
    if value is None or isinstance(value, (bool, int, str)):
        if isinstance(value, str) and len(value) > MAX_VALUE_CHARS:
            return value[:MAX_VALUE_CHARS] + "..."
        return value
    if isinstance(value, float):
        return _safe_float(value)
    if depth >= 4:
        return repr(value)[:MAX_VALUE_CHARS]
    if isinstance(value, dict):
        return {str(k): _safe(v, depth=depth + 1) for k, v in list(value.items())[:20]}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_safe(v, depth=depth + 1) for v in list(value)[:20]]
        if len(value) > 20:
            items.append(f"...(+{len(value) - 20} more)")
        return items
    return repr(value)[:MAX_VALUE_CHARS]


def _validation_detail(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Render ``exc.errors()`` as a bounded, JSON-safe detail list."""
    errors = exc.errors()
    detail: list[dict[str, Any]] = []
    for err in errors[:20]:
        entry: dict[str, Any] = {
            "type": str(err.get("type", "validation_error")),
            "loc": [str(part) for part in err.get("loc", ())],
            "msg": str(err.get("msg", "invalid input")),
        }
        if "input" in err:
            entry["input"] = _safe(err["input"])
        if "ctx" in err:
            entry["ctx"] = _safe(err["ctx"])
        detail.append(entry)
    if len(errors) > 20:
        detail.append({"type": "truncated", "msg": f"...(+{len(errors) - 20} more errors)"})
    return detail


def install_error_handlers(app: FastAPI) -> None:
    """Register the JSON-only, leak-free error handlers on ``app``."""

    @app.exception_handler(RequestValidationError)
    async def _on_validation_error(_request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": _validation_detail(exc)})

    @app.exception_handler(StarletteHTTPException)
    async def _on_http_exception(_request, exc: StarletteHTTPException) -> JSONResponse:
        # Mirrors FastAPI's default {"detail": ...} body (which the SPA reads)
        # but sanitized, so an HTTPException carrying a non-finite float or a
        # huge string still serializes.
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": _safe(exc.detail)},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _on_unhandled_exception(_request, exc: Exception) -> JSONResponse:
        # Full traceback to the server log; a fixed, safe message to the client.
        logger.exception("unhandled error while serving a request: %s", exc)
        return JSONResponse(status_code=500, content={"detail": INTERNAL_ERROR_DETAIL})


__all__ = ["install_error_handlers", "INTERNAL_ERROR_DETAIL", "MAX_VALUE_CHARS"]
