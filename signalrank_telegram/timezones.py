from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_USER_TIMEZONE = "UTC"
OWNER_DEFAULT_TIMEZONE = "Africa/Lagos"
COMMON_TIMEZONES = (
    "Africa/Lagos",
    "Europe/London",
    "America/New_York",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Europe/Berlin",
)
TIMEZONE_ALIASES = {
    "lagos": "Africa/Lagos",
    "nigeria": "Africa/Lagos",
    "wat": "Africa/Lagos",
    "london": "Europe/London",
    "uk": "Europe/London",
    "new york": "America/New_York",
    "new_york": "America/New_York",
    "nyc": "America/New_York",
    "dubai": "Asia/Dubai",
    "uae": "Asia/Dubai",
    "india": "Asia/Kolkata",
    "kolkata": "Asia/Kolkata",
    "berlin": "Europe/Berlin",
}


def validate_timezone_name(value: str | None) -> str | None:
    name = str(value or "").strip()
    if not name:
        return None


def resolve_timezone_query(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    alias = TIMEZONE_ALIASES.get(raw.lower())
    return alias or validate_timezone_name(raw)


def timezone_from_coordinates(latitude: float, longitude: float) -> str | None:
    try:
        from timezonefinder import TimezoneFinder

        timezone_name = TimezoneFinder(in_memory=True).timezone_at(
            lat=float(latitude), lng=float(longitude)
        )
        return validate_timezone_name(timezone_name)
    except Exception:
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
    if str(os.getenv("SIGNAL_TIMEZONE_DISPLAY_ENABLED", "1")).lower() in {"0", "false", "off", "no"}:
        timezone_name = "UTC"
    zone_name = effective_user_timezone(timezone_name, telegram_user_id)
    local = utc_value.astimezone(ZoneInfo(zone_name))
    pattern = "%Y-%m-%d %I:%M %p %Z" if include_date else "%I:%M %p %Z"
    return local.strftime(pattern).replace(" 0", " ")


def format_user_time(value: datetime | None, user: object, *, include_date: bool = True) -> str:
    """Single user-object entry point used by Telegram message renderers."""
    if str(os.getenv("SIGNAL_TIMEZONE_DISPLAY_ENABLED", "1")).lower() in {"0", "false", "off", "no"}:
        return format_user_datetime(value, "UTC", getattr(user, "telegram_user_id", None), include_date=include_date)
    timezone_name = getattr(user, "timezone", None)
    telegram_user_id = getattr(user, "telegram_user_id", None)
    rendered = format_user_datetime(value, timezone_name, telegram_user_id, include_date=include_date)
    if str(getattr(user, "time_format", "12h") or "12h").lower() == "24h":
        utc_value = as_utc(value)
        if utc_value is not None:
            zone_name = effective_user_timezone(timezone_name, telegram_user_id)
            local = utc_value.astimezone(ZoneInfo(zone_name))
            pattern = "%Y-%m-%d %H:%M %Z" if include_date else "%H:%M %Z"
            rendered = local.strftime(pattern)
    return rendered


def travel_timezone_refresh_due(user: object, *, days: int | None = None) -> bool:
    if not bool(getattr(user, "timezone_auto_update", False)):
        return False
    updated_at = as_utc(getattr(user, "timezone_updated_at", None))
    if updated_at is None:
        return True
    interval_days = days or int(os.getenv("TRAVEL_TIMEZONE_REFRESH_DAYS", "14") or 14)
    return datetime.now(timezone.utc) - updated_at >= timedelta(days=max(1, interval_days))


def should_store_location_coordinates() -> bool:
    return str(os.getenv("TIMEZONE_STORE_LOCATION_COORDINATES", "0") or "0").lower() in {
        "1", "true", "yes", "on",
    }


def age_seconds(created_at: datetime | None, delivered_at: datetime | None = None) -> int | None:
    created = as_utc(created_at)
    delivered = as_utc(delivered_at) or datetime.now(timezone.utc)
    if created is None:
        return None
    return max(0, int((delivered - created).total_seconds()))
