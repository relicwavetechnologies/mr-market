"""Indian market regular trading hours (RTH) check in IST."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
_OPEN = time(9, 15)
_CLOSE = time(15, 30)


def is_rth(now_utc: datetime | None = None) -> bool:
    """Return True if the NSE/BSE regular session is currently open.

    Mon-Fri 09:15-15:30 IST. Holiday calendar not modelled here — out of
    scope for Phase 1; cache TTL is short enough that it self-corrects.
    """
    now = (now_utc or datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))).astimezone(IST)
    if now.weekday() >= 5:
        return False
    return _OPEN <= now.time() <= _CLOSE
