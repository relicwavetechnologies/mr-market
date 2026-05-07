"""STUB endpoints for the Phase-3 watchlist surface.

Day-1 hand-off from Dev A → Dev B. Real implementation in P3-A7 (per-user
persistence + daily-digest cron). Schemas locked in
`app/contracts/phase3.md`.

The stub keeps state in a process-local set so Dev B can wire
`add_to_watchlist` end-to-end with realistic behaviour (add → list shows the
new ticker → delete → list shrinks). State resets on backend restart, which
is fine for the day-1 hand-off; real persistence lands in A-7.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

# Process-local stub state. Anonymous user only — real impl uses PM-1 auth.
_WATCHLIST: set[str] = set()


class WatchlistAddRequest(BaseModel):
    ticker: str


def _resp(ok: bool = True) -> dict[str, Any]:
    return {
        "ok": ok,
        "tickers": sorted(_WATCHLIST),
        "size": len(_WATCHLIST),
        "_stub": True,
    }


@router.get("")
async def list_watchlist() -> dict[str, Any]:
    return _resp()


@router.post("")
async def add_to_watchlist(req: WatchlistAddRequest) -> dict[str, Any]:
    sym = req.ticker.strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="ticker required")
    _WATCHLIST.add(sym)
    return _resp()


@router.delete("/{ticker}")
async def remove_from_watchlist(ticker: str) -> dict[str, Any]:
    sym = ticker.strip().upper()
    if sym not in _WATCHLIST:
        raise HTTPException(status_code=404, detail=f"{sym!r} not in watchlist")
    _WATCHLIST.discard(sym)
    return _resp()
