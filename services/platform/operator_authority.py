"""Owner/admin authority shared by the web operator API and Telegram operator views.

Configured owner Telegram IDs or a canonical OWNER tier make an owner; configured
admin IDs or a canonical ADMIN tier make an admin. Temporary bot unlocks never
grant operator authority here.
"""
from __future__ import annotations

from typing import Any


def operator_authority(*, telegram_user_id: Any, tier: Any) -> str | None:
    from config import (
        ADMIN_IDS,
        OWNER_IDS,
        OWNER_TELEGRAM_ID,
        OWNER_TELEGRAM_IDS,
    )

    telegram_id = int(telegram_user_id or 0)
    owner_ids = {int(value) for value in (OWNER_IDS or set())}
    owner_ids.update(int(value) for value in (OWNER_TELEGRAM_IDS or set()))
    if int(OWNER_TELEGRAM_ID or 0) > 0:
        owner_ids.add(int(OWNER_TELEGRAM_ID))
    if telegram_id > 0 and telegram_id in owner_ids:
        return "OWNER"

    canonical_tier = str(tier or "").strip().upper()
    if canonical_tier == "OWNER":
        return "OWNER"
    admin_ids = {int(value) for value in (ADMIN_IDS or set())}
    if telegram_id > 0 and telegram_id in admin_ids:
        return "ADMIN"
    if canonical_tier == "ADMIN":
        return "ADMIN"
    return None


__all__ = ["operator_authority"]
