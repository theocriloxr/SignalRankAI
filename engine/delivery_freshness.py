from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from data.provider_types import (
    FinalQuotePolicy,
    LivePriceFailure,
    LivePriceQuote,
    validate_quote_for_final_delivery,
)

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

FINAL_VALIDATION_POLICY_VERSION = "phase4-pass1-v1"


@dataclass(frozen=True, slots=True)
class DeliveryFreshnessResult:
    ok: bool
    reason: str
    age_minutes: float | None = None
    max_age_minutes: float | None = None
    opportunity_remaining_pct: float | None = None
    live_price: float | None = None
    state: str | None = None
    entry_drift_pct: float | None = None
    current_rr: float | None = None
    queue_age_seconds: float | None = None
    max_queue_age_seconds: float | None = None
    policy_version: str | None = None
    quote_provider: str | None = None
    quote_request_id: str | None = None
    quote_kind: str | None = None
    quote_source_timestamp: float | None = None
    quote_source_age_seconds: float | None = None
    rule_results: tuple[str, ...] = ()


def _direction(signal: dict[str, Any]) -> str:
    raw = str(signal.get("direction") or signal.get("side") or "").strip().lower()
    if raw in {"sell", "short", "bearish"}:
        return "short"
    return "long"


def _public_testing() -> bool:
    """Check if PUBLIC_TESTING_MODE is enabled."""
    raw = os.getenv("PUBLIC_TESTING_MODE")
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "y"}


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


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        return out if out > 0 else None
    except Exception:
        return None


def _asset_class(symbol: str) -> str:
    try:
        from services.asset_mapper import classify_asset
        cls = str(classify_asset(symbol)).lower()
        if cls == "forex":
            return "fx"
        return cls
    except Exception:
        sym = str(symbol or "").upper().strip()
        if sym.endswith(("USDT", "USDC", "BUSD", "BTC", "ETH")):
            return "crypto"
        if len(sym) == 6 and sym.isalpha():
            return "fx"
        if sym in {"XAUUSD", "XAGUSD", "GOLD", "SILVER", "USOIL", "OIL"}:
            return "commodity"
        return "stock"


def _max_entry_drift_pct(symbol: str) -> float:
    cls = _asset_class(symbol)
    defaults = {
        "crypto": 0.20,
        "fx": 0.08,
        "stock": 0.35,
        "commodity": 0.20,
        "index": 0.25,
    }
    env_by_cls = {
        "crypto": "FINAL_SEND_MAX_DRIFT_CRYPTO_PCT",
        "fx": "FINAL_SEND_MAX_DRIFT_FOREX_PCT",
        "stock": "FINAL_SEND_MAX_DRIFT_STOCK_PCT",
        "commodity": "FINAL_SEND_MAX_DRIFT_COMMODITY_PCT",
        "index": "FINAL_SEND_MAX_DRIFT_INDEX_PCT",
    }
    env_name = env_by_cls.get(cls, "FINAL_SEND_MAX_DRIFT_DEFAULT_PCT")
    return _env_float(env_name, defaults.get(cls, _env_float("FINAL_SEND_MAX_DRIFT_DEFAULT_PCT", 0.20)))


def _time_to_telegraph_budget_seconds(signal: dict[str, Any], symbol: str) -> float:
    """Return max queue/generation-to-Telegram age in seconds.

    This is intentionally stricter than the broader signal expiry window. A
    signal may still be analytically valid for 30 minutes, but if it waits too
    long in the delivery queue it should be revalidated or dropped rather than
    sent as a fresh alert.
    """
    if not _env_bool("DELIVERY_TIME_TO_TELEGRAPH_ENABLED", True):
        return float("inf")
    tf = str(signal.get("timeframe") or "").strip().lower()
    profile = _infer_profile(signal, user_profile=str(signal.get("delivery_user_profile") or ""))
    cls = _asset_class(symbol)
    budgets = {
        "crypto": _env_float("DELIVERY_QUEUE_MAX_AGE_CRYPTO_SECONDS", 75.0),
        "fx": _env_float("DELIVERY_QUEUE_MAX_AGE_FOREX_SECONDS", 120.0),
        "stock": _env_float("DELIVERY_QUEUE_MAX_AGE_STOCK_SECONDS", 180.0),
        "commodity": _env_float("DELIVERY_QUEUE_MAX_AGE_COMMODITY_SECONDS", 30.0),
        "index": _env_float("DELIVERY_QUEUE_MAX_AGE_INDEX_SECONDS", 90.0),
    }
    budget = budgets.get(cls, _env_float("DELIVERY_QUEUE_MAX_AGE_SECONDS", 120.0))
    if symbol.upper().startswith(("XAU", "XAG")) or symbol.upper() in {"GOLD", "SILVER"}:
        budget = min(budget, _env_float("DELIVERY_QUEUE_MAX_AGE_GOLD_SECONDS", 15.0))
    if profile == "scalp":
        budget = min(budget, _env_float("DELIVERY_QUEUE_MAX_AGE_SCALP_SECONDS", 20.0))
    tf_env = {
        "1m": "DELIVERY_QUEUE_MAX_AGE_1M_SECONDS",
        "3m": "DELIVERY_QUEUE_MAX_AGE_3M_SECONDS",
        "5m": "DELIVERY_QUEUE_MAX_AGE_5M_SECONDS",
        "15m": "DELIVERY_QUEUE_MAX_AGE_15M_SECONDS",
    }
    if tf in tf_env:
        default_by_tf = {"1m": 20.0, "3m": 45.0, "5m": 90.0, "15m": 180.0}.get(tf, budget)
        budget = min(budget, _env_float(tf_env[tf], default_by_tf))
    return max(1.0, float(budget))


def evaluate_time_to_telegraph(
    signal: dict[str, Any],
    *,
    symbol: str | None = None,
    now: datetime | None = None,
) -> DeliveryFreshnessResult:
    """Block signals that sat too long between generation and Telegram send."""
    if not _env_bool("DELIVERY_TIME_TO_TELEGRAPH_ENABLED", True):
        return DeliveryFreshnessResult(True, "time_to_telegraph_disabled", state="LIVE_QUEUE_CHECK_SKIPPED")
    created = _parse_created_at(signal.get("generated_at") or signal.get("created_at"))
    if created is None:
        if _env_bool("DELIVERY_TIME_TO_TELEGRAPH_REQUIRE_TIMESTAMP", True):
            return DeliveryFreshnessResult(False, "missing_generated_at_for_queue_gate", state="BLOCKED_MISSING_QUEUE_TIMESTAMP")
        return DeliveryFreshnessResult(True, "missing_generated_at_allowed", state="LIVE_QUEUE_CHECK_SKIPPED")
    now_naive = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(tzinfo=None)
    queue_age = max(0.0, (now_naive - created).total_seconds())
    sym = str(symbol or signal.get("asset") or signal.get("symbol") or "").upper().strip()
    max_queue_age = _time_to_telegraph_budget_seconds(signal, sym)
    if queue_age > max_queue_age:
        return DeliveryFreshnessResult(
            False,
            f"expired_in_queue:{queue_age:.1f}s>{max_queue_age:.1f}s",
            queue_age_seconds=queue_age,
            max_queue_age_seconds=max_queue_age,
            state="EXPIRED_IN_QUEUE",
        )
    return DeliveryFreshnessResult(
        True,
        "queue_age_ok",
        queue_age_seconds=queue_age,
        max_queue_age_seconds=max_queue_age,
        state="LIVE_QUEUE_CHECK_PASSED",
    )


async def _fetch_final_live_quote(symbol: str) -> LivePriceQuote | None:
    """Fetch a new provider observation; final-send caches are prohibited."""
    try:
        from data.get_live_price import get_live_price_result

        result = await get_live_price_result(
            symbol,
            timeout=max(1.0, _env_float("FINAL_SEND_LIVE_PRICE_TIMEOUT_SECONDS", 4.0)),
        )
        if isinstance(result, LivePriceFailure):
            logger.info(
                "[delivery_freshness] quote_unavailable symbol=%s provider=%s reason=%s request_id=%s",
                symbol,
                result.provider,
                result.reason,
                result.request_id,
            )
            return None
        logger.info(
            "[delivery_freshness] live_quote symbol=%s price=%s provider=%s kind=%s latency_ms=%s request_id=%s",
            symbol,
            result.price,
            result.provider,
            result.quote_kind,
            result.latency_ms,
            result.request_id,
        )
        return result
    except Exception as exc:
        logger.debug("[delivery_freshness] final live quote fetch failed symbol=%s err=%s", symbol, exc)
        return None


async def _fetch_final_live_price(symbol: str) -> float | None:
    """Legacy private wrapper retained for callers that still expect a float."""
    quote = await _fetch_final_live_quote(symbol)
    return float(quote.mid) if quote is not None else None


def _all_targets_consumed(signal: dict[str, Any], live_price: float) -> bool:
    targets = _target_prices(signal)
    if not targets:
        return False
    direction = _direction(signal)
    if direction == "short":
        return all(float(live_price) <= t for t in targets)
    return all(float(live_price) >= t for t in targets)


def _first_target_hit(signal: dict[str, Any], live_price: float) -> bool:
    targets = _target_prices(signal)
    if not targets:
        return False
    direction = _direction(signal)
    tp1 = targets[0]
    if direction == "short":
        return float(live_price) <= tp1
    return float(live_price) >= tp1


def _target_prices(signal: dict[str, Any]) -> list[float]:
    raw = (
        signal.get("take_profit")
        or signal.get("take_profits")
        or signal.get("targets")
        or signal.get("tp")
    )
    if raw is None:
        return []
    if isinstance(raw, (int, float)):
        parsed: Any = [raw]
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]
    else:
        parsed = raw
    if isinstance(parsed, dict):
        parsed = list(parsed.values())
    if not isinstance(parsed, (list, tuple, set)):
        parsed = [parsed]
    out: list[float] = []
    for item in parsed:
        if isinstance(item, dict):
            item = item.get("price") or item.get("target") or item.get("value")
        value = _to_float(item)
        if value is not None:
            out.append(value)
    return out


def _validate_risk_geometry(signal: dict[str, Any]) -> tuple[bool, str]:
    """Validate direction, stop placement, and monotonic TP ordering."""
    entry = _to_float(signal.get("entry"))
    stop = _to_float(signal.get("stop_loss") or signal.get("sl"))
    targets = _target_prices(signal)
    if entry is None:
        return False, "missing_or_invalid_entry"
    if stop is None:
        return False, "missing_or_invalid_stop"
    if not targets:
        return False, "missing_or_invalid_targets"
    direction = _direction(signal)
    if direction == "short":
        if stop <= entry:
            return False, "short_stop_must_be_above_entry"
        if any(target >= entry for target in targets):
            return False, "short_target_must_be_below_entry"
        if any(left <= right for left, right in zip(targets, targets[1:])):
            return False, "short_targets_must_descend"
    else:
        if stop >= entry:
            return False, "long_stop_must_be_below_entry"
        if any(target <= entry for target in targets):
            return False, "long_target_must_be_above_entry"
        if any(left >= right for left, right in zip(targets, targets[1:])):
            return False, "long_targets_must_ascend"
    return True, "risk_geometry_ok"


def _current_reward_risk(signal: dict[str, Any], live_price: float) -> tuple[bool, str, float | None]:
    entry = _to_float(signal.get("entry"))
    stop = _to_float(signal.get("stop_loss") or signal.get("sl"))
    if entry is None or stop is None:
        return True, "rr_skip_missing_entry_or_stop", None
    stop_distance = abs(entry - stop)
    if stop_distance <= 0:
        return False, "invalid_stop_distance", None

    max_drift = _env_float("DELIVERY_MAX_ENTRY_DRIFT_STOP_FRACTION", 0.75)
    drift_fraction = abs(float(live_price) - entry) / stop_distance
    if drift_fraction > max_drift:
        return False, f"entry_drift_exceeded:{drift_fraction:.2f}>{max_drift:.2f}", None

    targets = _target_prices(signal)
    if not targets:
        return True, "rr_skip_missing_target", None
    direction = _direction(signal)
    if direction == "short":
        viable = [t for t in targets if t < float(live_price)]
        target = max(viable) if viable else min(targets)
        risk = stop - float(live_price)
        reward = float(live_price) - target
    else:
        viable = [t for t in targets if t > float(live_price)]
        target = min(viable) if viable else max(targets)
        risk = float(live_price) - stop
        reward = target - float(live_price)
    if risk <= 0:
        return False, "current_price_beyond_stop", None
    if reward <= 0:
        return False, "target_already_consumed", 0.0
    current_rr = reward / risk
    min_rr = _env_float("DELIVERY_MIN_CURRENT_RR", 1.0)
    if current_rr < min_rr:
        return False, f"current_rr_too_low:{current_rr:.2f}<{min_rr:.2f}", current_rr
    return True, f"current_rr_ok:{current_rr:.2f}", current_rr


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
    live_quote: LivePriceQuote | None = None,
    final_send: bool = False,
    delivery_tier: str | None = None,
    quote_policy: FinalQuotePolicy | None = None,
) -> DeliveryFreshnessResult:
    """Validate analytical freshness or enforce the final-send trust boundary.

    ``final_send=True`` is deliberately stricter: it ignores cached/naked
    prices, obtains a typed provider observation, checks source age and market
    state, and fails closed independently of compatibility feature flags.

    PUBLIC_TESTING_MODE: When enabled, all fail-open delivery paths are
    overridden to fail-closed. A quote timeout, provider error, missing quote,
    or stale quote always blocks delivery. The env vars
    DELIVERY_FRESHNESS_TIMEOUT_FAIL_OPEN, DELIVERY_FRESHNESS_ERROR_FAIL_OPEN,
    and DELIVERY_MISSING_PRICE_FAIL_OPEN are ignored.
    """
    _pt = _public_testing()
    if not _env_bool("DELIVERY_FRESHNESS_GATE_ENABLED", True) and not final_send:
        return DeliveryFreshnessResult(True, "disabled")

    sig = dict(signal or {})
    age_result = evaluate_signal_age(sig, user_profile=user_profile)
    if not age_result.ok:
        if not final_send:
            return age_result
        return DeliveryFreshnessResult(
            False,
            age_result.reason,
            age_result.age_minutes,
            age_result.max_age_minutes,
            age_result.opportunity_remaining_pct,
            state="BLOCKED_STALE",
            policy_version=FINAL_VALIDATION_POLICY_VERSION,
            rule_results=("signal_age_failed",),
        )

    require_price = _env_bool("DELIVERY_REQUIRE_LIVE_PRICE", True) if require_live_price is None else bool(require_live_price)
    symbol = str(sig.get("asset") or sig.get("symbol") or "").upper().strip()

    queue_result = evaluate_time_to_telegraph(sig, symbol=symbol)
    if not queue_result.ok:
        return DeliveryFreshnessResult(
            False,
            queue_result.reason,
            age_result.age_minutes,
            age_result.max_age_minutes,
            age_result.opportunity_remaining_pct,
            None,
            state=queue_result.state,
            queue_age_seconds=queue_result.queue_age_seconds,
            max_queue_age_seconds=queue_result.max_queue_age_seconds,
            policy_version=FINAL_VALIDATION_POLICY_VERSION,
            rule_results=("signal_age_passed", "queue_age_failed"),
        )

    policy = quote_policy or FinalQuotePolicy()
    rule_results = ["signal_age_passed", "queue_age_passed"]
    quote = live_quote
    live_price = None
    quote_meta: dict[str, Any] = {
        "policy_version": policy.version if final_send else FINAL_VALIDATION_POLICY_VERSION,
    }

    if final_send:
        if quote is None and symbol:
            quote = await _fetch_final_live_quote(symbol)
        try:
            from data.market_hours import get_market_session_status

            market = get_market_session_status(symbol)
            market_open: bool | None = market.is_open
            market_reason = market.reason
        except Exception as exc:
            market_open = None
            market_reason = f"market_calendar_error:{type(exc).__name__}"
        trust = validate_quote_for_final_delivery(
            quote,
            market_open=market_open,
            market_reason=market_reason,
            policy=policy,
        )
        if quote is not None:
            quote_meta.update(
                quote_provider=quote.provider,
                quote_request_id=quote.request_id,
                quote_kind=quote.quote_kind,
                quote_source_timestamp=quote.source_timestamp,
                quote_source_age_seconds=trust.source_age_seconds,
            )
        if not trust.ok:
            return DeliveryFreshnessResult(
                False,
                trust.reason,
                age_result.age_minutes,
                age_result.max_age_minutes,
                age_result.opportunity_remaining_pct,
                None,
                state=trust.state,
                queue_age_seconds=queue_result.queue_age_seconds,
                max_queue_age_seconds=queue_result.max_queue_age_seconds,
                rule_results=tuple(rule_results) + ("quote_trust_failed",),
                **quote_meta,
            )
        live_price = float(quote.mid) if quote is not None else None
        rule_results.extend(trust.checks)
        rule_results.append("quote_trust_passed")
    else:
        force_fresh = _env_bool("FINAL_SEND_FORCE_FRESH_PRICE", False)
        if force_fresh and _env_bool("FINAL_SEND_LIVE_PRICE_CHECK_ENABLED", True) and symbol:
            quote = quote or await _fetch_final_live_quote(symbol)
            live_price = float(quote.mid) if quote is not None else None
        else:
            live_price = cached_live_price
            if live_price is None:
                raw_price = sig.get("current_price") or sig.get("live_price")
                try:
                    live_price = float(raw_price) if raw_price is not None else None
                except Exception:
                    live_price = None

    if require_price and live_price is None:
        # In public-testing mode, always block with a distinct state name
        # so logs clearly identify the enforcement.
        _blocked_state = "BLOCKED_PROVIDER_UNTRUSTED"
        if _pt:
            _blocked_state = "BLOCKED_PROVIDER_UNTRUSTED_PUBLIC_TEST"
        elif final_send:
            _blocked_state = "BLOCKED_PROVIDER_UNTRUSTED"
        logger.warning(
            "[delivery_blocked] signal=%(signal_id)s asset=%(asset)s reason=%(reason)s fail_open=false",
            {
                "signal_id": str(sig.get("signal_id") or "unknown")[:12],
                "asset": symbol,
                "reason": "live_price_unavailable",
            },
        )
        return DeliveryFreshnessResult(
            False,
            "live_price_unavailable:final_live_price_unavailable",
            age_result.age_minutes,
            age_result.max_age_minutes,
            age_result.opportunity_remaining_pct,
            None,
            state=_blocked_state,
            queue_age_seconds=queue_result.queue_age_seconds,
            max_queue_age_seconds=queue_result.max_queue_age_seconds,
            rule_results=tuple(rule_results) + ("live_price_missing",),
            **quote_meta,
        )

    if final_send:
        geometry_ok, geometry_reason = _validate_risk_geometry(sig)
        if not geometry_ok:
            return DeliveryFreshnessResult(
                False,
                geometry_reason,
                age_result.age_minutes,
                age_result.max_age_minutes,
                age_result.opportunity_remaining_pct,
                live_price,
                state="BLOCKED_RISK_INVALID",
                queue_age_seconds=queue_result.queue_age_seconds,
                max_queue_age_seconds=queue_result.max_queue_age_seconds,
                rule_results=tuple(rule_results) + ("risk_geometry_failed",),
                **quote_meta,
            )
        rule_results.append("risk_geometry_passed")

    try:
        from engine.stale_signal_validator import validate_signal_freshness

        validation_signal = dict(sig)
        if final_send:
            validation_signal["_trusted_live_quote"] = True
        ok, reason, fetched_live = await validate_signal_freshness(validation_signal, cached_live_price=live_price)
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
                state="MISSED_ENTRY" if final_send else None,
                queue_age_seconds=queue_result.queue_age_seconds,
                max_queue_age_seconds=queue_result.max_queue_age_seconds,
                rule_results=tuple(rule_results) + ("stale_validator_failed",),
                **quote_meta,
            )
        reason_l = str(reason or "").lower()
        if require_price and live_price is None and any(marker in reason_l for marker in ("unavailable", "timeout", "error", "skip")):
            return DeliveryFreshnessResult(
                False,
                f"live_price_unavailable:{reason}",
                age_result.age_minutes,
                age_result.max_age_minutes,
                age_result.opportunity_remaining_pct,
                None,
                state="BLOCKED_PROVIDER_UNTRUSTED" if final_send else None,
                rule_results=tuple(rule_results) + ("stale_validator_no_price",),
                **quote_meta,
            )
        rule_results.append("stale_validator_passed")
    except Exception as exc:
        if require_price:
            return DeliveryFreshnessResult(
                False,
                f"price_revalidation_error:{type(exc).__name__}",
                age_result.age_minutes,
                age_result.max_age_minutes,
                age_result.opportunity_remaining_pct,
                live_price,
                state="BLOCKED_PROVIDER_UNTRUSTED" if final_send else None,
                rule_results=tuple(rule_results) + ("stale_validator_error",),
                **quote_meta,
            )
        logger.debug("[delivery_freshness] price revalidation skipped after error: %s", exc)

    if live_price is not None:
        if _env_bool("REJECT_IF_TP1_ALREADY_HIT", True) and _first_target_hit(sig, float(live_price)):
            return DeliveryFreshnessResult(
                False,
                "tp1_already_hit_before_send",
                age_result.age_minutes,
                age_result.max_age_minutes,
                age_result.opportunity_remaining_pct,
                float(live_price),
                state="MISSED_ENTRY" if final_send else "TP1_ALREADY_HIT",
                queue_age_seconds=queue_result.queue_age_seconds,
                max_queue_age_seconds=queue_result.max_queue_age_seconds,
                rule_results=tuple(rule_results) + ("tp1_already_hit",),
                **quote_meta,
            )
        if _env_bool("REJECT_IF_ALL_TARGETS_ALREADY_HIT", True) and _all_targets_consumed(sig, float(live_price)):
            return DeliveryFreshnessResult(
                False,
                "all_targets_already_consumed_before_send",
                age_result.age_minutes,
                age_result.max_age_minutes,
                age_result.opportunity_remaining_pct,
                float(live_price),
                state="MISSED_ENTRY" if final_send else None,
                rule_results=tuple(rule_results) + ("all_targets_consumed",),
                **quote_meta,
            )
        rr_ok, rr_reason, current_rr = _current_reward_risk(sig, float(live_price))
        if not rr_ok:
            return DeliveryFreshnessResult(
                False,
                rr_reason,
                age_result.age_minutes,
                age_result.max_age_minutes,
                age_result.opportunity_remaining_pct,
                float(live_price),
                state="MISSED_ENTRY" if "drift" in rr_reason and final_send else ("BLOCKED_RISK_INVALID" if final_send else None),
                current_rr=current_rr,
                rule_results=tuple(rule_results) + ("reward_risk_failed",),
                **quote_meta,
            )
        rule_results.append("reward_risk_passed")

        entry = _to_float(sig.get("entry"))
        drift_pct = None
        if entry is not None:
            drift_pct = abs(float(live_price) - entry) / entry * 100.0
            max_drift_pct = _max_entry_drift_pct(symbol)
            if drift_pct > max_drift_pct + 1e-9:
                return DeliveryFreshnessResult(
                    False,
                    f"final_entry_drift:{drift_pct:.2f}%>{max_drift_pct:.2f}%",
                    age_result.age_minutes,
                    age_result.max_age_minutes,
                    age_result.opportunity_remaining_pct,
                    float(live_price),
                    state="MISSED_ENTRY" if final_send else "MISSED_ENTRY_DRIFT",
                    entry_drift_pct=drift_pct,
                    queue_age_seconds=queue_result.queue_age_seconds,
                    max_queue_age_seconds=queue_result.max_queue_age_seconds,
                    rule_results=tuple(rule_results) + ("class_drift_failed",),
                    **quote_meta,
                )
        rule_results.append("class_drift_passed")
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
                    state="MISSED_ENTRY" if final_send else None,
                    rule_results=tuple(rule_results) + ("sl_tp_already_resolved",),
                    **quote_meta,
                )
            rule_results.append("sl_tp_not_resolved")
        except Exception as exc:
            if final_send:
                return DeliveryFreshnessResult(
                    False,
                    f"sl_tp_validation_error:{type(exc).__name__}",
                    age_result.age_minutes,
                    age_result.max_age_minutes,
                    age_result.opportunity_remaining_pct,
                    float(live_price),
                    state="BLOCKED_RISK_INVALID",
                    rule_results=tuple(rule_results) + ("sl_tp_validation_error",),
                    **quote_meta,
                )
            logger.debug("[delivery_freshness] SL/TP revalidation failed: %s", exc)

    return DeliveryFreshnessResult(
        True,
        "fresh_for_delivery",
        age_result.age_minutes,
        age_result.max_age_minutes,
        age_result.opportunity_remaining_pct,
        live_price,
        state="LIVE_CHECK_PASSED",
        queue_age_seconds=queue_result.queue_age_seconds,
        max_queue_age_seconds=queue_result.max_queue_age_seconds,
        rule_results=tuple(rule_results),
        **quote_meta,
    )
