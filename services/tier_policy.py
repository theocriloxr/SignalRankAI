from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from core.tier_constants import get_daily_limit, normalize_tier


@dataclass(frozen=True, slots=True)
class TierCapabilities:
    tier: str
    daily_limit: int
    delivery_delay_minutes: int
    max_tp_levels: int
    allowed_asset_classes: tuple[str, ...]
    signal_updates: bool
    auto_trading: bool
    trade_management: bool
    portfolio_analytics: bool
    ai_coaching: bool
    detail_level: str


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, str(default)) or default))
    except Exception:
        return int(default)


TIER_ALLOWED_ASSETS = {
    "free": ("crypto", "fx"),
    "premium": ("crypto", "fx", "commodity", "index", "stock"),
    "vip": ("crypto", "fx", "commodity", "index", "stock"),
    "admin": ("crypto", "fx", "commodity", "index", "stock"),
    "owner": ("crypto", "fx", "commodity", "index", "stock"),
}


def get_tier_capabilities(tier: str | None) -> TierCapabilities:
    normalized = normalize_tier(tier)
    if normalized == "free":
        return TierCapabilities(
            tier="free",
            daily_limit=int(get_daily_limit("free")),
            delivery_delay_minutes=_env_int("FREE_SIGNAL_DELAY_MINUTES", 10),
            max_tp_levels=1,
            allowed_asset_classes=TIER_ALLOWED_ASSETS["free"],
            signal_updates=False,
            auto_trading=False,
            trade_management=False,
            portfolio_analytics=False,
            ai_coaching=False,
            detail_level="basic",
        )
    if normalized == "premium":
        return TierCapabilities(
            tier="premium",
            daily_limit=int(get_daily_limit("premium")),
            delivery_delay_minutes=_env_int("PREMIUM_SIGNAL_DELAY_MINUTES", 0),
            max_tp_levels=2,
            allowed_asset_classes=TIER_ALLOWED_ASSETS["premium"],
            signal_updates=True,
            auto_trading=False,
            trade_management=True,
            portfolio_analytics=True,
            ai_coaching=False,
            detail_level="detailed",
        )
    if normalized == "vip":
        return TierCapabilities(
            tier="vip",
            daily_limit=int(get_daily_limit("vip")),
            delivery_delay_minutes=_env_int("VIP_SIGNAL_DELAY_MINUTES", 0),
            max_tp_levels=3,
            allowed_asset_classes=TIER_ALLOWED_ASSETS["vip"],
            signal_updates=True,
            auto_trading=True,
            trade_management=True,
            portfolio_analytics=True,
            ai_coaching=True,
            detail_level="professional",
        )
    return TierCapabilities(
        tier=normalized,
        daily_limit=int(get_daily_limit(normalized)),
        delivery_delay_minutes=0,
        max_tp_levels=3,
        allowed_asset_classes=TIER_ALLOWED_ASSETS["owner"],
        signal_updates=True,
        auto_trading=True,
        trade_management=True,
        portfolio_analytics=True,
        ai_coaching=True,
        detail_level="owner",
    )


def tier_allows_signal(signal: dict[str, Any], tier: str | None) -> tuple[bool, str]:
    caps = get_tier_capabilities(tier)
    asset_class = str(signal.get("asset_class") or signal.get("class") or "").lower().strip()
    if asset_class == "forex":
        asset_class = "fx"
    if asset_class and asset_class not in caps.allowed_asset_classes:
        return False, f"{caps.tier}_asset_class_block:{asset_class}"
    return True, "ok"


def apply_tier_visibility(signal: dict[str, Any], tier: str | None) -> dict[str, Any]:
    caps = get_tier_capabilities(tier)
    out = dict(signal or {})
    raw_tp = out.get("take_profit") or out.get("targets") or []
    if not isinstance(raw_tp, (list, tuple)):
        raw_tp = [raw_tp] if raw_tp else []
    out["visible_take_profit"] = list(raw_tp)[: caps.max_tp_levels]
    out["tier_detail_level"] = caps.detail_level
    out["tier_delivery_delay_minutes"] = caps.delivery_delay_minutes
    out["tier_signal_updates"] = caps.signal_updates
    out["tier_auto_trading"] = caps.auto_trading
    return out
