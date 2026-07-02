from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


DEFAULT_TIMEFRAME_MAX_AGE_MINUTES: dict[str, float] = {
    "1m": 2.0,
    "3m": 6.0,
    "5m": 10.0,
    "15m": 20.0,
    "30m": 35.0,
    "1h": 60.0,
    "4h": 180.0,
    "1d": 720.0,
    "1w": 4320.0,
}

DEFAULT_PROFILE_MAX_AGE_MINUTES: dict[str, float] = {
    "scalp": 10.0,
    "day": 45.0,
    "swing": 360.0,
    "position": 4320.0,
}


@dataclass(frozen=True, slots=True)
class DeliveryFreshnessResult:
    ok: bool
    reason: str
    age_minutes: float | None = None
    max_age_minutes: float | None = None
    opportunity_remaining_pct: float | None = None
    live_price: float | None = None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


def _load_json_mapping(env_name: str, fallback: dict[str, float]) -> dict[str, float]:
    raw = (os.getenv(env_name) or "").strip()
    if not raw:
        return dict(fallback)
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            out = dict(fallback)
            for key, value in data.items():
                try:
                    out[str(key).strip().lower()] = max(0.0, float(value))
                except Exception:
                    continue
            return out
    except Exception:
        logger.warning("[delivery_freshness] invalid JSON in %s", env_name)
    return dict(fallback)


def _parse_created_at(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    try:
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 10_000_000_000:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        text = str(value).strip()
        if not text:
            return None
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
    except Exception:
        return None


def _infer_profile(signal: dict[str, Any], user_profile: str | None = None) -> str:
    try:
        from services.trade_profiles import infer_trade_profile, normalize_trade_profile

        profile = normalize_trade_profile(user_profile or "", default="")
        if profile and profile != "all":
            return profile
        return infer_trade_profile(signal)
    except Exception:
        return str(signal.get("trade_profile") or "swing").strip().lower() or "swing"


def max_delivery_age_minutes(signal: dict[str, Any], user_profile: str | None = None) -> float:
    """Return the hard max age for a signal at final delivery time."""
    tf = str(signal.get("timeframe") or "").strip().lower()
    tf_limits = _load_json_mapping("DELIVERY_MAX_SIGNAL_AGE_BY_TF_MINUTES", DEFAULT_TIMEFRAME_MAX_AGE_MINUTES)
    profile_limits = _load_json_mapping("DELIVERY_MAX_SIGNAL_AGE_BY_PROFILE_MINUTES", DEFAULT_PROFILE_MAX_AGE_MINUTES)
    tf_limit = tf_limits.get(tf, _env_float("DELIVERY_DEFAULT_MAX_SIGNAL_AGE_MINUTES", 60.0))
    profile = _infer_profile(signal, user_profile=user_profile)
    profile_limit = profile_limits.get(profile, tf_limit)
    return max(0.1, min(float(tf_limit), float(profile_limit)))


def evaluate_signal_age(
    signal: dict[str, Any],
    *,
    user_profile: str | None = None,
    now: datetime | None = None,
) -> DeliveryFreshnessResult:
    created = _parse_created_at(signal.get("created_at") or signal.get("generated_at"))
    if created is None:
        return DeliveryFreshnessResult(False, "missing_created_at")
    now_naive = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(tzinfo=None)
    age_minutes = max(0.0, (now_naive - created).total_seconds() / 60.0)
    max_age = max_delivery_age_minutes(signal, user_profile=user_profile)
    remaining = max(0.0, min(100.0, 100.0 * (1.0 - (age_minutes / max(max_age, 0.1)))))
    min_remaining = _env_float("DELIVERY_OPPORTUNITY_MIN_REMAINING_PCT", 30.0)
    if age_minutes > max_age:
        return DeliveryFreshnessResult(
            False,
            f"age_exceeded:{age_minutes:.1f}m>{max_age:.1f}m",
            age_minutes,
            max_age,
            remaining,
        )
    if remaining < min_remaining:
        return DeliveryFreshnessResult(
            False,
            f"opportunity_decayed:{remaining:.1f}%<{min_remaining:.1f}%",
            age_minutes,
            max_age,
            remaining,
        )
    return DeliveryFreshnessResult(True, "age_ok", age_minutes, max_age, remaining)


async def validate_delivery_freshness(
    signal: dict[str, Any],
    *,
    user_profile: str | None = None,
    cached_live_price: float | None = None,
    require_live_price: bool | None = None,
) -> DeliveryFreshnessResult:
    """Final non-negotiable gate before a signal is reserved or sent."""
    if not _env_bool("DELIVERY_FRESHNESS_GATE_ENABLED", True):
        return DeliveryFreshnessResult(True, "disabled")

    sig = dict(signal or {})
    age_result = evaluate_signal_age(sig, user_profile=user_profile)
    if not age_result.ok:
        return age_result

    require_price = _env_bool("DELIVERY_REQUIRE_LIVE_PRICE", True) if require_live_price is None else bool(require_live_price)
    live_price = cached_live_price
    if live_price is None:
        raw_price = sig.get("current_price") or sig.get("live_price")
        try:
            live_price = float(raw_price) if raw_price is not None else None
        except Exception:
            live_price = None

    try:
        from engine.stale_signal_validator import validate_signal_freshness

        ok, reason, fetched_live = await validate_signal_freshness(sig, cached_live_price=live_price)
        if fetched_live is not None:
            live_price = float(fetched_live)
        if not ok:
            return DeliveryFreshnessResult(
                False,
                f"price_drift:{reason}",
                age_result.age_minutes,
                age_result.max_age_minutes,
                age_result.opportunity_remaining_pct,
                live_price,
            )
        reason_l = str(reason or "").lower()
        if require_price and live_price is None and any(
            marker in reason_l
            for marker in ("unavailable", "timeout", "error", "skip")
        ):
            return DeliveryFreshnessResult(
                False,
                f"live_price_unavailable:{reason}",
                age_result.age_minutes,
                age_result.max_age_minutes,
                age_result.opportunity_remaining_pct,
                None,
            )
    except Exception as exc:
        if require_price:
            return DeliveryFreshnessResult(
                False,
                f"price_revalidation_error:{type(exc).__name__}",
                age_result.age_minutes,
                age_result.max_age_minutes,
                age_result.opportunity_remaining_pct,
                live_price,
            )
        logger.debug("[delivery_freshness] price revalidation skipped after error: %s", exc)

    if live_price is not None:
        try:
            from engine.price_validator import check_sl_tp_hit

            should_skip, reason = check_sl_tp_hit(sig, float(live_price))
            if should_skip:
                return DeliveryFreshnessResult(
                    False,
                    f"already_resolved:{reason}",
                    age_result.age_minutes,
                    age_result.max_age_minutes,
                    age_result.opportunity_remaining_pct,
                    float(live_price),
                )
        except Exception as exc:
            logger.debug("[delivery_freshness] SL/TP revalidation failed: %s", exc)

    return DeliveryFreshnessResult(
        True,
        "fresh_for_delivery",
        age_result.age_minutes,
        age_result.max_age_minutes,
        age_result.opportunity_remaining_pct,
        live_price,
    )
