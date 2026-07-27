from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.tier_policy import get_entitlements


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
    execution_eligible: bool = False


TIER_ALLOWED_ASSETS = {
    tier: get_entitlements(tier).allowed_asset_classes
    for tier in ("free", "premium", "vip", "admin", "owner")
}


def get_tier_capabilities(tier: str | None) -> TierCapabilities:
    policy = get_entitlements(tier)
    normalized = policy.tier.value.lower()
    return TierCapabilities(
        tier=normalized,
        daily_limit=policy.daily_signal_limit,
        delivery_delay_minutes=policy.delivery_delay_minutes,
        max_tp_levels=policy.max_tp_levels,
        allowed_asset_classes=policy.allowed_asset_classes,
        signal_updates=policy.has("lifecycle_updates"),
        # Entitlement never activates unsafe execution. Pass 6 owns the
        # independent global/consent/risk/kill-switch execution gate.
        auto_trading=False,
        trade_management=policy.has("trade_management"),
        portfolio_analytics=policy.has("portfolio_analytics"),
        ai_coaching=policy.has("ai_coaching"),
        detail_level=policy.analytics_level,
        execution_eligible=policy.has("execution_preflight"),
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
