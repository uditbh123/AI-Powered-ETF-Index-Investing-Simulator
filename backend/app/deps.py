"""Shared FastAPI dependencies."""
from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator

from .database import get_connection


def get_db() -> Iterator[sqlite3.Connection]:
    """Provide a per-request SQLite connection, always closed on exit."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


#: Cap on concurrent simulations, bounding *peak memory* rather than per-request
#: work. `MAX_PATH_STEPS` already caps a single request at 20M path-steps, but a
#: cap that only applies to one request bounds nothing: Starlette runs these sync
#: handlers in its default 40-thread pool, so N clients cost N times the same
#: peak. Measured worst legal request (33,333 paths x 600 months): ~800 MB
#: allocated, ~5x the 160 MB result array because `cumprod` and the annuity
#: discount each allocate a full copy. 40 of those is ~32 GB.
#:
#: Varying `seed` evades the run cache entirely (`canonical_params` keys on it),
#: so cache hits cannot be relied on to absorb a burst.
#:
#: This is deliberately an *admission* control rather than a queue: the acquire
#: is non-blocking, so an overloaded server sheds load with a 503 instead of
#: accumulating blocked threads holding open DB connections. Two slots is
#: conservative for the measured footprint and leaves headroom on a 2 GB box.
SIMULATION_SLOTS = threading.Semaphore(2)


__all__ = ["get_db", "SIMULATION_SLOTS"]