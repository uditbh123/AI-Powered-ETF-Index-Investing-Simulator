"""Simulation trigger and result endpoints."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_db
from ..schemas import SimulationRequest
from ..services.simulation import get_run_response, run_portfolio_simulation

router = APIRouter(tags=["simulations"])


@router.post("/portfolios/{portfolio_id}/simulate")
def trigger_simulation(
    portfolio_id: int,
    request: SimulationRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    try:
        return run_portfolio_simulation(
            conn,
            portfolio_id,
            initial_balance=request.initial_balance,
            horizon_months=request.horizon_months,
            n_simulations=request.n_simulations,
            blocks=request.blocks,
            seed=request.seed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/simulation-runs/{run_id}")
def get_simulation_run(run_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    response = get_run_response(conn, run_id)
    if response is None:
        raise HTTPException(status_code=404, detail="simulation run not found")
    return response