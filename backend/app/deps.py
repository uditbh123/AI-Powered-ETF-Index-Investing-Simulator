"""Shared FastAPI dependencies."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from .database import get_connection


def get_db() -> Iterator[sqlite3.Connection]:
    """Provide a per-request SQLite connection, always closed on exit."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


__all__ = ["get_db"]