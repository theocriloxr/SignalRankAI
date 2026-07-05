from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_USER_TIMEZONE = "UTC"
OWNER_DEFAULT_TIMEZONE = "Africa/Lagos"


def validate_timezone_name(value: str | None) -> str | None:
    name = str(value or "").strip()
    if not name:
        return None
    try:
        ZoneInfo(name)
        return name
    except (ZoneInfoNotFoundError, ValueError):
        return None


def effective_user_timezone(value: str | None, telegram_user_id: int | None = None) -> str:
    valid = validate_timezone_name(value)
    if valid:
        return valid
    try:
        from config import OWNER_IDS, ADMIN_IDS

        privileged = {int(item) for item in (OWNER_IDS or set())} | {
            int(item) for item in (ADMIN_IDS or set())
        }
        if telegram_user_id is not None and int(telegram_user_id) in privileged:
            return OWNER_DEFAULT_TIMEZONE
    except Exception:
        pass
    return DEFAULT_USER_TIMEZONE


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def format_user_datetime(
    value: datetime | None,
    timezone_name: str | None,
    telegram_user_id: int | None = None,
    *,
    include_date: bool = True,
) -> str:
    utc_value = as_utc(value)
    if utc_value is None:
        return "n/a"
    zone_name = effective_user_timezone(timezone_name, telegram_user_id)
    local = utc_value.astimezone(ZoneInfo(zone_name))
    pattern = "%Y-%m-%d %I:%M %p %Z" if include_date else "%I:%M %p %Z"
    return local.strftime(pattern).replace(" 0", " ")


def age_seconds(created_at: datetime | None, delivered_at: datetime | None = None) -> int | None:
    created = as_utc(created_at)
    delivered = as_utc(delivered_at) or datetime.now(timezone.utc)
    if created is None:
        return None
    return max(0, int((delivered - created).total_seconds()))
