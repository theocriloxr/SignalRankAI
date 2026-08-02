"""Canonical per-user same-asset repeat-lock policy.

The durable decision is made from PostgreSQL delivery proof. Redis keys created
here are accelerators only and must never be treated as proof that a Telegram
message was sent.
"""

from __future__ import annotations

import math
import os
from typing import Iterable

DEFAULT_ASSET_REPEAT_LOCK_HOURS = 4.0


def _env_float(name: str) -> float | None:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return None
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def get_asset_repeat_lock_hours(tier: str | None = None) -> float:
    """Return the proof-backed same-asset lock duration for every tier.

    The global four-hour product rule is authoritative. Tier-specific values are
    ignored unless ``ALLOW_TIER_ASSET_COOLDOWN_OVERRIDES=1``. Even then, they can
    only make the lock stricter unless an additional audited reduction switch is
    enabled. This prevents owner/admin environment leftovers from silently
    disabling the product safety gate.
    """

    global_candidates: Iterable[float | None] = (
        _env_float("DELIVERY_SAME_ASSET_COOLDOWN_HOURS"),
        _env_float("ASSET_REPEAT_LOCK_HOURS"),
        DEFAULT_ASSET_REPEAT_LOCK_HOURS,
    )
    base = DEFAULT_ASSET_REPEAT_LOCK_HOURS
    for value in global_candidates:
        if value is not None:
            base = max(0.0, float(value))
            break

    if not _env_bool("ALLOW_TIER_ASSET_COOLDOWN_OVERRIDES", False):
        return base

    tier_name = str(tier or "").strip().lower().split("_", 1)[0]
    tier_env = {
        "vip": "VIP_ASSET_COOLDOWN_HOURS",
        "owner": "VIP_ASSET_COOLDOWN_HOURS",
        "admin": "VIP_ASSET_COOLDOWN_HOURS",
        "premium": "PREMIUM_ASSET_COOLDOWN_HOURS",
        "free": "FREE_ASSET_COOLDOWN_HOURS",
    }.get(tier_name)
    override = _env_float(tier_env) if tier_env else None
    if override is None:
        return base
    override = max(0.0, float(override))
    if _env_bool("ALLOW_ASSET_COOLDOWN_REDUCTION", False):
        return override
    return max(base, override)


def canonical_delivery_cooldown_key(user_id: int, asset: str) -> str:
    """Direction-agnostic Redis accelerator key for one user and asset."""

    symbol = str(asset or "").upper().strip()
    return f"delivery_asset:{int(user_id)}:{symbol}"


def legacy_delivery_cooldown_keys(user_id: int, asset: str, direction: str | None = None) -> tuple[str, ...]:
    """Legacy keys read during migration so existing cooldowns are honoured."""

    symbol = str(asset or "").upper().strip()
    side = str(direction or "").upper().strip()
    keys = [f"delivery:{int(user_id)}:{symbol}:{side}", f"delivery_cool:{int(user_id)}:{symbol}:{side}"]
    return tuple(key for key in keys if side)
