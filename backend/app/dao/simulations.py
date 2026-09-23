"""Simulation run DAO: persistence + lookup of cached Monte Carlo results."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable


def create_run(
    conn: sqlite3.Connection,
    portfolio_id: int,
    params_json: str,
    stats_json: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO simulation_runs (portfolio_id, params_json, stats_json) "
        "VALUES (?, ?, ?)",
        (portfolio_id, params_json, stats_json),
    )
    return cur.lastrowid


_RUN_COLUMNS = "id, portfolio_id, params_json, stats_json, created_at"


def get_run(conn: sqlite3.Connection, run_id: int) -> sqlite3.Row | None:
    return conn.execute(
        f"SELECT {_RUN_COLUMNS} " "FROM simulation_runs WHERE id = ?",
        (run_id,),
    ).fetchone()


def find_cached_run(
    conn: sqlite3.Connection,
    portfolio_id: int,
    params_json: str,
) -> sqlite3.Row | None:
    """Return the most recent run for a portfolio with identical parameters."""
    return conn.execute(
        f"SELECT {_RUN_COLUMNS} "
        "FROM simulation_runs WHERE portfolio_id = ? AND params_json = ? "
        "ORDER BY id DESC LIMIT 1",
        (portfolio_id, params_json),
    ).fetchone()


def list_runs(conn: sqlite3.Connection, portfolio_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        f"SELECT {_RUN_COLUMNS} "
        "FROM simulation_runs WHERE portfolio_id = ? ORDER BY id DESC",
        (portfolio_id,),
    ).fetchall()


def has_results(conn: sqlite3.Connection, run_id: int) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM simulation_results WHERE run_id = ? LIMIT 1", (run_id,)
        ).fetchone()
        is not None
    )


def save_results(
    conn: sqlite3.Connection,
    run_id: int,
    results: Iterable[tuple[float, str]],
) -> int:
    """Persist (percentile, path_json) rows for a run. Returns rows written."""
    cur = conn.executemany(
        "INSERT INTO simulation_results (run_id, percentile, path_json) VALUES (?, ?, ?)",
        [(run_id, level, path) for level, path in results],
    )
    return cur.rowcount


def get_results(conn: sqlite3.Connection, run_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT percentile, path_json FROM simulation_results "
        "WHERE run_id = ? ORDER BY percentile",
        (run_id,),
    ).fetchall()


__all__ = [
    "create_run",
    "get_run",
    "find_cached_run",
    "list_runs",
    "has_results",
    "save_results",
    "get_results",
]