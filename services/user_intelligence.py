from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import text

from services.trade_profiles import normalize_trade_profile


RISK_PROFILES = {
    "ultra_conservative": {"risk_pct": 0.25, "min_score_boost": 8.0, "max_daily_loss_pct": 1.0, "max_open_trades": 1},
    "conservative": {"risk_pct": 0.5, "min_score_boost": 5.0, "max_daily_loss_pct": 2.0, "max_open_trades": 2},
    "balanced": {"risk_pct": 1.0, "min_score_boost": 0.0, "max_daily_loss_pct": 4.0, "max_open_trades": 4},
    "aggressive": {"risk_pct": 1.5, "min_score_boost": -3.0, "max_daily_loss_pct": 6.0, "max_open_trades": 6},
}

DEFAULT_ASSET_CLASSES = ("crypto", "fx", "commodity", "index", "stock")


@dataclass(slots=True)
class UserTradingPreferences:
    trade_profile: str = "all"
    risk_profile: str = "balanced"
    asset_classes: tuple[str, ...] = DEFAULT_ASSET_CLASSES
    preferred_assets: tuple[str, ...] = ()
    blocked_assets: tuple[str, ...] = ()
    sessions: tuple[str, ...] = ("auto",)
    notification_style: str = "normal"
    execution_mode: str = "manual"
    max_signals_per_day: int | None = None
    auto_trade_brokers: tuple[str, ...] = ()
    learned_preferences: dict[str, Any] = field(default_factory=dict)


def normalize_risk_profile(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_")
    aliases = {"safe": "conservative", "normal": "balanced", "medium": "balanced", "high": "aggressive"}
    raw = aliases.get(raw, raw)
    return raw if raw in RISK_PROFILES else "balanced"


def _tuple_from(value: Any, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        value = [v.strip() for v in value.split(",")]
    if not isinstance(value, (list, tuple, set)):
        value = [value]
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip().lower()
        if not text or text in seen:
            continue
        if text == "forex":
            text = "fx"
        if text == "indices":
            text = "index"
        seen.add(text)
        out.append(text)
    return tuple(out) if out else default


def preferences_from_payload(payload: dict[str, Any] | None) -> UserTradingPreferences:
    data = dict(payload or {})
    return UserTradingPreferences(
        trade_profile=normalize_trade_profile(data.get("trade_profile") or data.get("profile"), default="all"),
        risk_profile=normalize_risk_profile(data.get("risk_profile")),
        asset_classes=_tuple_from(data.get("asset_classes"), DEFAULT_ASSET_CLASSES),
        preferred_assets=tuple(str(x).upper().strip() for x in _tuple_from(data.get("preferred_assets"))),
        blocked_assets=tuple(str(x).upper().strip() for x in _tuple_from(data.get("blocked_assets"))),
        sessions=_tuple_from(data.get("sessions"), ("auto",)),
        notification_style=str(data.get("notification_style") or "normal").strip().lower(),
        execution_mode=str(data.get("execution_mode") or "manual").strip().lower(),
        max_signals_per_day=int(data["max_signals_per_day"]) if data.get("max_signals_per_day") is not None else None,
        auto_trade_brokers=_tuple_from(data.get("auto_trade_brokers")),
        learned_preferences=dict(data.get("learned_preferences") or {}),
    )


def preferences_to_payload(prefs: UserTradingPreferences) -> dict[str, Any]:
    payload = asdict(prefs)
    for key, value in list(payload.items()):
        if isinstance(value, tuple):
            payload[key] = list(value)
    return payload


async def get_user_trading_preferences(session, telegram_user_id: int) -> UserTradingPreferences:
    key = f"trading_preferences:{int(telegram_user_id)}"
    row = await session.execute(text("SELECT value FROM runtime_state WHERE key = :key"), {"key": key})
    raw = row.scalar_one_or_none()
    if isinstance(raw, dict):
        return preferences_from_payload(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return preferences_from_payload(parsed)
        except Exception:
            pass
    # Keep backward compatibility with the older single-value trade profile.
    try:
        from services.trade_profiles import get_user_trade_profile

        trade_profile = await get_user_trade_profile(session, telegram_user_id)
    except Exception:
        trade_profile = "all"
    return UserTradingPreferences(trade_profile=trade_profile)


async def set_user_trading_preferences(session, telegram_user_id: int, prefs: UserTradingPreferences) -> UserTradingPreferences:
    payload = json.dumps(preferences_to_payload(prefs))
    await session.execute(
        text(
            """
            INSERT INTO runtime_state(key, value, expires_at, updated_at)
            VALUES (:key, CAST(:value AS JSONB), NULL, NOW())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, expires_at = NULL, updated_at = NOW()
            """
        ),
        {"key": f"trading_preferences:{int(telegram_user_id)}", "value": payload},
    )
    # Also maintain the legacy key used by earlier dispatch code.
    await session.execute(
        text(
            """
            INSERT INTO runtime_state(key, value, expires_at, updated_at)
            VALUES (:key, CAST(:value AS JSONB), NULL, NOW())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, expires_at = NULL, updated_at = NOW()
            """
        ),
        {
            "key": f"trade_profile:{int(telegram_user_id)}",
            "value": json.dumps({"profile": prefs.trade_profile}),
        },
    )
    return prefs


def risk_profile_settings(name: str | None) -> dict[str, float]:
    return dict(RISK_PROFILES[normalize_risk_profile(name)])


def signal_matches_preferences(signal: dict[str, Any], prefs: UserTradingPreferences) -> tuple[bool, str]:
    asset = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()
    asset_class = str(signal.get("asset_class") or "").lower().strip()
    if asset_class == "forex":
        asset_class = "fx"
    if prefs.asset_classes and asset_class and asset_class not in prefs.asset_classes:
        return False, f"asset_class:{asset_class}"
    if asset and asset in prefs.blocked_assets:
        return False, "blocked_asset"
    if prefs.preferred_assets and asset and asset not in prefs.preferred_assets:
        return False, "not_preferred_asset"
    session = str(signal.get("market_session") or "").lower().strip()
    if prefs.sessions and "auto" not in prefs.sessions and session:
        if not any(s in session for s in prefs.sessions):
            return False, f"session:{session}"
    if prefs.trade_profile and prefs.trade_profile != "all":
        from services.trade_profiles import signal_matches_user_profile

        if not signal_matches_user_profile(signal, prefs.trade_profile):
            return False, f"profile:{prefs.trade_profile}"
    return True, "ok"


def format_preferences(prefs: UserTradingPreferences) -> str:
    return "\n".join(
        [
            "AI Trading Profile",
            "",
            f"Style: {prefs.trade_profile}",
            f"Risk: {prefs.risk_profile}",
            f"Assets: {', '.join(prefs.asset_classes)}",
            f"Sessions: {', '.join(prefs.sessions)}",
            f"Notifications: {prefs.notification_style}",
            f"Execution: {prefs.execution_mode}",
            "",
            "Examples:",
            "/profile day",
            "/profile risk conservative",
            "/profile assets forex crypto index",
            "/profile sessions london new_york",
            "/profile execution manual",
        ]
    )
