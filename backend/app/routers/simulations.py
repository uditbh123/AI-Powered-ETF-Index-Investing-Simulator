"""Simulation trigger and result endpoints."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..dao import portfolios as portfolio_dao
from ..deps import SIMULATION_SLOTS, get_db
from ..schemas import SimulationRequest
from ..services.simulation import get_run_response, run_portfolio_simulation

router = APIRouter(tags=["simulations"])


@router.post("/portfolios/{portfolio_id}/simulate")
def trigger_simulation(
    portfolio_id: int,
    request: SimulationRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    # Existence is checked here (not left to the service's ValueError) so a
    # missing portfolio is a 404 like every other portfolio route, and the
    # service's ValueError is reserved for genuine "cannot simulate" reasons.
    if portfolio_dao.get_portfolio(conn, portfolio_id) is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    # Acquired after the 404 so an unknown id never consumes a slot. Non-blocking
    # on purpose: an overloaded server sheds load rather than piling blocked
    # threads onto an already-saturated pool (see SIMULATION_SLOTS).
    if not SIMULATION_SLOTS.acquire(blocking=False):
        raise HTTPException(
            status_code=503,
            detail="simulation capacity exhausted, retry shortly",
            headers={"Retry-After": "5"},
        )
    try:
        return run_portfolio_simulation(
            conn,
            portfolio_id,
            initial_balance=request.initial_balance,
            horizon_months=request.horizon_months,
            n_simulations=request.n_simulations,
            blocks=request.blocks,
            seed=request.seed,
            use_sentiment=request.use_sentiment,
            adjust_for_inflation=request.adjust_for_inflation,
            apply_capital_gains_tax=request.apply_capital_gains_tax,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        SIMULATION_SLOTS.release()


@router.get("/simulation-runs/{run_id}")
def get_simulation_run(run_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    response = get_run_response(conn, run_id)
    if response is None:
        raise HTTPException(status_code=404, detail="simulation run not found")
    return response