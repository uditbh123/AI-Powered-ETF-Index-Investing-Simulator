"""Portfolio DAO: users, portfolios, and portfolio_holdings."""
from __future__ import annotations

import sqlite3


def get_or_create_user(conn: sqlite3.Connection, name: str = "default") -> int:
    """MVP has no auth; a single default user is auto-created on demand."""
    row = conn.execute("SELECT id FROM users WHERE name = ?", (name,)).fetchone()
    if row is not None:
        return row["id"]
    return conn.execute("INSERT INTO users (name) VALUES (?)", (name,)).lastrowid


def create_portfolio(
    conn: sqlite3.Connection,
    user_id: int,
    name: str,
    monthly_contribution: float,
    start_date: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO portfolios (user_id, name, monthly_contribution, start_date) "
        "VALUES (?, ?, ?, ?)",
        (user_id, name, monthly_contribution, start_date),
    )
    return cur.lastrowid


def get_portfolio(conn: sqlite3.Connection, portfolio_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, user_id, name, monthly_contribution, start_date "
        "FROM portfolios WHERE id = ?",
        (portfolio_id,),
    ).fetchone()


def list_portfolios(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, user_id, name, monthly_contribution, start_date "
        "FROM portfolios ORDER BY id"
    ).fetchall()


def add_holding(
    conn: sqlite3.Connection,
    portfolio_id: int,
    ticker_id: int,
    weight: float,
) -> int:
    cur = conn.execute(
        "INSERT INTO portfolio_holdings (portfolio_id, ticker_id, weight) VALUES (?, ?, ?)",
        (portfolio_id, ticker_id, weight),
    )
    return cur.lastrowid


def list_holdings(conn: sqlite3.Connection, portfolio_id: int) -> list[sqlite3.Row]:
    """Holdings joined to tickers so callers get symbol + name."""
    return conn.execute(
        """
        SELECT h.id, h.portfolio_id, h.ticker_id, h.weight, t.symbol, t.name, t.sector
        FROM portfolio_holdings h
        JOIN tickers t ON t.id = h.ticker_id
        WHERE h.portfolio_id = ?
        ORDER BY h.id
        """,
        (portfolio_id,),
    ).fetchall()


def delete_portfolio(conn: sqlite3.Connection, portfolio_id: int) -> bool:
    """Delete a portfolio and everything it owns, FK-safe.

    Child rows are removed in dependency order before the portfolio row:
    simulation_results first (they reference simulation_runs), then the runs,
    then holdings, then the portfolio itself. Returns False when the portfolio
    does not exist (no deletes performed). Foreign keys are enforced per
    connection, so an out-of-order delete would otherwise fail.
    """
    exists = conn.execute(
        "SELECT id FROM portfolios WHERE id = ?", (portfolio_id,)
    ).fetchone()
    if exists is None:
        return False

    conn.execute(
        "DELETE FROM simulation_results WHERE run_id IN "
        "(SELECT id FROM simulation_runs WHERE portfolio_id = ?)",
        (portfolio_id,),
    )
    conn.execute(
        "DELETE FROM simulation_runs WHERE portfolio_id = ?", (portfolio_id,)
    )
    conn.execute(
        "DELETE FROM portfolio_holdings WHERE portfolio_id = ?", (portfolio_id,)
    )
    conn.execute("DELETE FROM portfolios WHERE id = ?", (portfolio_id,))
    return True


__all__ = [
    "get_or_create_user",
    "create_portfolio",
    "get_portfolio",
    "list_portfolios",
    "add_holding",
    "list_holdings",
    "delete_portfolio",
]