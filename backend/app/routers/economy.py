"""Macro economy + external-intelligence endpoints (Phase 8).

Read-only surface over data that the offline ``intel_ingest`` CLI has already
stored. Serving a response never touches the network and never needs a provider
key, so a deployment with no keys configured still answers both endpoints --
``/economy/indicators`` just returns whatever was last ingested (possibly an
empty snapshot) and ``/economy/providers`` reports which upstreams are usable.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query

from ..dao import macro as macro_dao
from ..deps import get_db
from ..schemas import EconomyOut, MacroIndicatorOut, ProviderOut, ProvidersOut
from ..services.external_intel import provider_status

router = APIRouter(tags=["economy"])

MAX_INDICATORS = 500


@router.get("/economy/indicators", response_model=EconomyOut)
def get_economy_indicators(
    indicator: str | None = Query(default=None),
    country: str | None = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> EconomyOut:
    """Latest stored macro indicator snapshot, optionally filtered.

    Rows are capped at 500 in SQL so a wide table is never fully materialized.
    ``as_of`` is the newest ``fetched_at`` in the returned window, so a client
    can show data freshness without a second request.
    """
    rows = macro_dao.list_indicators(conn, indicator=indicator, country=country)
    rows = rows[:MAX_INDICATORS]
    as_of = max((r["fetched_at"] for r in rows), default=None)
    return EconomyOut(
        count=len(rows),
        as_of=as_of,
        indicators=[
            MacroIndicatorOut(
                country=r["country"],
                indicator=r["indicator"],
                label=r["label"],
                value=r["value"],
                unit=r["unit"],
                period=r["period"],
                source=r["source"],
            )
            for r in rows
        ],
    )


@router.get("/economy/providers", response_model=ProvidersOut)
def get_economy_providers() -> ProvidersOut:
    """Which external intelligence providers are configured for ingestion.

    Never reveals the keys themselves -- only whether each is present, so the
    frontend can explain why, e.g., Grok headlines are absent on a keyless
    deployment rather than showing an empty section with no reason.
    """
    return ProvidersOut(
        providers=[
            ProviderOut(name=p.name, configured=p.configured, description=p.description)
            for p in provider_status()
        ]
    )
