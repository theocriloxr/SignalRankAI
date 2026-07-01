from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text


PROFILE_ALIASES = {
    "scalp": "scalp",
    "scalper": "scalp",
    "scalping": "scalp",
    "day": "day",
    "daytrade": "day",
    "day_trader": "day",
    "intraday": "day",
    "swing": "swing",
    "position": "position",
    "position_trader": "position",
    "longterm": "position",
    "long_term": "position",
    "all": "all",
}


@dataclass(frozen=True, slots=True)
class TradeProfile:
    name: str
    label: str
    timeframes: tuple[str, ...]
    target_atr_multipliers: tuple[float, float, float]
    stop_atr_multiplier: float
    expiry_minutes: int
    expected_duration: str
    max_tp1_hours: float
    min_rr: float


TRADE_PROFILES: dict[str, TradeProfile] = {
    "scalp": TradeProfile(
        name="scalp",
        label="Scalper",
        timeframes=("1m", "3m", "5m"),
        target_atr_multipliers=(0.4, 0.7, 1.0),
        stop_atr_multiplier=0.35,
        expiry_minutes=90,
        expected_duration="5-60 minutes",
        max_tp1_hours=1.0,
        min_rr=1.2,
    ),
    "day": TradeProfile(
        name="day",
        label="Day Trader",
        timeframes=("5m", "15m", "30m", "1h"),
        target_atr_multipliers=(0.8, 1.2, 1.8),
        stop_atr_multiplier=0.65,
        expiry_minutes=24 * 60,
        expected_duration="30 minutes-24 hours",
        max_tp1_hours=24.0,
        min_rr=1.35,
    ),
    "swing": TradeProfile(
        name="swing",
        label="Swing Trader",
        timeframes=("4h", "1d"),
        target_atr_multipliers=(2.0, 3.0, 5.0),
        stop_atr_multiplier=1.1,
        expiry_minutes=10 * 24 * 60,
        expected_duration="2-10 days",
        max_tp1_hours=10 * 24.0,
        min_rr=1.5,
    ),
    "position": TradeProfile(
        name="position",
        label="Position Trader",
        timeframes=("1d", "1w"),
        target_atr_multipliers=(3.0, 5.0, 8.0),
        stop_atr_multiplier=1.6,
        expiry_minutes=42 * 24 * 60,
        expected_duration="2-6 weeks",
        max_tp1_hours=42 * 24.0,
        min_rr=1.7,
    ),
}


def normalize_trade_profile(value: Any, default: str = "swing") -> str:
    raw = str(value or "").strip().lower().replace("-", "_")
    if not raw:
        return default
    return PROFILE_ALIASES.get(raw, default)


def infer_trade_profile(signal: dict[str, Any] | None = None, timeframe: str | None = None) -> str:
    sig = dict(signal or {})
    explicit = sig.get("trade_profile") or sig.get("trader_profile") or sig.get("intent_profile")
    if explicit:
        return normalize_trade_profile(explicit)
    tf = str(timeframe or sig.get("timeframe") or "").strip().lower()
    if tf in {"1m", "3m"}:
        return "scalp"
    if tf in {"5m", "15m", "30m", "1h"}:
        return "day"
    if tf in {"1w", "1mo"}:
        return "position"
    if tf == "1d":
        return "swing"
    return "swing"


def get_trade_profile(name: Any) -> TradeProfile:
    normalized = normalize_trade_profile(name)
    if normalized == "all":
        normalized = "swing"
    return TRADE_PROFILES.get(normalized, TRADE_PROFILES["swing"])


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _parse_tp_levels(raw: Any) -> list[float]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text_value = raw.strip()
        if not text_value:
            return []
        try:
            raw = json.loads(text_value)
        except Exception:
            raw = [p.strip() for p in text_value.strip("[]").replace("'", "").replace('"', "").split(",") if p.strip()]
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    levels: list[float] = []
    for item in raw:
        try:
            if isinstance(item, dict):
                item = item.get("price") or item.get("tp") or item.get("target") or item.get("value")
            value = float(item)
            if value > 0:
                levels.append(value)
        except Exception:
            continue
    return levels


def _resolve_atr(signal: dict[str, Any], entry: float) -> float:
    for key in ("atr", "atr_value", "avg_true_range"):
        value = _as_float(signal.get(key), 0.0)
        if value > 0:
            return value
    stop_loss = _as_float(signal.get("stop_loss") or signal.get("stop"), 0.0)
    if entry > 0 and stop_loss > 0:
        return abs(entry - stop_loss)
    return abs(entry) * 0.005 if entry else 0.0


def estimate_time_to_target(signal: dict[str, Any], profile_name: str | None = None) -> dict[str, Any]:
    profile = get_trade_profile(profile_name or infer_trade_profile(signal))
    entry = _as_float(signal.get("entry"), 0.0)
    atr = _resolve_atr(signal, entry)
    tp_levels = _parse_tp_levels(signal.get("take_profit") or signal.get("targets") or signal.get("tp_levels"))
    if not entry or not atr or not tp_levels:
        return {
            "profile": profile.name,
            "expected_duration": profile.expected_duration,
            "tp1_hours": None,
            "score": 50.0,
            "probabilities": {},
        }
    tp1_distance_atr = abs(float(tp_levels[0]) - entry) / max(atr, 1e-9)
    # Practical approximation until replay-calibrated empirical distributions exist.
    tf = str(signal.get("timeframe") or "").lower()
    tf_minutes = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080}.get(tf, 60)
    tp1_hours = max(0.05, (tp1_distance_atr * tf_minutes * 4.0) / 60.0)
    score = max(0.0, min(100.0, (profile.max_tp1_hours / max(tp1_hours, 0.05)) * 100.0))
    horizons = (1, 4, 12, 24, 72, 168)
    probabilities = {
        f"tp1_{h}h": round(max(0.0, min(0.99, h / max(tp1_hours * 1.35, 0.1))), 3)
        for h in horizons
    }
    return {
        "profile": profile.name,
        "expected_duration": profile.expected_duration,
        "tp1_hours": round(tp1_hours, 2),
        "score": round(score, 1),
        "probabilities": probabilities,
    }


def apply_trade_profile_to_signal(signal: dict[str, Any], preferred_profile: str | None = None) -> dict[str, Any]:
    sig = dict(signal or {})
    profile_name = normalize_trade_profile(preferred_profile) if preferred_profile else infer_trade_profile(sig)
    if profile_name == "all":
        profile_name = infer_trade_profile(sig)
    profile = get_trade_profile(profile_name)
    entry = _as_float(sig.get("entry"), 0.0)
    direction = str(sig.get("direction") or "long").lower()
    atr = _resolve_atr(sig, entry)
    if entry > 0 and atr > 0:
        sign = 1.0 if direction in {"long", "buy"} else -1.0
        sl = entry - (sign * atr * profile.stop_atr_multiplier)
        levels = [entry + (sign * atr * m) for m in profile.target_atr_multipliers]
        sig["stop_loss"] = round(float(sl), 8)
        sig["take_profit"] = [round(float(x), 8) for x in levels if x > 0]
        risk = abs(entry - float(sig["stop_loss"]))
        if risk > 0 and sig["take_profit"]:
            sig["rr_ratio"] = round(abs(float(sig["take_profit"][0]) - entry) / risk, 2)
            sig["rr_estimate"] = sig["rr_ratio"]
    sig["trade_profile"] = profile.name
    sig["trade_profile_label"] = profile.label
    sig["expected_duration"] = profile.expected_duration
    sig["target_model"] = "atr_profile"
    sig["expires_at"] = datetime.utcnow() + timedelta(minutes=int(profile.expiry_minutes))
    ettt = estimate_time_to_target(sig, profile.name)
    sig["time_to_target"] = ettt
    sig["time_to_target_score"] = float(ettt.get("score") or 0.0)
    try:
        base_score = _as_float(sig.get("score"), 0.0)
        sig["score"] = round((base_score * 0.90) + (float(sig["time_to_target_score"]) * 0.10), 2)
    except Exception:
        pass
    return sig


def signal_matches_user_profile(signal: dict[str, Any], user_profile: str | None) -> bool:
    normalized = normalize_trade_profile(user_profile or "all", default="all")
    if normalized == "all":
        return True
    return infer_trade_profile(signal) == normalized


async def get_user_trade_profile(session, telegram_user_id: int) -> str:
    key = f"trade_profile:{int(telegram_user_id)}"
    row = await session.execute(text("SELECT value FROM runtime_state WHERE key = :key"), {"key": key})
    raw = row.scalar_one_or_none()
    if isinstance(raw, dict):
        return normalize_trade_profile(raw.get("profile"), default="all")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return normalize_trade_profile(parsed.get("profile"), default="all")
        except Exception:
            return normalize_trade_profile(raw, default="all")
    return "all"


async def set_user_trade_profile(session, telegram_user_id: int, profile: str) -> str:
    normalized = normalize_trade_profile(profile, default="")
    if normalized not in {"scalp", "day", "swing", "position", "all"}:
        raise ValueError("invalid_trade_profile")
    payload = json.dumps({"profile": normalized})
    await session.execute(
        text(
            """
            INSERT INTO runtime_state(key, value, expires_at, updated_at)
            VALUES (:key, CAST(:value AS JSONB), NULL, NOW())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, expires_at = NULL, updated_at = NOW()
            """
        ),
        {"key": f"trade_profile:{int(telegram_user_id)}", "value": payload},
    )
    return normalized


def format_trade_profile_options(current: str = "all") -> str:
    current = normalize_trade_profile(current, default="all")
    labels = {
        "scalp": "Scalper: 1m/3m/5m, 5-60 minutes",
        "day": "Day Trader: 5m-1h, same-day targets",
        "swing": "Swing Trader: 4h/1d, multi-day targets",
        "position": "Position Trader: daily/weekly, multi-week targets",
        "all": "All: receive any matching high-quality profile",
    }
    lines = ["Trading Profile", "", f"Current: {current.upper()}", ""]
    lines.extend(f"- {name}: {desc}" for name, desc in labels.items())
    lines.append("")
    lines.append("Use /profile scalp, /profile day, /profile swing, /profile position, or /profile all.")
    return "\n".join(lines)

