from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from sqlalchemy import text

from services.trade_profiles import normalize_trade_profile


RISK_PROFILES = {
    "ultra_conservative": {
        "risk_pct": 0.25,
        "min_score_boost": 8.0,
        "max_daily_loss_pct": 1.0,
        "max_open_trades": 1,
    },
    "conservative": {
        "risk_pct": 0.5,
        "min_score_boost": 5.0,
        "max_daily_loss_pct": 2.0,
        "max_open_trades": 2,
    },
    "balanced": {
        "risk_pct": 1.0,
        "min_score_boost": 0.0,
        "max_daily_loss_pct": 4.0,
        "max_open_trades": 4,
    },
    "aggressive": {
        "risk_pct": 1.5,
        "min_score_boost": -3.0,
        "max_daily_loss_pct": 6.0,
        "max_open_trades": 6,
    },
}

DEFAULT_ASSET_CLASSES = ("crypto", "fx", "commodity", "index", "stock")
DEFAULT_TIMEFRAMES: tuple[str, ...] = ()


@dataclass(slots=True)
class UserTradingPreferences:
    """Canonical user profile shared by generation, delivery and execution.

    The project historically stored signal filters and execution preferences in
    separate runtime-state records.  This model intentionally contains both so
    every downstream path reads one consistent policy.
    """

    trade_profile: str = "all"
    risk_profile: str = "balanced"
    asset_classes: tuple[str, ...] = DEFAULT_ASSET_CLASSES
    preferred_assets: tuple[str, ...] = ()
    blocked_assets: tuple[str, ...] = ()
    preferred_timeframes: tuple[str, ...] = DEFAULT_TIMEFRAMES
    preferred_strategies: tuple[str, ...] = ()
    sessions: tuple[str, ...] = ("auto",)
    notification_style: str = "normal"
    execution_mode: str = "manual"
    trading_mode: str = "paper"
    execution_provider: str = "auto"
    min_signal_score: float = 0.0
    max_signals_per_day: int | None = None
    risk_per_trade_pct: float = 1.0
    max_daily_trades: int = 10
    max_concurrent_positions: int = 3
    max_daily_loss_pct: float = 5.0
    notify_on_entry: bool = True
    notify_on_exit: bool = True
    notify_on_tp: bool = True
    notify_on_sl: bool = True
    auto_trade_brokers: tuple[str, ...] = ()
    learned_preferences: dict[str, Any] = field(default_factory=dict)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return float(default)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        except Exception:
            return {}
    return {}


def normalize_risk_profile(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "safe": "conservative",
        "normal": "balanced",
        "medium": "balanced",
        "high": "aggressive",
        "ultra": "ultra_conservative",
    }
    raw = aliases.get(raw, raw)
    return raw if raw in RISK_PROFILES else "balanced"


def _risk_profile_from_pct(value: Any) -> str:
    pct = _as_float(value, 1.0)
    if pct <= 0.3:
        return "ultra_conservative"
    if pct <= 0.65:
        return "conservative"
    if pct <= 1.25:
        return "balanced"
    return "aggressive"


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
        item_text = str(item or "").strip().lower()
        if not item_text:
            continue
        if item_text == "forex":
            item_text = "fx"
        if item_text == "indices":
            item_text = "index"
        if item_text not in seen:
            seen.add(item_text)
            out.append(item_text)
    return tuple(out) if out else default


def _normalize_timeframes(value: Any) -> tuple[str, ...]:
    aliases = {
        "60m": "1h",
        "1hr": "1h",
        "240m": "4h",
        "4hr": "4h",
        "24h": "1d",
        "daily": "1d",
        "weekly": "1w",
    }
    values = _tuple_from(value)
    out: list[str] = []
    for raw in values:
        normalized = aliases.get(str(raw).lower(), str(raw).lower())
        if normalized and normalized not in out:
            out.append(normalized)
    return tuple(out)


def _normalize_execution_mode(value: Any) -> str:
    raw = str(value or "manual").strip().lower().replace("-", "_")
    aliases = {
        "signals_only": "manual",
        "none": "manual",
        "semi": "semi_auto",
        "copy": "copy_trade",
        "copytrade": "copy_trade",
    }
    return aliases.get(raw, raw or "manual")


def merge_preference_payloads(
    modern: Mapping[str, Any] | None = None,
    legacy: Mapping[str, Any] | None = None,
    trade_profile_payload: Mapping[str, Any] | str | None = None,
) -> dict[str, Any]:
    """Merge old and new preference stores without allowing defaults to erase data."""

    legacy_data = dict(legacy or {})
    modern_data = dict(modern or {})
    merged: dict[str, Any] = {}

    # Translate legacy execution settings into canonical names first.
    merged.update(legacy_data)
    if "asset_classes" not in merged and legacy_data.get("preferred_asset_class"):
        merged["asset_classes"] = [legacy_data.get("preferred_asset_class")]
    if "preferred_timeframes" not in merged and legacy_data.get("preferred_timeframes"):
        merged["preferred_timeframes"] = legacy_data.get("preferred_timeframes")
    if "max_signals_per_day" not in merged and legacy_data.get("max_daily_trades") is not None:
        merged["max_signals_per_day"] = legacy_data.get("max_daily_trades")
    if "risk_profile" not in merged and legacy_data.get("risk_per_trade_pct") is not None:
        merged["risk_profile"] = _risk_profile_from_pct(legacy_data.get("risk_per_trade_pct"))
    provider = str(legacy_data.get("execution_provider") or "").strip().lower()
    if provider and provider != "auto" and not merged.get("auto_trade_brokers"):
        merged["auto_trade_brokers"] = [provider]

    # Explicit AI-profile values take precedence.
    merged.update(modern_data)

    profile_payload = _mapping(trade_profile_payload)
    if not merged.get("trade_profile") and not merged.get("profile"):
        if profile_payload.get("profile"):
            merged["trade_profile"] = profile_payload.get("profile")
        elif isinstance(trade_profile_payload, str) and trade_profile_payload.strip():
            merged["trade_profile"] = trade_profile_payload.strip()
    return merged


def preferences_from_payload(payload: dict[str, Any] | None) -> UserTradingPreferences:
    data = dict(payload or {})
    asset_classes_raw = data.get("asset_classes")
    if asset_classes_raw is None and data.get("preferred_asset_class"):
        asset_classes_raw = [data.get("preferred_asset_class")]
    preferred_assets = tuple(str(x).upper().strip() for x in _tuple_from(data.get("preferred_assets")))
    blocked_assets = tuple(str(x).upper().strip() for x in _tuple_from(data.get("blocked_assets")))
    risk_pct = _as_float(data.get("risk_per_trade_pct"), RISK_PROFILES[normalize_risk_profile(data.get("risk_profile"))]["risk_pct"])
    risk_profile = normalize_risk_profile(data.get("risk_profile") or _risk_profile_from_pct(risk_pct))
    max_daily_trades = max(0, _as_int(data.get("max_daily_trades"), 10))
    explicit_daily = data.get("max_signals_per_day")
    max_signals = None if explicit_daily in (None, "", 0, "0") else max(1, _as_int(explicit_daily, max_daily_trades or 1))
    return UserTradingPreferences(
        trade_profile=normalize_trade_profile(data.get("trade_profile") or data.get("profile"), default="all"),
        risk_profile=risk_profile,
        asset_classes=_tuple_from(asset_classes_raw, DEFAULT_ASSET_CLASSES),
        preferred_assets=preferred_assets,
        blocked_assets=blocked_assets,
        preferred_timeframes=_normalize_timeframes(data.get("preferred_timeframes") or data.get("notification_timeframes")),
        preferred_strategies=_tuple_from(data.get("preferred_strategies") or data.get("notification_strategies")),
        sessions=_tuple_from(data.get("sessions"), ("auto",)),
        notification_style=str(data.get("notification_style") or "normal").strip().lower(),
        execution_mode=_normalize_execution_mode(data.get("execution_mode")),
        trading_mode=str(data.get("trading_mode") or "paper").strip().lower(),
        execution_provider=str(data.get("execution_provider") or "auto").strip().lower(),
        min_signal_score=max(0.0, min(100.0, _as_float(data.get("min_signal_score"), 0.0))),
        max_signals_per_day=max_signals,
        risk_per_trade_pct=max(0.0, risk_pct),
        max_daily_trades=max_daily_trades,
        max_concurrent_positions=max(1, _as_int(data.get("max_concurrent_positions"), 3)),
        max_daily_loss_pct=max(0.0, _as_float(data.get("max_daily_loss_pct"), 5.0)),
        notify_on_entry=_as_bool(data.get("notify_on_entry"), True),
        notify_on_exit=_as_bool(data.get("notify_on_exit"), True),
        notify_on_tp=_as_bool(data.get("notify_on_tp"), True),
        notify_on_sl=_as_bool(data.get("notify_on_sl"), True),
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
    user_id = int(telegram_user_id)
    keys = {
        f"trading_preferences:{user_id}": "modern",
        f"user_prefs:{user_id}": "legacy",
        f"trade_profile:{user_id}": "profile",
    }
    result = await session.execute(
        text(
            """
            SELECT key, value
            FROM runtime_state
            WHERE key = :modern_key OR key = :legacy_key OR key = :profile_key
            """
        ),
        {
            "modern_key": f"trading_preferences:{user_id}",
            "legacy_key": f"user_prefs:{user_id}",
            "profile_key": f"trade_profile:{user_id}",
        },
    )
    values: dict[str, Any] = {}
    try:
        rows = result.all()
    except Exception:
        rows = []
    for row in rows:
        try:
            key = str(row[0])
            value = row[1]
        except Exception:
            mapping = getattr(row, "_mapping", row)
            key = str(mapping.get("key"))
            value = mapping.get("value")
        label = keys.get(key)
        if label:
            values[label] = value
    merged = merge_preference_payloads(
        _mapping(values.get("modern")),
        _mapping(values.get("legacy")),
        values.get("profile"),
    )
    return preferences_from_payload(merged)


async def set_user_trading_preferences(
    session,
    telegram_user_id: int,
    prefs: UserTradingPreferences,
) -> UserTradingPreferences:
    user_id = int(telegram_user_id)
    payload_dict = preferences_to_payload(prefs)
    payload = json.dumps(payload_dict)
    await session.execute(
        text(
            """
            INSERT INTO runtime_state(key, value, expires_at, updated_at)
            VALUES (:key, CAST(:value AS JSONB), NULL, NOW())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, expires_at = NULL, updated_at = NOW()
            """
        ),
        {"key": f"trading_preferences:{user_id}", "value": payload},
    )
    await session.execute(
        text(
            """
            INSERT INTO runtime_state(key, value, expires_at, updated_at)
            VALUES (:key, CAST(:value AS JSONB), NULL, NOW())
            ON CONFLICT (key) DO UPDATE
            SET value = COALESCE(runtime_state.value, '{}'::jsonb) || EXCLUDED.value,
                expires_at = NULL,
                updated_at = NOW()
            """
        ),
        {
            "key": f"user_prefs:{user_id}",
            "value": json.dumps(
                {
                    "trading_mode": prefs.trading_mode,
                    "execution_mode": prefs.execution_mode,
                    "execution_provider": prefs.execution_provider,
                    "risk_per_trade_pct": prefs.risk_per_trade_pct,
                    "min_signal_score": prefs.min_signal_score,
                    "preferred_asset_class": prefs.asset_classes[0] if len(prefs.asset_classes) == 1 else None,
                    "preferred_timeframes": list(prefs.preferred_timeframes),
                    "preferred_strategies": list(prefs.preferred_strategies),
                    "max_daily_trades": prefs.max_daily_trades,
                    "max_concurrent_positions": prefs.max_concurrent_positions,
                    "max_daily_loss_pct": prefs.max_daily_loss_pct,
                    "notify_on_entry": prefs.notify_on_entry,
                    "notify_on_exit": prefs.notify_on_exit,
                    "notify_on_tp": prefs.notify_on_tp,
                    "notify_on_sl": prefs.notify_on_sl,
                }
            ),
        },
    )
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
            "key": f"trade_profile:{user_id}",
            "value": json.dumps({"profile": prefs.trade_profile}),
        },
    )
    return prefs


def risk_profile_settings(name: str | None) -> dict[str, float]:
    return dict(RISK_PROFILES[normalize_risk_profile(name)])


def minimum_score_for_preferences(prefs: UserTradingPreferences) -> float:
    base = _env_float("USER_PROFILE_BASE_MIN_SIGNAL_SCORE", 75.0)
    boost = float(risk_profile_settings(prefs.risk_profile).get("min_score_boost") or 0.0)
    risk_floor = max(0.0, min(100.0, base + boost))
    return max(risk_floor, float(prefs.min_signal_score or 0.0))


def _canonical_asset_class(signal: Mapping[str, Any]) -> str:
    raw = str(signal.get("asset_class") or "").strip().lower()
    aliases = {"forex": "fx", "indices": "index", "equity": "stock", "equities": "stock"}
    if raw:
        return aliases.get(raw, raw)
    asset = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()
    try:
        from services.asset_registry import classify_asset

        return aliases.get(classify_asset(asset), classify_asset(asset))
    except Exception:
        return ""


def signal_matches_preferences(
    signal: dict[str, Any],
    prefs: UserTradingPreferences,
) -> tuple[bool, str]:
    asset = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()
    asset_class = _canonical_asset_class(signal)
    if prefs.asset_classes and asset_class and asset_class not in prefs.asset_classes:
        return False, f"asset_class:{asset_class}"
    if asset and asset in prefs.blocked_assets:
        return False, "blocked_asset"
    if prefs.preferred_assets and asset and asset not in prefs.preferred_assets:
        return False, "not_preferred_asset"

    timeframe = str(signal.get("timeframe") or "").strip().lower()
    if prefs.preferred_timeframes and timeframe and timeframe not in prefs.preferred_timeframes:
        return False, f"timeframe:{timeframe}"

    strategy_name = str(signal.get("strategy_name") or signal.get("strategy") or "").lower().strip()
    if prefs.preferred_strategies and strategy_name and not any(
        preferred in strategy_name or strategy_name in preferred
        for preferred in prefs.preferred_strategies
    ):
        return False, f"strategy:{strategy_name}"

    session_name = str(signal.get("market_session") or signal.get("session") or "").lower().strip()
    if prefs.sessions and "auto" not in prefs.sessions:
        if not session_name:
            return False, "session_missing"
        if not any(value in session_name for value in prefs.sessions):
            return False, f"session:{session_name}"

    if prefs.trade_profile and prefs.trade_profile != "all":
        from services.trade_profiles import signal_matches_user_profile

        if not signal_matches_user_profile(signal, prefs.trade_profile):
            return False, f"profile:{prefs.trade_profile}"

    score_keys = ("score_calibrated", "score_final", "score")
    score_present = any(signal.get(key) is not None for key in score_keys)
    if score_present:
        score = _as_float(
            signal.get("score_calibrated")
            or signal.get("score_final")
            or signal.get("score"),
            0.0,
        )
        minimum_score = minimum_score_for_preferences(prefs)
        if score < minimum_score:
            return False, f"profile_score:{minimum_score:.1f}"
    return True, "ok"


def personalize_signal_for_preferences(
    signal: Mapping[str, Any],
    prefs: UserTradingPreferences,
) -> dict[str, Any]:
    """Attach user policy and a ranking score without mutating canonical levels."""

    personalized = dict(signal or {})
    base_score = _as_float(
        personalized.get("score_calibrated")
        or personalized.get("score_final")
        or personalized.get("score"),
        0.0,
    )
    asset = str(personalized.get("asset") or personalized.get("symbol") or "").upper().strip()
    timeframe = str(personalized.get("timeframe") or "").lower().strip()
    rank_bonus = 0.0
    if asset and asset in prefs.preferred_assets:
        rank_bonus += 5.0
    if timeframe and timeframe in prefs.preferred_timeframes:
        rank_bonus += 2.0
    if prefs.trade_profile != "all":
        rank_bonus += 1.0
    learned = prefs.learned_preferences or {}
    try:
        rank_bonus += max(-5.0, min(5.0, float((learned.get("asset_score_adjustments") or {}).get(asset, 0.0))))
    except Exception:
        pass
    personalized["personalized_rank_score"] = round(max(0.0, min(100.0, base_score + rank_bonus)), 2)
    personalized["delivery_user_profile"] = prefs.trade_profile
    personalized["delivery_risk_profile"] = prefs.risk_profile
    personalized["delivery_execution_mode"] = prefs.execution_mode
    personalized["delivery_trading_mode"] = prefs.trading_mode
    personalized["delivery_execution_provider"] = prefs.execution_provider
    personalized["delivery_asset_classes"] = tuple(prefs.asset_classes)
    personalized["delivery_preferred_assets"] = tuple(prefs.preferred_assets)
    personalized["delivery_blocked_assets"] = tuple(prefs.blocked_assets)
    personalized["delivery_preferred_timeframes"] = tuple(prefs.preferred_timeframes)
    personalized["delivery_preferred_strategies"] = tuple(prefs.preferred_strategies)
    personalized["delivery_sessions"] = tuple(prefs.sessions)
    personalized["delivery_notification_style"] = prefs.notification_style
    personalized["delivery_risk_per_trade_pct"] = float(prefs.risk_per_trade_pct)
    personalized["delivery_max_daily_loss_pct"] = float(prefs.max_daily_loss_pct)
    personalized["delivery_max_concurrent_positions"] = int(prefs.max_concurrent_positions)
    personalized["delivery_profile_min_score"] = minimum_score_for_preferences(prefs)
    personalized["delivery_profile_verified"] = True
    return personalized


def format_preferences(prefs: UserTradingPreferences) -> str:
    return "\n".join(
        [
            "AI Trading Profile",
            "",
            f"Style: {prefs.trade_profile}",
            f"Risk: {prefs.risk_profile}",
            f"Assets: {', '.join(prefs.asset_classes)}",
            f"Timeframes: {', '.join(prefs.preferred_timeframes) if prefs.preferred_timeframes else 'auto'}",
            f"Strategies: {', '.join(prefs.preferred_strategies) if prefs.preferred_strategies else 'auto'}",
            f"Sessions: {', '.join(prefs.sessions)}",
            f"Minimum score: {minimum_score_for_preferences(prefs):.1f}",
            f"Notifications: {prefs.notification_style}",
            f"Trading mode: {prefs.trading_mode}",
            f"Execution: {prefs.execution_mode} via {prefs.execution_provider}",
            "",
            "Examples:",
            "/profile day",
            "/profile risk conservative",
            "/profile assets forex crypto index",
            "/profile sessions london new_york",
            "/profile execution manual",
        ]
    )


__all__ = [
    "DEFAULT_ASSET_CLASSES",
    "RISK_PROFILES",
    "UserTradingPreferences",
    "format_preferences",
    "get_user_trading_preferences",
    "merge_preference_payloads",
    "minimum_score_for_preferences",
    "normalize_risk_profile",
    "personalize_signal_for_preferences",
    "preferences_from_payload",
    "preferences_to_payload",
    "risk_profile_settings",
    "set_user_trading_preferences",
    "signal_matches_preferences",
]
