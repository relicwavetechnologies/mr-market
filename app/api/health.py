from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    db_ok = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        db_ok = f"error: {e!s}"
    return {"status": "ok", "db": db_ok}


@router.get("/")
async def root() -> dict[str, str]:
    return {"app": "mr-market", "phase": "1-local-demo"}
