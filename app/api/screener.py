"""Screener REST endpoints (P3-A3).

Now fully backed by the engine + the `screeners` DB table:
- `POST /screener/run` — `expr` path runs the live engine; `name` path
  resolves the saved expression from `screeners` and runs the same engine.
- `GET /screener/list` — returns all stored screeners (seeds + user-saved).
- `GET /screener/{name}` — returns one stored screener.

Schemas locked in `app/contracts/phase3.md`. The `_stub: true` marker has
been removed everywhere — Dev B's tests can now expect real data.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.screener import (
    ScreenerError,
    result_to_dict,
    run_screener,
)
from app.db.models.screener import Screener
from app.db.session import get_session

router = APIRouter(prefix="/screener", tags=["screener"])


_SCREENER_CACHE_TTL_S = 5 * 60  # 5 minutes — short enough that intra-day moves aren't masked


def _screener_cache_key(expr: str, limit: int) -> str:
    """Hash the expression + limit so semantically equivalent calls
    (different name/expr text but same query) collide cleanly. The hash
    is over the *resolved* expression, not the raw `name` — same body =
    same cache hit."""
    h = hashlib.sha256(f"{expr}|limit={limit}".encode()).hexdigest()[:16]
    return f"screener:run:{h}"


class ScreenerRunRequest(BaseModel):
    expr: str | None = Field(
        default=None, description="Expression like 'rsi_14 < 30 AND pe_trailing < 20'"
    )
    name: str | None = Field(default=None, description="Name of a saved screener")
    limit: int = Field(default=50, ge=1, le=100)


def _screener_to_dict(s: Screener) -> dict[str, Any]:
    return {
        "name": s.name,
        "expr": s.expr,
        "description": s.description,
        "is_seed": s.is_seed,
        "created_by": str(s.created_by) if s.created_by else None,
    }


@router.post("/run")
async def post_run_screener(
    req: ScreenerRunRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if not req.expr and not req.name:
        raise HTTPException(
            status_code=400, detail="either `expr` or `name` is required"
        )
    if req.expr and req.name:
        raise HTTPException(
            status_code=400, detail="pass `expr` OR `name`, not both"
        )

    # `name` path: resolve the saved expression from the DB, then run
    # the same engine. Single code path — same shape, same semantics.
    if req.name:
        s = (
            await session.execute(
                select(Screener).where(Screener.name == req.name)
            )
        ).scalar_one_or_none()
        if s is None:
            raise HTTPException(
                status_code=404, detail=f"screener {req.name!r} not found"
            )
        expr_str = s.expr
    else:
        expr_str = req.expr  # type: ignore[assignment]

    # P3-B6: Redis cache. Keyed on the *resolved* expression so the
    # `name` and `expr` paths collide for equivalent queries.
    redis = getattr(request.app.state, "redis", None)
    cache_key = _screener_cache_key(expr_str, req.limit)
    if redis is not None:
        try:
            cached = await redis.get(cache_key)
        except Exception:  # noqa: BLE001
            cached = None
        if cached:
            try:
                payload = json.loads(cached)
                payload["_cache"] = "hit"
                return payload
            except Exception:  # noqa: BLE001
                pass

    try:
        result = await run_screener(session, expr_str, limit=req.limit)
    except ScreenerError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    payload = result_to_dict(result)

    if redis is not None:
        try:
            await redis.set(
                cache_key, json.dumps(payload, default=str), ex=_SCREENER_CACHE_TTL_S
            )
        except Exception:  # noqa: BLE001
            pass
    payload["_cache"] = "miss"
    return payload


@router.get("/list")
async def list_screeners(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    rows = (
        await session.execute(select(Screener).order_by(Screener.name))
    ).scalars().all()
    return {"screeners": [_screener_to_dict(s) for s in rows]}


@router.get("/{name}")
async def get_screener(
    name: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    s = (
        await session.execute(select(Screener).where(Screener.name == name))
    ).scalar_one_or_none()
    if s is None:
        raise HTTPException(status_code=404, detail=f"screener {name!r} not found")
    return _screener_to_dict(s)
