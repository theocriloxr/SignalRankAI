from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import text
from utils.timeutils import now_utc_naive


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
    # Account flipping: fast, high-reward setups for growing a small account.
    "flip": "flip",
    "flipper": "flip",
    "account_flip": "flip",
    "flipping": "flip",
    "small_account": "flip",
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
        min_rr=1.1,
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
        min_rr=1.2,
    ),
    "swing": TradeProfile(
        name="swing",
        label="Swing Trader",
        timeframes=("2h", "4h", "6h", "8h", "12h", "1d"),
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
    # Fewer, faster, asymmetric trades: a 1-2 day horizon and at least 3R to the
    # first target, so a small account can compound without a high win rate.
    # It never raises position size; risk per trade stays the user's setting.
    "flip": TradeProfile(
        name="flip",
        label="Account Flipper",
        timeframes=("15m", "1h", "4h"),
        target_atr_multipliers=(2.4, 4.0, 6.0),
        stop_atr_multiplier=0.8,
        expiry_minutes=2 * 24 * 60,
        expected_duration="2 hours-2 days",
        max_tp1_hours=48.0,
        min_rr=3.0,
    ),
}

FLIP_MIN_RR = 3.0


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
    if tf in {"2h", "4h", "6h", "8h", "12h", "1d", "24h"}:
        return "swing"
    if tf in {"1w", "1mo"}:
        return "position"
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


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "y"}


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
            "score_model": "heuristic_atr_time",
            "probabilities": {},
            "probability_model": "heuristic_atr_time",
            "probabilities_calibrated": False,
        }
    tp1_distance_atr = abs(float(tp_levels[0]) - entry) / max(atr, 1e-9)
    # Practical approximation until replay-calibrated empirical distributions exist.
    tf = str(signal.get("timeframe") or "").lower()
    tf_minutes = {
        "1m": 1,
        "3m": 3,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "2h": 120,
        "4h": 240,
        "6h": 360,
        "8h": 480,
        "12h": 720,
        "1d": 1440,
        "24h": 1440,
        "1w": 10080,
    }.get(tf, 60)
    tp1_hours = max(0.05, (tp1_distance_atr * tf_minutes * 4.0) / 60.0)
    score = max(0.0, min(100.0, (profile.max_tp1_hours / max(tp1_hours, 0.05)) * 100.0))
    horizons = (1, 4, 12, 24, 72, 168)
    probabilities = {f"tp1_{h}h": round(max(0.0, min(0.99, h / max(tp1_hours * 1.35, 0.1))), 3) for h in horizons}
    return {
        "profile": profile.name,
        "expected_duration": profile.expected_duration,
        "tp1_hours": round(tp1_hours, 2),
        "score": round(score, 1),
        "score_model": "heuristic_atr_time",
        "probabilities": probabilities,
        "probability_model": "heuristic_atr_time",
        "probabilities_calibrated": False,
    }


def apply_trade_profile_to_signal(signal: dict[str, Any], preferred_profile: str | None = None) -> dict[str, Any]:
    """Attach horizon/profile metadata without silently rewriting a valid thesis.

    Strategy-authored entry/stop/targets remain canonical by default. ATR profile
    geometry is synthesized only when the original geometry is missing/invalid,
    or when TRADE_PROFILE_RESHAPE_EXISTING_LEVELS=1 is explicitly enabled.
    """
    sig = dict(signal or {})
    profile_name = normalize_trade_profile(preferred_profile) if preferred_profile else infer_trade_profile(sig)
    if profile_name == "all":
        profile_name = infer_trade_profile(sig)
    profile = get_trade_profile(profile_name)
    entry = _as_float(sig.get("entry"), 0.0)
    direction = str(sig.get("direction") or "").strip().lower()
    is_long = direction in {"long", "buy"}
    is_short = direction in {"short", "sell"}
    stop = _as_float(sig.get("stop_loss") or sig.get("stop"), 0.0)
    original_levels = _parse_tp_levels(sig.get("take_profit") or sig.get("targets") or sig.get("tp_levels"))

    geometry_valid = bool(
        entry > 0
        and stop > 0
        and (is_long or is_short)
        and ((is_long and stop < entry) or (is_short and stop > entry))
        and original_levels
        and all((level > entry if is_long else level < entry) for level in original_levels)
    )
    reshape_existing = _env_bool("TRADE_PROFILE_RESHAPE_EXISTING_LEVELS", False)
    atr = _resolve_atr(sig, entry)
    if entry > 0 and atr > 0 and (reshape_existing or not geometry_valid) and (is_long or is_short):
        sign = 1.0 if is_long else -1.0
        sl = entry - (sign * atr * profile.stop_atr_multiplier)
        levels = [entry + (sign * atr * m) for m in profile.target_atr_multipliers]
        levels = [round(float(x), 8) for x in levels if x > 0]
        sig["stop_loss"] = round(float(sl), 8)
        sig["take_profit"] = levels
        sig["target_model"] = "atr_profile"
    else:
        # Keep the original executable thesis intact; profile metadata describes
        # user horizon and fit rather than manufacturing a different trade.
        if geometry_valid:
            sig["stop_loss"] = stop
            sig["take_profit"] = list(original_levels)
        sig["target_model"] = str(sig.get("target_model") or "strategy_preserved")

    # Canonical R:R is always recalculated from the geometry that will actually
    # be displayed/persisted.
    final_stop = _as_float(sig.get("stop_loss") or sig.get("stop"), 0.0)
    final_levels = _parse_tp_levels(sig.get("take_profit") or sig.get("targets") or sig.get("tp_levels"))
    risk = abs(entry - final_stop) if entry > 0 and final_stop > 0 else 0.0
    target_rrs = [
        abs(float(level) - entry) / risk
        for level in final_levels
        if risk > 0 and ((is_long and level > entry) or (is_short and level < entry))
    ]
    if target_rrs:
        sig["rr_ratio"] = round(float(target_rrs[0]), 4)
        sig["rr_estimate"] = sig["rr_ratio"]
        sig["rr_tp1"] = sig["rr_ratio"]
        sig["rr_final"] = round(float(target_rrs[-1]), 4)

    sig["trade_profile"] = profile.name
    sig["trade_profile_label"] = profile.label
    sig["expected_duration"] = profile.expected_duration
    sig["profile_min_rr"] = float(profile.min_rr)
    sig["profile_rr_ok"] = bool(target_rrs and float(target_rrs[0]) >= float(profile.min_rr))
    if not sig.get("expires_at"):
        sig["expires_at"] = now_utc_naive() + timedelta(minutes=int(profile.expiry_minutes))
    ettt = estimate_time_to_target(sig, profile.name)
    sig["time_to_target"] = ettt
    sig["time_to_target_score"] = float(ettt.get("score") or 0.0)

    # Horizon fit may be experimented with in scoring, but profile selection must
    # not silently alter the canonical signal score in production by default.
    if _env_bool("TRADE_PROFILE_SCORE_BLEND_ENABLED", False):
        base_score = _as_float(sig.get("score"), 0.0)
        sig["score"] = round(
            (base_score * 0.90) + (float(sig["time_to_target_score"]) * 0.10),
            2,
        )
        sig["profile_score_blended"] = True
    else:
        sig["profile_score_blended"] = False
    return sig


def _extend_target_ladder(sig: dict[str, Any], entry: float, stop: float, levels: list[float],
                          is_long: bool) -> None:
    """Give one- and two-target signals a real TP2/TP3 (owner request, 8 Nov 2026).

    The tracker, the paper desk and broker trade management all work the plan
    50% at TP1 (stop to entry), 25% at TP2, the rest at TP3. Strategies that
    author only TP1 left half the position with no target. Missing levels are
    added in steps of ``SIGNAL_TARGET_LADDER_STEP_R`` (default 1R) beyond the
    last authored target; they are stored on the signal, so the tracker,
    paper trades and cards all follow the same levels. Authored targets are
    never moved; ``take_profit_authored`` keeps them for audit.
    """
    if not _env_bool("SIGNAL_TARGET_LADDER_ENABLED", True) or not levels or len(levels) >= 3:
        return
    risk = abs(entry - stop)
    if risk <= 0:
        return
    try:
        step_r = float(os.getenv("SIGNAL_TARGET_LADDER_STEP_R", "1.0") or 1.0)
    except (TypeError, ValueError):
        step_r = 1.0
    step_r = max(0.25, min(5.0, step_r))
    ordered = sorted(levels, reverse=not is_long)
    sign = 1.0 if is_long else -1.0
    ladder = list(ordered)
    while len(ladder) < 3:
        nxt = ladder[-1] + sign * step_r * risk
        if nxt <= 0:
            return
        ladder.append(round(float(nxt), 8))
    sig["take_profit_authored"] = list(ordered)
    sig["take_profit"] = ladder
    sig["target_ladder"] = {"source": "r_steps", "step_r": step_r, "authored_targets": len(ordered)}
    sig["target_model"] = f"{sig.get('target_model') or 'strategy_preserved'}+ladder"


def apply_target_ladder(signal: dict[str, Any]) -> dict[str, Any]:
    """Add TP2/TP3 to a signal that has passed every gate (9 Nov 2026).

    Production, 9 Nov: the ladder was added during profile shaping, before the
    gates. The production quality guard caps the R:R of the farthest target
    (FX 4.5), so a ladder TP3 rejected FX setups it used to accept
    ("quality_rr 4.88 > 4.50 (fx)") and no signal passed all day. The ladder
    is now applied only after selection, so every gate sees exactly the
    strategy's own geometry. Returns the same dict.
    """
    entry = _as_float(signal.get("entry"), 0.0)
    stop = _as_float(signal.get("stop_loss") or signal.get("stop"), 0.0)
    direction = str(signal.get("direction") or "").strip().lower()
    is_long = direction in {"long", "buy"}
    levels = _parse_tp_levels(signal.get("take_profit") or signal.get("targets") or signal.get("tp_levels"))
    if entry <= 0 or stop <= 0 or not levels or direction not in {"long", "buy", "short", "sell"}:
        return signal
    if not all((level > entry if is_long else level < entry) for level in levels):
        return signal
    _extend_target_ladder(signal, entry, stop, levels, is_long)
    if signal.get("take_profit_authored"):
        risk = abs(entry - stop)
        signal["rr_ladder_final"] = round(abs(float(signal["take_profit"][-1]) - entry) / risk, 4)
    return signal


def _max_target_rr(signal: dict[str, Any]) -> float:
    for key in ("rr_final", "rr_ratio", "rr_estimate"):
        value = _as_float(signal.get(key), 0.0)
        if value > 0 and key == "rr_final":
            return value
    entry = _as_float(signal.get("entry"), 0.0)
    stop = _as_float(signal.get("stop_loss") or signal.get("stop"), 0.0)
    levels = _parse_tp_levels(signal.get("take_profit") or signal.get("targets") or signal.get("tp_levels"))
    risk = abs(entry - stop)
    if entry > 0 and risk > 0 and levels:
        return max(abs(level - entry) / risk for level in levels)
    return _as_float(signal.get("rr_ratio") or signal.get("rr_estimate"), 0.0)


def signal_matches_user_profile(signal: dict[str, Any], user_profile: str | None) -> bool:
    normalized = normalize_trade_profile(user_profile or "all", default="all")
    if normalized == "all":
        return True
    inferred = infer_trade_profile(signal)
    if normalized == "flip":
        # Flippers get explicit flip setups plus any 15m-4h setup paying at least 3R.
        if inferred == "flip":
            return True
        timeframe = str(signal.get("timeframe") or "").strip().lower()
        return timeframe in TRADE_PROFILES["flip"].timeframes and _max_target_rr(signal) >= FLIP_MIN_RR
    return inferred == normalized


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
    if normalized not in {"scalp", "day", "swing", "position", "flip", "all"}:
        raise ValueError("invalid_trade_profile")
    payload = json.dumps({"profile": normalized})
    await session.execute(
        text(
            """
            INSERT INTO runtime_state(key, value, expires_at, updated_at)
            VALUES (:key, :value, NULL, CURRENT_TIMESTAMP)
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, expires_at = NULL, updated_at = CURRENT_TIMESTAMP
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
        "flip": "Account Flipper: 15m-4h, 3R+ targets, hours to 2 days (fewer, higher-risk setups)",
        "all": "All: receive any matching high-quality profile",
    }
    lines = ["Trading Profile", "", f"Current: {current.upper()}", ""]
    lines.extend(f"- {name}: {desc}" for name, desc in labels.items())
    lines.append("")
    lines.append("Use /profile scalp, /profile day, /profile swing, /profile position, /profile flip, or /profile all.")
    return "\n".join(lines)
