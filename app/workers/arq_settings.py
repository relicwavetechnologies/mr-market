"""arq cron settings — Phase-2 nightly EOD pipeline.

Run with:  uv run arq app.workers.arq_settings.WorkerSettings
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from arq.connections import RedisSettings
from arq.cron import cron

from app.config import get_settings
from app.db.session import SessionLocal
from app.workers.eod_ingest import ingest_one_day

logger = logging.getLogger(__name__)


def _redis_settings() -> RedisSettings:
    """Parse `redis://[:pass@]host:port/db` into arq's RedisSettings."""
    s = get_settings()
    return RedisSettings.from_dsn(s.redis_url)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


async def task_eod_yesterday(_ctx) -> dict:
    """Cron entry point — pull yesterday's bhavcopy."""
    target = date.today() - timedelta(days=1)
    async with SessionLocal() as session:
        stats = await ingest_one_day(session, target)
    return {"trade_date": stats.trade_date, "fetched": stats.fetched,
            "upserted": stats.upserted, "error": stats.error}


async def task_eod_for_date(_ctx, ymd: str) -> dict:
    """On-demand task; ymd format YYYY-MM-DD."""
    target = date.fromisoformat(ymd)
    async with SessionLocal() as session:
        stats = await ingest_one_day(session, target)
    return {"trade_date": stats.trade_date, "fetched": stats.fetched,
            "upserted": stats.upserted, "error": stats.error}


# ---------------------------------------------------------------------------
# WorkerSettings — discovered by `arq` CLI
# ---------------------------------------------------------------------------


class WorkerSettings:
    redis_settings = _redis_settings()
    functions = [task_eod_for_date]

    # 04:00 IST = 22:30 UTC the previous day. arq's cron runs in UTC.
    # NSE bhavcopy is normally available by ~18:30 IST (13:00 UTC), so 22:30
    # UTC gives us a generous safety margin.
    cron_jobs = [
        cron(
            task_eod_yesterday,
            hour={22},
            minute={30},
            run_at_startup=False,
            unique=True,
            timeout=600,
        ),
    ]
