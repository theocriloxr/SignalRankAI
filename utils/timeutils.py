from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def now_utc_naive() -> datetime:
    """Return current UTC time as an offset-naive datetime (naive UTC).

    This is a stop-gap for databases that expect naive datetimes. Prefer
    storing timestamptz in the DB and using aware datetimes everywhere.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert any datetime to offset-naive UTC.

    - If dt is None, returns None.
    - If dt is timezone-aware, convert to UTC and drop tzinfo.
    - If dt is already naive, return as-is.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def to_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert any datetime to timezone-aware UTC (tzinfo=UTC).

    - If dt is None, returns None.
    - If dt is naive, attach UTC tzinfo.
    - If dt already has tzinfo, convert to UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
