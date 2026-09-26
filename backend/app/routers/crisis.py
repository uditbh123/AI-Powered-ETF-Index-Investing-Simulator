"""Crisis replay endpoint: re-run a portfolio through a historical window."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..dao import portfolios as portfolio_dao
from ..deps import get_db
from ..schemas import CrisisReplayRequest
from ..services.crisis import run_crisis_replay

router = APIRouter(tags=["crisis"])


@router.post("/portfolios/{portfolio_id}/crisis-replay")
def replay_crisis(
    portfolio_id: int,
    request: CrisisReplayRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Replay a portfolio through a fixed historical crisis window.

    Compounds the portfolio's realized monthly returns over the window
    (contributions at the start of each month, matching the simulator engine)
    and also returns 10/50/90 percentile bands resampled from the full history
    with a fixed seed. See ``docs/data_methodology.md`` for the window
    boundaries. Returns 404 for a missing portfolio and 400 when the history
    does not cover the window.
    """
    if portfolio_dao.get_portfolio(conn, portfolio_id) is None:
        raise HTTPException(status_code=404, detail="portfolio not found")
    try:
        return run_crisis_replay(
            conn,
            portfolio_id,
            crisis=request.crisis,
            initial_balance=request.initial_balance,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc