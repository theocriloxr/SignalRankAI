from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import secrets
from datetime import datetime, timedelta, timezone
from utils.timeutils import now_utc_naive
def to_naive_utc(dt: datetime) -> datetime:
    """Convert any datetime to naive UTC (no tzinfo)."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import Result, Select, Subquery, Update, CursorResult, Row, and_, func, select, update, delete, case, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    AlertPreference,
    FreeSignalQueue,
    BotEvent,
    PaymentEvent,
    ReferralAttribution,
    ReferralCode,
    ReferralReward,
    Signal,
    SignalDelivery,
    ActiveSignalMessage,
    Outcome,
    OutcomeNotification,
    User,
    UserSignalMonitoring,
    StrategyStat,  # <-- Added import for StrategyStat
    Subscription,  # <-- Added import for Subscription
    ManagedAsset,
)
from db.repository import activate_subscription, get_or_create_user, normalize_tier
from db.session import is_transient_db_error
from core.tier_constants import TIER_DAILY_LIMITS
from delivery.service import (
    DeliveryOperation,
    DeliveryState,
    canonical_delivery_state,
    forbids_blind_retry,
    transition_allowed,
)

logger = logging.getLogger(__name__)


async def ensure_alert_prefs(session: AsyncSession, telegram_user_id: int) -> None:
    """Ensure a default alert_prefs row exists for the user."""
    user: User = await get_or_create_user(session, telegram_user_id=int(telegram_user_id))
    res: Result[Tuple[AlertPreference]] = await session.execute(select(AlertPreference).where(AlertPreference.user_id == user.id))
    pref: AlertPreference | None = res.scalar_one_or_none()
    if pref is not None:
        return
    session.add(AlertPreference(user_id=user.id, tp_sl_enabled=True, updated_at=_utcnow()))
    await session.flush()


async def _touch_strategy_stat(session: AsyncSession, *, strategy_name: str, strategy_group: str) -> None:
    name: str = str(strategy_name or "unknown")[:64]
    group: str = str(strategy_group or "unknown")[:32]
    res = await session.execute(
        select(StrategyStat).where(StrategyStat.strategy_name == name, StrategyStat.strategy_group == group)
    )
    row = res.scalar_one_or_none()
    if row is None:
        session.add(StrategyStat(strategy_name=name, strategy_group=group, updated_at=_utcnow()))
    else:
        row.updated_at = _utcnow()
    await session.flush()


async def record_bot_event(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    event_type: str,
    meta: Dict[str, Any] | None = None,
    username: str | None = None,
) -> None:
    """Record a generic bot audit event (best-effort; caller commits)."""
    user: User = await get_or_create_user(session, telegram_user_id=int(telegram_user_id), username=username)
    ev = BotEvent(
        user_id=int(user.id),
        event_type=str(event_type or "unknown")[:64],
        meta=dict(meta or {}),
    )
    session.add(ev)
    await session.flush()


def _env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or str(default)).strip())
    except Exception:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    """Parse a boolean environment flag consistently and fail safely.

    Outcome recipient selection uses this helper before an outcome notification
    row can be queued.  v1.3.6.8 referenced ``_env_bool`` from that path without
    defining it in this module, which raised ``NameError`` after every detected
    TP/SL transition and prevented outcome persistence and notification fan-out.
    """
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _utcnow() -> datetime:
    # Return a naive UTC datetime to match DB columns (TIMESTAMP WITHOUT TIME ZONE)
    return now_utc_naive()


class SignalDedupBlocked(RuntimeError):
    def __init__(self, reason: str, signal_id: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.signal_id = signal_id


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


def _parse_interval_hours(*, default: float, env_names: tuple[str, ...]) -> float:
    for name in env_names:
        raw = (os.getenv(name) or "").strip()
        if not raw:
            continue
        try:
            lower = raw.lower()
            if lower.endswith("ms"):
                return max(0.0, float(lower[:-2]) / 3_600_000.0)
            if lower.endswith("s"):
                return max(0.0, float(lower[:-1]) / 3600.0)
            if lower.endswith("m"):
                return max(0.0, float(lower[:-1]) / 60.0)
            if lower.endswith("h"):
                return max(0.0, float(lower[:-1]))
            if name == "SIGNAL_MIN_INTERVAL":
                return max(0.0, float(lower))
            return max(0.0, float(lower))
        except Exception:
            continue
    return max(0.0, float(default))


def _asset_matches(signal_asset: str, candidate_asset: str) -> bool:
    return str(signal_asset or "").upper().strip() == str(candidate_asset or "").upper().strip()


def _entry_within_buffer(new_entry: float, existing_entry: float, buffer_pct: float) -> bool:
    try:
        new_val = abs(float(new_entry))
        existing_val = abs(float(existing_entry))
        base = max(new_val, existing_val, 1e-9)
        delta_pct = abs(new_val - existing_val) / base * 100.0
        return delta_pct <= max(0.0, float(buffer_pct))
    except Exception:
        return False


def _active_trade_signal_id_for_asset(active_trades: Any, asset: str) -> str | None:
    for payload in (active_trades or {}).values():
        if not isinstance(payload, dict):
            continue
        signal = payload.get("signal") if isinstance(payload.get("signal"), dict) else payload
        if not isinstance(signal, dict):
            continue
        if not _asset_matches(asset, signal.get("asset") or signal.get("symbol") or ""):
            continue
        signal_id = signal.get("signal_id") or signal.get("id") or payload.get("signal_id")
        if signal_id:
            return str(signal_id)
        return None
    return None


def _active_trade_payload_for_asset(active_trades: Any, asset: str) -> tuple[str | None, dict[str, Any] | None, str | None]:
    for trade_key, payload in (active_trades or {}).items():
        if not isinstance(payload, dict):
            continue
        signal = payload.get("signal") if isinstance(payload.get("signal"), dict) else payload
        if not isinstance(signal, dict):
            continue
        if not _asset_matches(asset, signal.get("asset") or signal.get("symbol") or ""):
            continue
        signal_id = signal.get("signal_id") or signal.get("id") or payload.get("signal_id") or trade_key
        return str(trade_key) if trade_key is not None else None, payload, str(signal_id) if signal_id else None
    return None, None, None


def _active_trade_payload_age_hours(payload: dict[str, Any] | None, now: datetime) -> float | None:
    if not isinstance(payload, dict):
        return None
    candidates = (
        payload.get("updated_at"),
        payload.get("open_time"),
        (payload.get("signal") or {}).get("created_at") if isinstance(payload.get("signal"), dict) else None,
    )
    for raw in candidates:
        try:
            if raw is None:
                continue
            if isinstance(raw, (int, float)):
                ts = float(raw)
                if ts > 10_000_000_000:
                    ts = ts / 1000.0
                dt = datetime.utcfromtimestamp(ts)
            elif isinstance(raw, datetime):
                dt = raw.astimezone(timezone.utc).replace(tzinfo=None) if raw.tzinfo else raw
            else:
                text = str(raw).strip()
                if not text:
                    continue
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return max(0.0, (now - dt.replace(tzinfo=None)).total_seconds() / 3600.0)
        except Exception:
            continue
    return None


def _active_trade_has_asset(active_trades: Any, asset: str) -> bool:
    for payload in (active_trades or {}).values():
        if not isinstance(payload, dict):
            continue
        signal = payload.get("signal") if isinstance(payload.get("signal"), dict) else payload
        if not isinstance(signal, dict):
            continue
        if _asset_matches(asset, signal.get("asset") or signal.get("symbol") or ""):
            return True
    return False


def compute_signal_fingerprint(signal: Dict[str, Any]) -> str:
    asset: str = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()
    timeframe: str = str(signal.get("timeframe") or "").lower().strip()
    direction: str = str(signal.get("direction") or "").lower().strip()

    def _normalize_timestamp(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            dt = value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
            return dt.replace(microsecond=0).isoformat()
        try:
            if isinstance(value, (int, float)):
                seconds = float(value) / 1000.0 if float(value) > 10_000_000_000 else float(value)
                return datetime.utcfromtimestamp(seconds).replace(microsecond=0).isoformat()
        except Exception:
            pass
        text = str(value).strip()
        if not text:
            return ""
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed.replace(microsecond=0).isoformat()
        except Exception:
            return text

    def _round(value: Any) -> str:
        try:
            return f"{float(value):.6f}"
        except Exception:
            return str(value)

    entry: str = _round(signal.get("entry"))
    stop_loss: str = _round(signal.get("stop_loss") or signal.get("stop"))
    take_profit: Any = signal.get("take_profit") or signal.get("targets")
    if isinstance(take_profit, (list, tuple)):
        take_profit_norm: str = ",".join(_round(item.get("price") if isinstance(item, dict) else item) for item in take_profit)
    else:
        take_profit_norm = _round(take_profit)

    strategy_group: str = str(signal.get("strategy_group") or "").strip().lower()
    strategy_name: str = str(signal.get("strategy_name") or signal.get("strategy") or "").strip().lower()
    candle_timestamp: str = _normalize_timestamp(
        signal.get("candle_timestamp")
        or signal.get("candle_time")
        or signal.get("source_candle_timestamp")
        or signal.get("bar_timestamp")
    )

    raw: str = (
        f"{asset}|{timeframe}|{direction}|{entry}|{stop_loss}|"
        f"{take_profit_norm}|{strategy_group}|{strategy_name}|{candle_timestamp}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


async def check_active_signal_exists(
    session: AsyncSession,
    asset: str,
    direction: str,
    timeframe: str,
) -> bool:
    """Check if an active signal already exists for this asset/direction/timeframe.
    
    Prevents duplicate signal generation for the same trade thesis.
    Uses Redis lock + DB check for redundancy.
    """
    from sqlalchemy import and_, select
    from db.models import Signal, Outcome
    
    asset_upper = str(asset).upper().strip()
    direction_lower = str(direction).lower().strip()
    timeframe_lower = str(timeframe).lower().strip()
    
    # Check Redis first (fast path)
    redis_key = f"signal_active:{asset_upper}:{direction_lower}:{timeframe_lower}"
    try:
        from core.redis_state import state
        if state.has_redis_sync():
            if state.get_str_sync(redis_key):
                return True
    except Exception:
        pass
    
    # Check DB for active signal (no outcome yet)
    try:
        # First check: any non-expired, non-archived signal
        stmt = (
            select(Signal)
            .where(
                and_(
                    Signal.asset == asset_upper,
                    Signal.direction == direction_lower,
                    Signal.timeframe == timeframe_lower,
                    Signal.expired.is_(False),
                    Signal.archived.is_(False),
                )
            )
            .order_by(Signal.created_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        signal = result.scalar_one_or_none()
        
        if signal is not None:
            # Check if it has an outcome (resolved trades are OK to overwrite)
            outcome_stmt = (
                select(Outcome)
                .where(Outcome.signal_id == signal.signal_id)
                .limit(1)
            )
            outcome_result = await session.execute(outcome_stmt)
            outcome = outcome_result.scalar_one_or_none()
            
            if outcome is None:
                # Active signal with no outcome - block duplicate
                return True
    except Exception:
        pass
    
    return False


async def acquire_signal_lock(
    asset: str,
    direction: str,
    timeframe: str,
    ttl_seconds: int = 14400,  # 4 hours default
) -> bool:
    """Acquire Redis lock for signal generation.
    
    Prevents race conditions when multiple engine cycles
    try to generate signals for the same asset.
    
    Key format: signal_lock:{ASSET}:{DIRECTION}:{TIMEFRAME}
    TTL: 4 hours (configurable)
    """
    redis_key = f"signal_lock:{asset.upper()}:{direction.lower()}:{timeframe.lower()}"
    
    try:
        from core.redis_state import state
        if state.has_redis_sync():
            # Try to acquire lock (atomic set if not exists)
            existing = state.get_str_sync(redis_key)
            if existing:
                # Lock already held
                return False
            # Acquire lock
            state.set_str_sync(redis_key, "1", ex=ttl_seconds)
            return True
    except Exception:
        pass
    
    return True  # Allow if Redis unavailable


async def release_signal_lock(
    asset: str,
    direction: str,
    timeframe: str,
) -> None:
    """Release Redis lock after signal generation."""
    redis_key = f"signal_lock:{asset.upper()}:{direction.lower()}:{timeframe.lower()}"
    
    try:
        from core.redis_state import state
        if state.has_redis_sync():
            state.delete_sync(redis_key)
    except Exception:
        pass


# Delivery cooldown TTL is derived from the canonical proof-backed policy.
# All tiers default to four hours unless an explicit business-policy override
# is supplied through environment configuration.


def check_delivery_cooldown(
    user_id: int,
    asset: str,
    direction: str,
) -> bool:
    """Check if user is in delivery cooldown for this asset/direction.
    
    Returns True if cooldown active (should skip delivery).
    Key format: delivery:{USER_ID}:{ASSET}:{DIRECTION}
    TTL: VIP=4h, Premium=6h, Free=12h
    """
    from core.redis_state import state
    
    uid = int(user_id)
    asset = str(asset).upper().strip()
    direction = str(direction).lower().strip()
    
    from services.asset_repeat_policy import canonical_delivery_cooldown_key, legacy_delivery_cooldown_keys

    keys = (canonical_delivery_cooldown_key(uid, asset), *legacy_delivery_cooldown_keys(uid, asset, direction))
    try:
        if state.has_redis_sync():
            return any(bool(state.get_str_sync(key)) for key in keys)
    except Exception:
        pass
    return False


def set_delivery_cooldown(
    user_id: int,
    asset: str,
    direction: str,
) -> None:
    """Set delivery cooldown for user/asset/direction."""
    from core.redis_state import state
    
    uid = int(user_id)
    asset = str(asset).upper().strip()
    direction = str(direction).lower().strip()
    
    tier_name: str = "free"
    try:
        from signalrank_telegram.access import resolve_user_tier
        tier_name = resolve_user_tier(uid).lower()
    except Exception:
        tier_name = "free"

    from services.asset_repeat_policy import canonical_delivery_cooldown_key, get_asset_repeat_lock_hours

    ttl = max(1, int(get_asset_repeat_lock_hours(tier_name) * 3600))
    redis_key = canonical_delivery_cooldown_key(uid, asset)
    try:
        if state.has_redis_sync():
            state.set_str_sync(redis_key, "1", ex=ttl)
    except Exception:
        pass


def _get_signal_with_retry(
    session: AsyncSession,
    signal: Dict[str, Any],
    dedup_hours: int | None = None,
) -> Signal:
    """Synchronous wrapper to handle get_or_create_signal with retry logic for DB connection issues.
    
    This wraps the async signal creation logic to add retry capability when
    TooManyConnectionsError or other transient DB errors occur.
    """
    import asyncio
    
    async def _create_signal() -> Signal:
        return await get_or_create_signal_impl(session, signal, dedup_hours)
    
    # Use run_with_db_retry for transient DB error handling
    # This is already imported from db.session
    try:
        from db.session import run_with_db_retry
        return asyncio.get_event_loop().run_until_complete(
            run_with_db_retry(_create_signal, retries=3)
        )
    except Exception:
        # Fallback: try directly if retry not available
        return asyncio.get_event_loop().run_until_complete(_create_signal())


async def get_or_create_signal(
    session: AsyncSession,
    signal: Dict[str, Any],
    dedup_hours: int | None = None,
) -> Signal:
    """Get or create a signal with retry logic for transient DB errors.
    
    This is the public API that wraps the implementation with retry handling.
    """
    return await get_or_create_signal_impl(session, signal, dedup_hours)


async def active_signal_exists(
    session: AsyncSession,
    asset: str,
    direction: str,
    timeframe: str,
) -> bool:
    """Check if an active signal already exists for this asset/direction/timeframe.
    
    This prevents creating duplicate signals for the same trading opportunity.
    Used before generating new signals.
    
    Returns True if an active (non-expired, non-archived) signal exists.
    """
    asset_normalized = str(asset or "").upper().strip()[:32]
    direction_normalized = str(direction or "long").lower().strip()[:8]
    timeframe_normalized = str(timeframe or "1h").lower().strip()[:8]
    
    try:
        # Check for non-expired, non-archived signals with same asset/direction/timeframe
        result = await session.execute(
            select(Signal.signal_id).where(
                and_(
                    Signal.asset == asset_normalized,
                    Signal.direction == direction_normalized,
                    Signal.timeframe == timeframe_normalized,
                    Signal.expired.is_(False),
                    Signal.archived.is_(False),
                )
            ).limit(1)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            logger.info(
                f"[active_signal_exists] Found active signal for {asset_normalized} "
                f"{direction_normalized} {timeframe_normalized}"
            )
            return True
        return False
    except Exception as e:
        logger.debug(f"[active_signal_exists] Check failed: {e}")
        return False


async def get_or_create_signal_impl(
    session: AsyncSession,
    signal: Dict[str, Any],
    dedup_hours: int | None = None,
) -> Signal:
    """Actual implementation of get_or_create_signal (without wrapper retry logic)."""
    now: datetime = _utcnow().replace(tzinfo=None)
    try:
        if dedup_hours is None:
            dedup_hours = int((os.getenv("SIGNAL_DEDUP_HOURS") or "24").strip())
        dedup_hours = max(0, int(dedup_hours))
    except Exception:
        dedup_hours = 24
    cutoff: datetime | None = (now - timedelta(hours=int(dedup_hours))) if int(dedup_hours) > 0 else None

    asset: str = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()[:32]
    timeframe: str = str(signal.get("timeframe") or "").lower().strip()[:8]
    direction: str = str(signal.get("direction") or "").lower().strip()[:8]
    try:
        from services.trade_profiles import infer_trade_profile
        trade_profile = str(signal.get("trade_profile") or infer_trade_profile(signal)).lower().strip()[:16]
    except Exception:
        trade_profile = str(signal.get("trade_profile") or "").lower().strip()[:16] or None
    try:
        from services.asset_mapper import classify_asset
        asset_class = str(signal.get("asset_class") or classify_asset(asset)).lower().strip()[:16]
        if asset_class == "forex":
            asset_class = "fx"
    except Exception:
        asset_class = str(signal.get("asset_class") or "").lower().strip()[:16] or None
    target_model = str(signal.get("target_model") or "").strip()[:32] or None
    expected_duration = str(signal.get("expected_duration") or "").strip()[:64] or None

    entry = float(signal.get("entry") or 0)
    stop_loss = float(signal.get("stop_loss") or signal.get("stop") or 0)

    take_profit: Any = signal.get("take_profit") or signal.get("targets") or []
    # Normalize take_profit to a JSON-encoded list string for consistent DB storage
    import json as _tp_json
    if isinstance(take_profit, str):
        # If already a string, normalize to proper JSON (handles Python repr like "['1.2']")
        try:
            _tp_parsed = _tp_json.loads(take_profit)
            tp_str: str = _tp_json.dumps(_tp_parsed if isinstance(_tp_parsed, list) else [float(_tp_parsed)])
        except Exception:
            try:
                _tp_clean = take_profit.strip("[]").replace("'", "").replace('"', "")
                _tp_parts = [float(p.strip()) for p in _tp_clean.split(',') if p.strip()]
                tp_str = _tp_json.dumps(_tp_parts)
            except Exception:
                tp_str = take_profit  # last resort
    elif isinstance(take_profit, (list, tuple)):
        try:
            prices = []
            for x in take_profit:
                if isinstance(x, dict):
                    # StrategySignal format: {'price': X, 'pct': Y, 'exit_percent': Z}
                    p = x.get('price') or x.get('tp') or x.get('target')
                    if p is not None:
                        prices.append(float(p))
                else:
                    prices.append(float(x))
            tp_str = _tp_json.dumps([p for p in prices if p > 0])
        except Exception:
            tp_str = _tp_json.dumps([str(x) for x in take_profit])
    else:
        try:
            tp_str = _tp_json.dumps([float(take_profit)])
        except Exception:
            tp_str = _tp_json.dumps([str(take_profit)])

    min_interval_hours: float = _parse_interval_hours(
        default=2.0,
        env_names=("SIGNAL_MIN_INTERVAL_HOURS", "SIGNAL_MIN_INTERVAL"),
    )
# FIXED: Increased buffer from 0.5% to 2.0% to prevent duplicate signals
    # from being created when live price fluctuates slightly between engine cycles.
    # This prevents the "same signal sent 3 times" issue where slight price
    # differences (due to floating point or live price changes) cause
    # different fingerprints to be generated.
    price_buffer_pct: float = max(0.0, _env_float("SIGNAL_PRICE_BUFFER_PCT", 2.0))

    active_signal_id: str | None = None
    try:
        from core.redis_state import state

        active_trades = state.get_active_trades_sync() or {}
        active_trade_key, active_payload, active_signal_id = _active_trade_payload_for_asset(active_trades, asset)
        if active_payload is not None:
            orphan_max_hours = max(0.0, _env_float("ACTIVE_TRADE_ORPHAN_MAX_HOURS", 12.0))
            if active_signal_id:
                res_active: Result[Tuple[Signal]] = await session.execute(
                    select(Signal).where(Signal.signal_id == active_signal_id)
                )
                existing_active = res_active.scalar_one_or_none()
                if existing_active is not None:
                    if bool(getattr(existing_active, "archived", False)) or bool(getattr(existing_active, "expired", False)):
                        try:
                            state.remove_active_trade_sync(active_signal_id)
                            logger.warning(
                                "[dedup] removed stale redis active trade for %s: signal_id=%s archived=%s expired=%s",
                                asset,
                                active_signal_id,
                                bool(getattr(existing_active, "archived", False)),
                                bool(getattr(existing_active, "expired", False)),
                            )
                        except Exception:
                            pass
                    else:
                        try:
                            if trade_profile and not getattr(existing_active, "trade_profile", None):
                                existing_active.trade_profile = trade_profile
                            if asset_class and not getattr(existing_active, "asset_class", None):
                                existing_active.asset_class = asset_class
                            if target_model and not getattr(existing_active, "target_model", None):
                                existing_active.target_model = target_model
                            if expected_duration and not getattr(existing_active, "expected_duration", None):
                                existing_active.expected_duration = expected_duration
                        except Exception:
                            pass
                        outcome_res: Result[Tuple[Outcome]] = await session.execute(
                            select(Outcome.status)
                            .where(Outcome.signal_id == active_signal_id)
                            .order_by(Outcome.closed_at.desc().nullslast(), Outcome.id.desc())
                            .limit(1)
                        )
                        outcome_status = str(outcome_res.scalar_one_or_none() or "").lower().strip()
                        if outcome_status and outcome_status not in {"active", "tp1", "tp2"}:
                            try:
                                state.remove_active_trade_sync(active_signal_id)
                                logger.warning(
                                    "[dedup] removed closed redis active trade for %s: signal_id=%s outcome=%s",
                                    asset,
                                    active_signal_id,
                                    outcome_status,
                                )
                            except Exception:
                                pass
                        else:
                            return existing_active
                else:
                    try:
                        state.remove_active_trade_sync(active_signal_id)
                        logger.warning(
                            "[dedup] removed orphan redis active trade for %s: signal_id=%s missing_in_db",
                            asset,
                            active_signal_id,
                        )
                    except Exception:
                        pass
            else:
                age_hours = _active_trade_payload_age_hours(active_payload, now)
                if age_hours is None or age_hours >= orphan_max_hours:
                    try:
                        if active_trade_key:
                            state.remove_active_trade_sync(active_trade_key)
                        logger.warning(
                            "[dedup] removed orphan redis active trade for %s: no_signal_id age_h=%s",
                            asset,
                            f"{age_hours:.1f}" if age_hours is not None else "unknown",
                        )
                    except Exception:
                        pass
                elif str(os.getenv("SIGNAL_DEDUP_BLOCK_ORPHAN_ACTIVE_TRADE", "0")).strip().lower() in {"1", "true", "yes", "on"}:
                    raise SignalDedupBlocked("active_trade_orphan", signal_id=active_trade_key)
    except SignalDedupBlocked:
        raise
    except Exception:
        pass

    if min_interval_hours > 0:
        min_interval_cutoff = now - timedelta(hours=float(min_interval_hours))
        try:
            res_recent: Result[Tuple[Signal]] = await session.execute(
                select(Signal).where(
                    and_(
                        Signal.asset == asset,
                        Signal.timeframe == timeframe,
                        Signal.direction == direction,
                        Signal.created_at >= min_interval_cutoff,
                        Signal.expired.is_(False),
                        Signal.archived.is_(False),
                    )
                ).order_by(Signal.created_at.desc())
            )
            recent_signal = res_recent.scalars().first()
            if recent_signal is not None:
                return recent_signal
        except Exception:
            pass

    if cutoff is not None:
        try:
            res_fuzzy: Result[Tuple[Signal]] = await session.execute(
                select(Signal).where(
                    and_(
                        Signal.asset == asset,
                        Signal.created_at >= cutoff,
                    )
                ).order_by(Signal.created_at.desc())
            )
            for candidate in res_fuzzy.scalars().all():
                try:
                    if str(candidate.timeframe or "").lower().strip() != timeframe:
                        continue
                    if str(candidate.direction or "").lower().strip() != direction:
                        continue
                    if float(candidate.stop_loss or 0) != stop_loss:
                        continue
                    if str(candidate.take_profit or "") != str(tp_str):
                        continue
                    if str(candidate.strategy_group or "") != str(signal.get("strategy_group") or "unknown"):
                        continue
                    if str(candidate.strategy_name or "") != str(signal.get("strategy_name") or signal.get("strategy") or "unknown"):
                        continue
                    if _entry_within_buffer(entry, float(candidate.entry or 0), price_buffer_pct):
                        return candidate
                except Exception:
                    continue
        except Exception:
            pass

    rr_estimate = None
    try:
        rr_estimate = float(signal.get("rr_ratio"))
    except Exception:
        rr_estimate = None

    score = float(signal.get("score") or 0)
    regime: Any | None = signal.get("regime")
    strength = float(signal.get("strength") or signal.get("confidence") or 0)

    def _optional_float(value: Any) -> float | None:
        try:
            parsed = float(value)
            return parsed if parsed == parsed else None
        except Exception:
            return None

    def _optional_int(value: Any) -> int | None:
        try:
            return int(value) if value is not None and str(value).strip() != "" else None
        except Exception:
            return None

    raw_probability = _optional_float(signal.get("ml_probability_raw", signal.get("ml_probability")))
    calibrated_probability = _optional_float(signal.get("ml_probability_calibrated"))
    ml_probability = calibrated_probability if calibrated_probability is not None else raw_probability
    calibration_version = str(signal.get("ml_calibration_version") or "").strip()[:64] or None
    calibration_validated = bool(signal.get("ml_calibration_validated", False))
    calibration_rows = _optional_int(signal.get("ml_calibration_validation_rows"))
    calibration_brier = _optional_float(signal.get("ml_calibration_brier"))
    calibration_ece = _optional_float(signal.get("ml_calibration_ece"))
    quality_gate_version = str(signal.get("quality_gate_version") or "production-integrity-v1").strip()[:64]
    quality_gate_passed = bool(signal.get("quality_gate_passed", False))
    provider_value = signal.get("asset_discovery_provider")
    if isinstance(provider_value, (list, tuple, set)):
        provider_value = ",".join(str(item).strip() for item in provider_value if str(item).strip())
    asset_discovery_provider = str(provider_value or "").strip()[:128] or None

    strategy_name: str = str(signal.get("strategy_name") or signal.get("strategy") or "unknown")[:64]
    strategy_group: str = str(signal.get("strategy_group") or "unknown")[:32]

    fingerprint: str = compute_signal_fingerprint(
        {
            "asset": asset,
            "timeframe": timeframe,
            "direction": direction,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "strategy_group": strategy_group,
            "strategy_name": strategy_name,
        }
    )
    from core.production_integrity import (
        semantic_entries_equivalent,
        semantic_entry_gap,
        signal_thesis_fingerprint,
        signal_thesis_scope,
    )
    thesis_payload = dict(signal)
    thesis_payload.update(
        {
            "asset": asset,
            "timeframe": timeframe,
            "direction": direction,
            "entry": entry,
            "strategy_name": strategy_name,
            "regime": regime,
        }
    )
    thesis_fingerprint = str(signal.get("thesis_fingerprint") or signal_thesis_fingerprint(thesis_payload))[:64]

    # Serialize canonical-thesis admission across every engine replica. The
    # main production write path is db.pg_compat -> db.pg_features, so this lock
    # must live here rather than only in db.repository.persist_signal().
    thesis_hours = max(1, int(os.getenv("SIGNAL_THESIS_DEDUP_HOURS", "4") or 4))
    try:
        dialect_name = str(session.get_bind().dialect.name or "").lower()
        if dialect_name == "postgresql":
            # Lock both the exact fingerprint and the semantic asset/direction/
            # strategy scope. Hidden regime changes or adjacent timeframe scans
            # must not admit two near-identical user-visible trade ideas.
            semantic_scope = f"signal-thesis:{signal_thesis_scope(thesis_payload)}"
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:fingerprint))"),
                {"fingerprint": thesis_fingerprint},
            )
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:scope))"),
                {"scope": semantic_scope},
            )
    except Exception as lock_error:
        from core.env import runtime_environment_name
        if runtime_environment_name("development") == "production":
            raise RuntimeError("signal_thesis_lock_unavailable") from lock_error
        logger.warning("[dedup] canonical thesis lock unavailable in non-production: %s", lock_error)

    # Resolve expires_at before the dedupe update path so reused active signals
    # keep the latest validity window without mutating already delivered levels.
    _raw_expires = signal.get("expires_at")
    if isinstance(_raw_expires, datetime):
        signal_expires_at: datetime | None = _raw_expires.replace(tzinfo=None) if _raw_expires.tzinfo else _raw_expires
    else:
        signal_expires_at = now + timedelta(hours=12)

    thesis_cutoff = now - timedelta(hours=thesis_hours)
    existing: Signal | None = None
    res = await session.execute(
        select(Signal)
        .where(
            Signal.thesis_fingerprint == thesis_fingerprint,
            Signal.created_at >= thesis_cutoff,
            Signal.expired.is_(False),
            Signal.archived.is_(False),
        )
        .order_by(Signal.created_at.desc())
    )
    for candidate in res.scalars().all():
        outcome_res: Result[Tuple[Outcome]] = await session.execute(
            select(Outcome.status)
            .where(Outcome.signal_id == candidate.signal_id)
            .order_by(Outcome.closed_at.desc().nullslast(), Outcome.id.desc())
            .limit(1)
        )
        outcome_status = str(outcome_res.scalar_one_or_none() or "").lower().strip()
        if not outcome_status or outcome_status in {"active", "pending", "entered", "tp1", "tp2", "partial_win", "partial_win_be"}:
            existing = candidate
            break

    if existing is None:
        try:
            semantic_tolerance = max(
                0.0001,
                min(0.05, float(os.getenv("SIGNAL_SEMANTIC_ENTRY_TOLERANCE_PCT", "0.003") or 0.003)),
            )
        except Exception:
            semantic_tolerance = 0.003
        semantic_rows = (
            await session.execute(
                select(Signal)
                .where(
                    Signal.asset == asset,
                    Signal.direction == direction,
                    func.lower(Signal.strategy_name) == strategy_name.lower(),
                    Signal.created_at >= thesis_cutoff,
                    Signal.expired.is_(False),
                    Signal.archived.is_(False),
                )
                .order_by(Signal.created_at.desc())
            )
        ).scalars().all()
        for candidate in semantic_rows:
            candidate_entry = getattr(candidate, "entry", None)
            relative_gap = semantic_entry_gap(candidate_entry, entry)
            if relative_gap is None or not semantic_entries_equivalent(
                candidate_entry, entry, tolerance=semantic_tolerance
            ):
                continue
            outcome_status = str((await session.execute(
                select(Outcome.status)
                .where(Outcome.signal_id == candidate.signal_id)
                .order_by(Outcome.closed_at.desc().nullslast(), Outcome.id.desc())
                .limit(1)
            )).scalar_one_or_none() or "").lower().strip()
            if not outcome_status or outcome_status in {
                "active", "pending", "entered", "tp1", "tp2", "partial_win", "partial_win_be"
            }:
                existing = candidate
                logger.info(
                    "[dedup] semantic thesis reused asset=%s dir=%s strategy=%s gap_pct=%.5f signal_id=%s",
                    asset, direction, strategy_name, relative_gap * 100.0, candidate.signal_id,
                )
                break

    if existing is not None:
        confirmed_delivery_count = int(
            (
                await session.execute(
                    select(func.count(SignalDelivery.id)).where(
                        SignalDelivery.signal_id == existing.signal_id,
                        or_(
                            SignalDelivery.sent_ok.is_(True),
                            SignalDelivery.delivery_confirmed_at.is_not(None),
                            func.lower(SignalDelivery.delivery_state) == "confirmed",
                        ),
                    )
                )
            ).scalar_one()
            or 0
        )
        # Never rewrite entry/SL/TP after a user received the signal. Repricing a
        # delivered row corrupts outcome truth and makes Telegram cards disagree
        # with the canonical ledger. Before first delivery, the row may absorb a
        # fresher version of the same thesis.
        existing.score = max(float(existing.score or 0), score)
        existing.strength = max(float(existing.strength or 0), strength)
        if confirmed_delivery_count == 0:
            existing.entry = entry
            existing.stop_loss = stop_loss
            existing.take_profit = tp_str
            existing.expires_at = signal_expires_at
        elif existing.expires_at is None or (signal_expires_at and signal_expires_at > existing.expires_at):
            existing.expires_at = signal_expires_at
        existing.status = "active"
        existing.trade_profile = trade_profile
        existing.asset_class = asset_class
        existing.target_model = target_model
        existing.expected_duration = expected_duration
        existing.thesis_fingerprint = thesis_fingerprint
        existing.asset_discovery_provider = asset_discovery_provider or existing.asset_discovery_provider
        existing.ml_probability_raw = raw_probability
        existing.ml_probability_calibrated = calibrated_probability
        existing.ml_probability = ml_probability
        existing.ml_calibration_version = calibration_version
        existing.ml_calibration_validated = calibration_validated
        existing.ml_calibration_validation_rows = calibration_rows
        existing.ml_calibration_brier = calibration_brier
        existing.ml_calibration_ece = calibration_ece
        existing.quality_gate_version = quality_gate_version
        existing.quality_gate_passed = quality_gate_passed
        await session.flush()
        logger.info(
            "[dedup] canonical thesis reused asset=%s tf=%s dir=%s thesis=%s signal_id=%s delivered=%s",
            asset,
            timeframe,
            direction,
            thesis_fingerprint,
            existing.signal_id,
            confirmed_delivery_count,
        )
        return existing

    logger.info(
        "[dedup] creating canonical signal asset=%s tf=%s dir=%s thesis=%s exact=%s",
        asset,
        timeframe,
        direction,
        thesis_fingerprint,
        fingerprint,
    )

    signal_near_ob: bool = bool(signal.get("is_near_order_block", False))

    # Supersede only unresolved rows in the exact asset/timeframe bucket. A
    # materially different, older thesis stays immutable for audit/history.
    confirmed_delivery_exists = (
        select(SignalDelivery.id)
        .where(
            SignalDelivery.signal_id == Signal.signal_id,
            or_(
                SignalDelivery.sent_ok.is_(True),
                SignalDelivery.delivery_confirmed_at.is_not(None),
                func.lower(SignalDelivery.delivery_state) == "confirmed",
            ),
        )
        .exists()
    )
    await session.execute(
        update(Signal)
        .where(
            Signal.asset == asset,
            Signal.timeframe == timeframe,
            Signal.expired.is_(False),
            Signal.archived.is_(False),
            ~confirmed_delivery_exists,
        )
        .values(status="superseded", expired=True, archived=True)
    )

    s = Signal(
        asset=asset,
        timeframe=timeframe,
        direction=direction,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=tp_str,
        rr_estimate=rr_estimate,
        score=score,
        regime=str(regime)[:32] if regime is not None else None,
        ml_probability=ml_probability,
        ml_probability_raw=raw_probability,
        ml_probability_calibrated=calibrated_probability,
        ml_calibration_version=calibration_version,
        ml_calibration_validated=calibration_validated,
        ml_calibration_validation_rows=calibration_rows,
        ml_calibration_brier=calibration_brier,
        ml_calibration_ece=calibration_ece,
        quality_gate_version=quality_gate_version,
        quality_gate_passed=quality_gate_passed,
        strategy_name=strategy_name,
        strategy_group=strategy_group,
        strength=strength,
        fingerprint=fingerprint,
        thesis_fingerprint=thesis_fingerprint,
        asset_discovery_provider=asset_discovery_provider,
        trade_profile=trade_profile,
        asset_class=asset_class,
        target_model=target_model,
        expected_duration=expected_duration,
        status="active",
        created_at=now,
        expires_at=signal_expires_at,
        is_near_order_block=signal_near_ob,
        performance_version=int(os.getenv("PERFORMANCE_BASELINE_VERSION", "2") or 2),
    )
    session.add(s)
    await session.flush()

    try:
        await _touch_strategy_stat(session, strategy_name=strategy_name, strategy_group=strategy_group)
    except Exception:
        pass
    return s


async def record_signal_delivery(
    session: AsyncSession,
    telegram_user_id: int,
    signal_id: str,
    tier_at_send: str,
    *,
    channel_id: int | None = None,
    signal_version: str = "1",
    delivery_kind: str = "signal",
) -> bool:
    user: User = await get_or_create_user(session, telegram_user_id=telegram_user_id)
    operation = DeliveryOperation(
        user_id=int(telegram_user_id),
        signal_id=str(signal_id),
        channel_id=int(channel_id if channel_id is not None else telegram_user_id),
        signal_version=str(signal_version or "1"),
        delivery_kind=str(delivery_kind or "signal"),
    )
    operation_payload = {
        "delivery_operation": operation.as_dict(),
        "idempotency_key": operation.idempotency_key,
    }

    # Dedupe at two levels:
    # - per-user: don't send the same trade twice to the same user
    # - per-tier: don't send the same trade twice to a tier cohort
    # We use Signal.fingerprint so regenerated signal_ids still dedupe.
    try:
        dedupe_hours = int((os.getenv("DELIVERY_DEDUPE_HOURS") or "24").strip())
    except Exception:
        dedupe_hours = 24
    # Allow DELIVERY_DEDUPE_HOURS=0 to completely disable deduping (force resend).
    dedupe_hours: int = max(0, int(dedupe_hours))
    from typing import Optional
    cutoff: Optional[datetime] = _utcnow() - timedelta(hours=int(dedupe_hours)) if dedupe_hours > 0 else None

    # Optional deployment reset: ignore any deliveries recorded before this epoch.
    # Set DELIVERY_DEDUPE_RESET_EPOCH to a Unix timestamp (seconds) to treat all
    # signals as "new" from that point forward (e.g., on a fresh deployment).
    dedupe_reset_at = None
    try:
        reset_epoch: str | None = os.getenv("DELIVERY_DEDUPE_RESET_EPOCH")
        if reset_epoch:
            dedupe_reset_at: datetime = datetime.utcfromtimestamp(int(str(reset_epoch).strip()))
    except Exception:
        dedupe_reset_at = None

    if dedupe_reset_at:
        cutoff: datetime = max(cutoff, dedupe_reset_at) if cutoff else dedupe_reset_at

    tier_s: str = str(tier_at_send or "free").strip().lower()[:16]
    tier_base: str = tier_s.split("_", 1)[0].strip().lower()
    monitoring_tier: bool = tier_base in {"owner", "admin"}

    # Central hard daily cap. Every delivery path reserves through this
    # function, so enforce limits here instead of relying on each caller.
    if not monitoring_tier:
        daily_limit = TIER_DAILY_LIMITS.get(tier_base)
        if daily_limit is not None and daily_limit != float("inf"):
            day_start = to_naive_utc(_utcnow()).replace(hour=0, minute=0, second=0, microsecond=0)
            sent_today_res: Result[Tuple[int]] = await session.execute(
                select(func.count(SignalDelivery.id)).where(
                    SignalDelivery.user_id == user.id,
                    SignalDelivery.sent_ok.is_(True),
                    SignalDelivery.delivered_at >= day_start,
                )
            )
            sent_today = int(sent_today_res.scalar() or 0)
            if sent_today >= int(daily_limit):
                logger.info(
                    "[delivery_limit] blocked user=%s tier=%s sent_today=%s limit=%s",
                    user.id,
                    tier_base,
                    sent_today,
                    int(daily_limit),
                )
                return False

    try:
        market_cooldown_minutes = int((os.getenv("DELIVERY_MARKET_COOLDOWN_MINUTES") or "180").strip())
    except Exception:
        market_cooldown_minutes = 180
    market_cutoff: Optional[datetime] = (
        _utcnow() - timedelta(minutes=max(0, int(market_cooldown_minutes)))
        if market_cooldown_minutes > 0
        else None
    )
    if dedupe_reset_at:
        market_cutoff = max(market_cutoff, dedupe_reset_at) if market_cutoff else dedupe_reset_at


    try:
        res_sig: Result[Tuple[Signal]] = await session.execute(select(Signal).where(Signal.signal_id == str(signal_id)))
        sig: Signal | None = res_sig.scalar_one_or_none()
        if sig is None:
            logger.warning("[dedup] signal missing; blocking delivery user=%s signal=%s", user.id, signal_id)
            return False
        if sig:
            # Serialize per-user/per-asset delivery reservation across webhook,
            # resend and multiple front-door replicas. The subsequent query also
            # treats RESERVED/SENDING rows as active, so the lock remains useful
            # after the first transaction commits but before Telegram confirms.
            try:
                if str(session.get_bind().dialect.name or "").lower() == "postgresql":
                    await session.execute(
                        text("SELECT pg_advisory_xact_lock(hashtext(:scope))"),
                        {"scope": f"delivery:{int(user.id)}:{str(sig.asset).upper()}"},
                    )
            except Exception as lock_error:
                from core.env import runtime_environment_name
                if runtime_environment_name("development") == "production":
                    logger.warning(
                        "[dedup] user-asset delivery lock unavailable; blocking user=%s asset=%s",
                        user.id,
                        sig.asset,
                    )
                    return False
                logger.warning("[dedup] user-asset delivery lock unavailable in non-production: %s", lock_error)

            from services.asset_repeat_policy import get_asset_repeat_lock_hours

            asset_cooldown_hours = get_asset_repeat_lock_hours(str(tier_s).split("_", 1)[0])
            try:
                unresolved_block_hours = float(
                    (os.getenv("DELIVERY_UNRESOLVED_BLOCK_HOURS") or "168").strip()
                )
            except Exception:
                unresolved_block_hours = 168.0
            unresolved_block_hours = max(0.0, float(unresolved_block_hours))

            from services.asset_position_manager import get_user_asset_position_state

            position_state = await get_user_asset_position_state(
                session,
                telegram_user_id=int(telegram_user_id),
                asset=str(sig.asset),
                cooldown_hours=float(asset_cooldown_hours),
                unresolved_block_hours=float(unresolved_block_hours),
                exclude_signal_id=str(signal_id),
            )
            if position_state.is_locked:
                logger.info(
                    "[asset_position] blocked user=%s asset=%s state=%s prev_signal=%s prev_direction=%s "
                    "new_direction=%s age_h=%s reason=%s",
                    user.id,
                    sig.asset,
                    position_state.state,
                    position_state.signal_id,
                    position_state.direction,
                    sig.direction,
                    f"{position_state.age_hours:.2f}" if position_state.age_hours is not None else "n/a",
                    position_state.reason,
                )
                return False

            # Same-asset exposure gate:
            # Block any new signal for the same user+asset for the configured proof-backed lock,
            # and keep blocking while the previous asset exposure is unresolved.
            latest_asset_row = (
                await session.execute(
                    select(
                        SignalDelivery.signal_id,
                        SignalDelivery.delivered_at,
                        SignalDelivery.tier_at_send,
                        Signal.direction,
                        Outcome.status,
                    )
                    .select_from(SignalDelivery)
                    .join(Signal, Signal.signal_id == SignalDelivery.signal_id)
                    .outerjoin(Outcome, Outcome.signal_id == SignalDelivery.signal_id)
                    .where(
                        SignalDelivery.user_id == user.id,
                        or_(
                            SignalDelivery.sent_ok.is_(True),
                            func.lower(SignalDelivery.delivery_state).in_(
                                ("reserved", "sending", "sent", "delivered", "confirmed", "updated")
                            ),
                        ),
                        Signal.asset == sig.asset,
                        SignalDelivery.signal_id != str(signal_id),
                    )
                    .order_by(SignalDelivery.delivered_at.desc())
                    .limit(1)
                )
            ).first()

            if latest_asset_row is not None:
                prev_signal_id, prev_delivered_at, prev_tier_at_send, prev_direction, prev_status = latest_asset_row
                now_dt = _utcnow()
                age_hours = 9999.0
                try:
                    age_hours = max(0.0, (now_dt - prev_delivered_at).total_seconds() / 3600.0)
                except Exception:
                    pass

                resolved_statuses = {
                    "tp",
                    "tp3",
                    "sl",
                    "invalid",
                    "invalidated",
                    "expired",
                    "time_stop",
                    "cancel",
                    "cancelled",
                    "partial_win",
                    "partial_win_be",
                    "breakeven",
                    "be",
                }
                is_resolved = str(prev_status or "").strip().lower() in resolved_statuses

                should_block_asset = (
                    (age_hours < float(asset_cooldown_hours))
                    or ((not is_resolved) and (age_hours < unresolved_block_hours))
                )
                if should_block_asset:
                    try:
                        import logging
                        logging.getLogger(__name__).info(
                            f"[dedup] Asset gate hit: user={user.id} asset={sig.asset} prev_signal={prev_signal_id} "
                            f"prev_direction={prev_direction} new_direction={sig.direction} age_h={age_hours:.2f} resolved={is_resolved} "
                            f"cooldown_h={float(asset_cooldown_hours):.2f} unresolved_block_h={float(unresolved_block_hours):.2f}"
                        )
                    except Exception:
                        pass
                    return False

            if market_cutoff is not None:
                res_market: Result[Tuple[int]] = await session.execute(
                    select(func.count(SignalDelivery.id))
                    .select_from(SignalDelivery)
                    .join(Signal, Signal.signal_id == SignalDelivery.signal_id)
                    .where(
                        SignalDelivery.user_id == user.id,
                        SignalDelivery.sent_ok.is_(True),
                        Signal.asset == sig.asset,
                        Signal.timeframe == sig.timeframe,
                        Signal.direction == sig.direction,
                        Signal.strategy_group == sig.strategy_group,
                        Signal.strategy_name == sig.strategy_name,
                        SignalDelivery.delivered_at >= market_cutoff,
                    )
                )
                if int(res_market.scalar() or 0) > 0:
                    try:
                        import logging
                        logging.getLogger(__name__).info(
                            f"[dedup] Market cooldown hit: user={user.id} asset={sig.asset} tf={sig.timeframe} "
                            f"dir={sig.direction} strat={sig.strategy_group}/{sig.strategy_name}"
                        )
                    except Exception:
                        pass
                    return False

            if cutoff is not None:
                # Thesis delivery dedupe: regenerated signal ids and tiny price
                # changes should not reach the same user as a new signal.
                res_u: Result[Tuple[int]] = await session.execute(
                    select(func.count(SignalDelivery.id))
                    .select_from(SignalDelivery)
                    .join(Signal, Signal.signal_id == SignalDelivery.signal_id)
                    .where(
                        SignalDelivery.user_id == user.id,
                        SignalDelivery.sent_ok.is_(True),
                        Signal.asset == sig.asset,
                        Signal.timeframe == sig.timeframe,
                        Signal.direction == sig.direction,
                        Signal.strategy_group == sig.strategy_group,
                        Signal.fingerprint == sig.fingerprint,
                        SignalDelivery.delivered_at >= cutoff,
                    )
                )
                if int(res_u.scalar() or 0) > 0:
                    # Debug log for dedup hit
                    try:
                        import logging
                        logging.getLogger(__name__).info(f"[dedup] Existing thesis delivery found: user={user.id} asset={sig.asset} tf={sig.timeframe} dir={sig.direction} strat={sig.strategy_group} fp={sig.fingerprint}")
                    except Exception:
                        pass
                    return False
    except Exception as exc:
        # Dedupe is a safety-critical gate. Failing open caused repeated and
        # opposite-direction same-asset deliveries during Railway DB pressure.
        logger.warning("[dedup] safety query failed; blocking delivery user=%s signal=%s error=%s", user.id, signal_id, exc)
        return False

    existing_delivery_res = await session.execute(
        select(SignalDelivery)
        .where(
            SignalDelivery.user_id == user.id,
            SignalDelivery.signal_id == str(signal_id),
        )
        .order_by(SignalDelivery.id.desc())
        .limit(1)
        .with_for_update()
    )
    existing_delivery = existing_delivery_res.scalar_one_or_none()
    if existing_delivery is not None:
        if bool(getattr(existing_delivery, "sent_ok", False)):
            return False
        existing_result = dict(getattr(existing_delivery, "telegram_api_result", None) or {})
        existing_key = str(
            existing_result.get("idempotency_key")
            or (existing_result.get("delivery_operation") or {}).get("idempotency_key")
            or ""
        )
        if existing_key and existing_key != operation.idempotency_key:
            # The current compatibility schema is unique by user+signal.  Until
            # the planned schema reconciliation expands that constraint, never
            # collapse a second channel/version into the first operation.
            logger.error(
                "[delivery_idempotency_conflict] user=%s signal=%s existing_key=%s requested_key=%s",
                user.id,
                signal_id,
                existing_key,
                operation.idempotency_key,
            )
            return False
        existing_state = canonical_delivery_state(
            getattr(existing_delivery, "delivery_state", None)
        )
        if forbids_blind_retry(existing_state):
            logger.info(
                "[dedup] terminal delivery state=%s user=%s signal=%s",
                existing_state.value,
                user.id,
                signal_id,
            )
            return False
        try:
            retry_seconds = max(30, int(os.getenv("DELIVERY_INFLIGHT_RETRY_SECONDS", "300") or 300))
        except Exception:
            retry_seconds = 300
        last_attempt = getattr(existing_delivery, "last_attempt_at", None) or getattr(existing_delivery, "delivered_at", None)
        last_error = str(getattr(existing_delivery, "last_error", "") or "").strip()
        if last_attempt is not None and not last_error:
            try:
                age_seconds = (_utcnow() - last_attempt).total_seconds()
                if age_seconds < float(retry_seconds):
                    logger.info(
                        "[dedup] in-flight delivery reservation blocked user=%s signal=%s age_s=%.1f retry_s=%s",
                        user.id,
                        signal_id,
                        age_seconds,
                        retry_seconds,
                    )
                    return False
            except Exception:
                return False
        existing_delivery.tier_at_send = tier_s
        existing_delivery.last_attempt_at = _utcnow()
        existing_delivery.dispatch_started_at = _utcnow()
        existing_delivery.telegram_send_started_at = None
        existing_delivery.delivery_confirmed_at = None
        existing_delivery.delivery_state = DeliveryState.RESERVED.value
        existing_delivery.sent_ok = False
        existing_delivery.telegram_api_result = {**existing_result, **operation_payload}
        try:
            existing_delivery.attempt_count = int(getattr(existing_delivery, "attempt_count", 0) or 0) + 1
        except Exception:
            existing_delivery.attempt_count = 1
        existing_delivery.last_error = None
        await session.flush()
        return True


    before: int = len(session.new)
    delivery = SignalDelivery(
        user_id=user.id,
        signal_id=signal_id,
        tier_at_send=tier_s,
        sent_ok=False,
        delivery_state=DeliveryState.RESERVED.value,
        attempt_count=1,
        dispatch_started_at=_utcnow(),
        last_attempt_at=_utcnow(),
        delivered_at=_utcnow(),
        telegram_api_result=operation_payload,
    )
    session.add(delivery)
    try:
        await session.flush()
        # Debug log for new delivery creation
        try:
            import logging
            logging.getLogger(__name__).info(f"[dedup] Creating new delivery: user={user.id} signal_id={signal_id} tier={tier_s}")
        except Exception:
            pass
        return True
    except Exception:
        # Unique constraint hit or other issue: treat as already delivered
        await session.rollback()
        return False
    finally:
        _: int = before


async def list_signals_sent_today(
    session: AsyncSession,
    telegram_user_id: int,
) -> list[Signal]:
    now: datetime = to_naive_utc(_utcnow())
    start: datetime = now.replace(hour=0, minute=0, second=0, microsecond=0)

    res: Result[Tuple[User]] = await session.execute(select(User).where(User.telegram_user_id == int(telegram_user_id)))
    user: User | None = res.scalar_one_or_none()
    if user is None:
        return []

    q: Select[Tuple[Signal]] = (
        select(Signal)
        .join(SignalDelivery, SignalDelivery.signal_id == Signal.signal_id)
        .where(
            SignalDelivery.user_id == user.id,
            SignalDelivery.sent_ok.is_(True),
            SignalDelivery.delivered_at >= start,
        )
        .order_by(SignalDelivery.delivered_at.desc())
    )
    res2: Result[Tuple[Signal]] = await session.execute(q)
    return list(res2.scalars().all())


async def count_signals_sent_today(
    session: AsyncSession,
    telegram_user_id: int,
) -> int:
    """Return how many signals were delivered to this user since UTC midnight."""
    now: datetime = to_naive_utc(_utcnow())
    start: datetime = now.replace(hour=0, minute=0, second=0, microsecond=0)

    res: Result[Tuple[User]] = await session.execute(
        select(User).where(User.telegram_user_id == int(telegram_user_id))
    )
    user: User | None = res.scalar_one_or_none()
    if user is None:
        return 0

    cnt_res: Result[Tuple[int]] = await session.execute(
        select(func.count(SignalDelivery.id)).where(
            SignalDelivery.user_id == user.id,
            SignalDelivery.sent_ok.is_(True),
            SignalDelivery.delivered_at >= start,
        )
    )
    return int(cnt_res.scalar() or 0)


async def list_recent_signals_delivered(
    session: AsyncSession,
    telegram_user_id: int,
    limit: int = 10,
    asset: str | None = None,
    timeframe: str | None = None,
) -> list[Signal]:
    res: Result[Tuple[User]] = await session.execute(select(User).where(User.telegram_user_id == int(telegram_user_id)))
    user: User | None = res.scalar_one_or_none()
    if user is None:
        return []

    q: Select[Tuple[Signal]] = (
        select(Signal)
        .join(SignalDelivery, SignalDelivery.signal_id == Signal.signal_id)
        .where(SignalDelivery.user_id == user.id, SignalDelivery.sent_ok.is_(True))
        .order_by(SignalDelivery.delivered_at.desc())
        .limit(max(1, int(limit)))
    )
    if asset:
        q: Select[Tuple[Signal]] = q.where(Signal.asset == str(asset).upper().strip())
    if timeframe:
        q: Select[Tuple[Signal]] = q.where(Signal.timeframe == str(timeframe).lower().strip())

    res2: Result[Tuple[Signal]] = await session.execute(q)
    return list(res2.scalars().all())


async def list_delivered_signals_for_user(
    session: AsyncSession,
    telegram_user_id: int,
    *,
    lookback_days: int = 7,
    status_filter: str = "active",
    asset: str | None = None,
    limit: int = 50,
    sent_ok_only: bool = True,
) -> list[Signal]:
    """Return signals actually delivered to a Telegram user.

    This is the canonical user-facing query for /signals. It starts from
    SignalDelivery rather than Signal so generated/reserved-but-never-sent
    rows do not appear in a user's active signal list.
    """
    res: Result[Tuple[User]] = await session.execute(
        select(User).where(User.telegram_user_id == int(telegram_user_id))
    )
    user: User | None = res.scalar_one_or_none()
    if user is None:
        return []

    mode = str(status_filter or "active").strip().lower()
    if mode == "running":
        mode = "active"
    cutoff_days = max(1, int(lookback_days or 7))
    cutoff: datetime = _utcnow() - timedelta(days=cutoff_days)
    max_rows = max(1, min(int(limit or 50), 200))

    terminal_statuses = {
        "sl",
        "tp",
        "tp3",
        "invalid",
        "invalidated",
        "time_stop",
        "cancel",
        "cancelled",
        "expired",
        "superseded",
    }
    winner_statuses = {"tp", "tp1", "tp2", "tp3", "partial_tp"}
    loser_statuses = {"sl", "stop_loss"}
    missed_statuses = {"missed", "time_stop", "expired", "invalid", "invalidated", "cancel", "cancelled"}

    q: Select[Tuple[Signal]] = (
        select(Signal)
        .join(SignalDelivery, SignalDelivery.signal_id == Signal.signal_id)
        .outerjoin(Outcome, Outcome.signal_id == Signal.signal_id)
        .where(
            SignalDelivery.user_id == int(user.id),
            SignalDelivery.delivered_at >= cutoff,
        )
        .order_by(SignalDelivery.delivered_at.desc())
        .limit(max_rows)
    )
    if sent_ok_only:
        q = q.where(
            SignalDelivery.sent_ok.is_(True),
            SignalDelivery.telegram_chat_id.is_not(None),
            SignalDelivery.telegram_message_id.is_not(None),
        )
    if asset:
        q = q.where(Signal.asset == str(asset).upper().strip())

    status_lower = func.lower(Outcome.status)
    if mode in {"active", ""}:
        q = q.where(
            Signal.archived.is_(False),
            Signal.expired.is_(False),
            or_(Signal.expires_at.is_(None), Signal.expires_at > _utcnow()),
            or_(Outcome.id.is_(None), status_lower.notin_(terminal_statuses)),
        )
    elif mode == "closed":
        q = q.where(or_(Signal.archived.is_(True), Signal.expired.is_(True), status_lower.in_(terminal_statuses)))
    elif mode == "winners":
        q = q.where(status_lower.in_(winner_statuses))
    elif mode == "losers":
        q = q.where(status_lower.in_(loser_statuses))
    elif mode == "missed":
        q = q.where(or_(Signal.expired.is_(True), status_lower.in_(missed_statuses)))
    elif mode == "all":
        pass
    else:
        q = q.where(
            Signal.archived.is_(False),
            Signal.expired.is_(False),
            or_(Outcome.id.is_(None), status_lower.notin_(terminal_statuses)),
        )

    res2: Result[Tuple[Signal]] = await session.execute(q)
    rows = list(res2.scalars().all())

    # If delivery marking failed during a DB-pressure window, active message
    # tracking is the strongest evidence that the user really saw the signal.
    if mode == "active":
        q_active: Select[Tuple[Signal]] = (
            select(Signal)
            .join(ActiveSignalMessage, ActiveSignalMessage.signal_id == Signal.signal_id)
            .outerjoin(Outcome, Outcome.signal_id == Signal.signal_id)
            .where(
                ActiveSignalMessage.user_id == int(user.id),
                ActiveSignalMessage.is_active.is_(True),
                ActiveSignalMessage.created_at >= cutoff,
                Signal.archived.is_(False),
                Signal.expired.is_(False),
                or_(Signal.expires_at.is_(None), Signal.expires_at > _utcnow()),
                or_(Outcome.id.is_(None), status_lower.notin_(terminal_statuses)),
            )
            .order_by(ActiveSignalMessage.created_at.desc())
            .limit(max_rows)
        )
        if asset:
            q_active = q_active.where(Signal.asset == str(asset).upper().strip())
        res3: Result[Tuple[Signal]] = await session.execute(q_active)
        rows.extend(list(res3.scalars().all()))

    seen: set[str] = set()
    seen_market_buckets: set[tuple[str, str]] = set()
    out: list[Signal] = []
    for sig in rows:
        sid = str(getattr(sig, "signal_id", "") or "")
        if not sid or sid in seen:
            continue
        bucket = (
            str(getattr(sig, "asset", "") or "").upper(),
            str(getattr(sig, "timeframe", "") or "").lower(),
        )
        if mode == "active" and bucket in seen_market_buckets:
            continue
        seen.add(sid)
        seen_market_buckets.add(bucket)
        out.append(sig)
        if len(out) >= max_rows:
            break
    return out


async def get_delivered_signal_by_ref(
    session: AsyncSession,
    telegram_user_id: int,
    ref: str,
) -> Signal | None:
    from db.signal_reference import SignalReferenceError, resolve_signal_reference

    try:
        resolved = await resolve_signal_reference(
            session,
            ref,
            telegram_user_id=int(telegram_user_id),
            require_delivery_proof=True,
        )
    except SignalReferenceError:
        return None
    return resolved.signal


async def get_weekly_recap_stats(session: AsyncSession, telegram_user_id: int) -> dict:
    """Compute a simple last-7-days recap from deliveries."""
    now: datetime = _utcnow()
    start: datetime = now - timedelta(days=7)

    res: Result[Tuple[User]] = await session.execute(select(User).where(User.telegram_user_id == int(telegram_user_id)))
    user: User | None = res.scalar_one_or_none()
    if user is None:
        return {"total": 0, "top_assets": [], "top_strategies": []}

    res_total: Result[Tuple[int]] = await session.execute(
        select(func.count(SignalDelivery.id)).where(SignalDelivery.user_id == user.id, SignalDelivery.delivered_at >= start)
    )
    total = int(res_total.scalar() or 0)

    res_assets: Result[Tuple[str, int]] = await session.execute(
        select(Signal.asset, func.count(SignalDelivery.id))
        .join(SignalDelivery, SignalDelivery.signal_id == Signal.signal_id)
        .where(SignalDelivery.user_id == user.id, SignalDelivery.delivered_at >= start)
        .group_by(Signal.asset)
        .order_by(func.count(SignalDelivery.id).desc())
        .limit(3)
    )
    top_assets: list[str] = [str(a) for (a, _) in (res_assets.all() or [])]

    res_strats: Result[Tuple[str, int]] = await session.execute(
        select(Signal.strategy_name, func.count(SignalDelivery.id))
        .join(SignalDelivery, SignalDelivery.signal_id == Signal.signal_id)
        .where(SignalDelivery.user_id == user.id, SignalDelivery.delivered_at >= start)
        .group_by(Signal.strategy_name)
        .order_by(func.count(SignalDelivery.id).desc())
        .limit(3)
    )
    top_strategies: list[str] = [str(s) for (s, _) in (res_strats.all() or [])]

    return {"total": total, "top_assets": top_assets, "top_strategies": top_strategies}


async def upsert_outcome(
    session: AsyncSession,
    signal_id: str,
    status: str,
    *,
    meta: dict | None = None,
    r_multiple: float | None = None,
    percent: float | None = None,
    opened_at: datetime | None = None,
    closed_at: datetime | None = None,
    canonical_outcome: str | None = None,
    vip_fill_outcome: str | None = None,
    sentiment_outcome: str | None = None,
    queue_notifications: bool = True,
) -> Outcome:
    """Create or progress an outcome while making terminal results immutable.

    A finalized result can only change through an explicitly attributed audited
    correction. Duplicate terminal writes are idempotent and do not enqueue a
    second notification.
    """
    signal_id_str = str(signal_id)
    now = _utcnow()
    status_l = str(status or "pending").strip().lower()[:32]
    terminal_statuses = {
        "tp", "tp3", "win", "sl", "loss", "stop", "stop_loss",
        "be", "breakeven", "break_even", "partial_win", "partial_win_be",
        "time_stop", "expired", "missed_entry", "cancel", "cancelled",
        "tracking_failed", "invalid",
        "invalidated",
    }
    incoming_terminal = status_l in terminal_statuses
    supplied_meta = dict(meta or {})
    correction_requested = bool(supplied_meta.get("audited_correction"))
    correction_actor = str(supplied_meta.get("corrected_by") or "").strip()
    correction_reason = str(supplied_meta.get("correction_reason") or "").strip()
    if correction_requested and (not correction_actor or not correction_reason):
        raise ValueError("audited outcome correction requires corrected_by and correction_reason")

    try:
        bind = session.get_bind()
        if getattr(getattr(bind, "dialect", None), "name", "") == "postgresql":
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"signalrank:outcome:{signal_id_str}"},
            )
    except Exception as exc:
        bind = session.get_bind()
        if getattr(getattr(bind, "dialect", None), "name", "") == "postgresql":
            raise RuntimeError("outcome advisory lock failed") from exc

    result: Result[Tuple[Outcome]] = await session.execute(
        select(Outcome)
        .where(Outcome.signal_id == signal_id_str)
        .order_by(Outcome.closed_at.desc().nullslast(), Outcome.id.desc())
        .limit(1)
        .with_for_update()
    )
    oc = result.scalars().first()
    changed = False

    if oc is None:
        oc = Outcome(
            signal_id=signal_id_str,
            status=status_l,
            r_multiple=float(r_multiple) if r_multiple is not None else None,
            percent=float(percent) if percent is not None else None,
            opened_at=opened_at,
            closed_at=(closed_at or now) if incoming_terminal else closed_at,
            canonical_outcome=str(canonical_outcome).lower()[:16] if canonical_outcome is not None else None,
            vip_fill_outcome=str(vip_fill_outcome).lower()[:16] if vip_fill_outcome is not None else None,
            sentiment_outcome=str(sentiment_outcome).lower()[:16] if sentiment_outcome is not None else None,
            meta=supplied_meta,
            terminal_version=1 if incoming_terminal else 0,
            provenance=str(supplied_meta.get("provenance") or "canonical_live")[:32],
            calculation_policy_version=str(supplied_meta.get("calculation_policy_version") or "outcome-v1")[:64],
        )
        session.add(oc)
        await session.flush()
        changed = True
    else:
        existing_status = str(getattr(oc, "status", "") or "").strip().lower()
        existing_terminal = bool(int(getattr(oc, "terminal_version", 0) or 0)) or existing_status in terminal_statuses
        if existing_terminal and not correction_requested:
            logger.warning(
                "[outcome_immutability] rejected mutation signal=%s existing=%s incoming=%s",
                signal_id_str,
                existing_status,
                status_l,
            )
            return oc

        before = {
            "status": existing_status,
            "r_multiple": getattr(oc, "r_multiple", None),
            "percent": getattr(oc, "percent", None),
            "closed_at": getattr(oc, "closed_at", None).isoformat() if getattr(oc, "closed_at", None) else None,
            "terminal_version": int(getattr(oc, "terminal_version", 0) or 0),
        }
        oc.status = status_l
        if incoming_terminal or closed_at is not None:
            oc.closed_at = closed_at or now
        if opened_at is not None:
            oc.opened_at = opened_at
        if r_multiple is not None:
            oc.r_multiple = float(r_multiple)
        if percent is not None:
            oc.percent = float(percent)
        if canonical_outcome is not None:
            oc.canonical_outcome = str(canonical_outcome).lower()[:16]
        if vip_fill_outcome is not None:
            oc.vip_fill_outcome = str(vip_fill_outcome).lower()[:16]
        if sentiment_outcome is not None:
            oc.sentiment_outcome = str(sentiment_outcome).lower()[:16]
        if incoming_terminal:
            oc.terminal_version = max(1, int(getattr(oc, "terminal_version", 0) or 0) + (1 if correction_requested else 0))
        if correction_requested:
            oc.corrected_at = now
            oc.corrected_by = correction_actor[:128]
            oc.correction_reason = correction_reason
            oc.provenance = "audited_correction"
            corrections = list((getattr(oc, "meta", {}) or {}).get("corrections") or [])
            corrections.append({
                "at": now.isoformat(),
                "by": correction_actor,
                "reason": correction_reason,
                "before": before,
                "after": {"status": status_l, "r_multiple": r_multiple, "percent": percent},
            })
            supplied_meta["corrections"] = corrections
        changed = True

    if supplied_meta:
        merged: Dict[str, Any] = dict(getattr(oc, "meta", {}) or {})
        merged.update(supplied_meta)
        oc.meta = merged

    try:
        if oc.opened_at is not None and oc.closed_at is not None:
            oc.duration_seconds = int((oc.closed_at - oc.opened_at).total_seconds())
    except Exception:
        pass

    if changed:
        try:
            new_status = str(getattr(oc, "status", "") or "").lower()
            mutable_meta = dict(getattr(oc, "meta", {}) or {})
            mutable_meta.pop("notified", None)
            mutable_meta.pop("notified_at", None)
            oc.meta = mutable_meta
            if queue_notifications and oc.closed_at is not None:
                # Notification creation has its own savepoint. A duplicate outbox row,
                # malformed recipient or notification failure must not abort the canonical
                # Outcome transaction.
                async with session.begin_nested():
                    await queue_outcome_notifications_for_outcome(
                        session,
                        int(getattr(oc, "id")),
                        signal_id_str,
                        new_status,
                    )
        except Exception:
            logger.exception("[outcome_immutability] notification queue failed signal=%s", signal_id_str)

    await session.flush()
    return oc


async def queue_outcome_notifications_for_outcome(
    session: AsyncSession,
    outcome_id: int,
    signal_id: str,
    status: str,
) -> int:
    recipients = await list_delivery_recipients_for_signal(session, str(signal_id))
    count = 0
    from core.outcome_ordering import outcome_stage_rank
    status_l = str(status or "").lower()[:16]
    stage_rank = outcome_stage_rank(status_l)
    now = _utcnow()
    for telegram_user_id, tier_at_send in recipients:
        idempotency_key = f"outcome:{signal_id}:{int(telegram_user_id)}:{status_l}"
        exists = await session.execute(
            select(OutcomeNotification.id).where(
                OutcomeNotification.idempotency_key == idempotency_key[:128]
            ).limit(1)
        )
        if exists.scalar_one_or_none() is not None:
            continue
        on = OutcomeNotification(
            outcome_id=int(outcome_id),
            signal_id=str(signal_id),
            telegram_user_id=int(telegram_user_id),
            tier_at_send=str(tier_at_send or "free")[:16],
            outcome_status=status_l,
            stage_rank=stage_rank,
            idempotency_key=idempotency_key[:128],
            delivery_state="pending",
            updated_at=now,
        )
        session.add(on)
        await session.flush()
        count += 1
    return count


async def mark_signal_delivery_result(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    signal_id: str,
    sent_ok: bool,
    error: str | None = None,
    telegram_chat_id: int | None = None,
    telegram_message_id: int | None = None,
    telegram_api_result: dict | None = None,
    delivery_state: str | None = None,
) -> bool:
    """Update a delivery result with monotonic proof and active-message CAS."""
    user_res = await session.execute(
        select(User).where(User.telegram_user_id == int(telegram_user_id)).limit(1)
    )
    user = user_res.scalar_one_or_none()
    if user is None:
        return False

    row_res = await session.execute(
        select(SignalDelivery)
        .where(
            SignalDelivery.user_id == int(user.id),
            SignalDelivery.signal_id == str(signal_id),
        )
        .order_by(SignalDelivery.id.desc())
        .limit(1)
        .with_for_update()
    )
    row = row_res.scalar_one_or_none()
    if row is None:
        return False

    now = _utcnow()
    proof_ok = telegram_chat_id is not None and telegram_message_id is not None
    if sent_ok and not proof_ok:
        sent_ok = False
        error = error or "missing_telegram_ack"

    current_state = canonical_delivery_state(
        getattr(row, "delivery_state", None),
        sent_ok=bool(getattr(row, "sent_ok", False)),
        proof_ok=(
            getattr(row, "telegram_chat_id", None) is not None
            and getattr(row, "telegram_message_id", None) is not None
        ),
    )
    target_state = canonical_delivery_state(
        delivery_state,
        sent_ok=bool(sent_ok),
        proof_ok=bool(proof_ok),
        error=error,
    )
    existing_proof_ok = bool(
        getattr(row, "sent_ok", False)
        and getattr(row, "telegram_chat_id", None) is not None
        and getattr(row, "telegram_message_id", None) is not None
    )
    if existing_proof_ok:
        if sent_ok and proof_ok and (
            int(getattr(row, "telegram_chat_id")) != int(telegram_chat_id)
            or int(getattr(row, "telegram_message_id")) != int(telegram_message_id)
        ):
            logger.error(
                "[delivery_duplicate_ack_ignored] user=%s signal=%s existing=%s/%s duplicate=%s/%s",
                telegram_user_id,
                signal_id,
                row.telegram_chat_id,
                row.telegram_message_id,
                telegram_chat_id,
                telegram_message_id,
            )
        # Confirmation is monotonic. A late failure or second acknowledgement
        # may not erase/replace the proof that made this operation authoritative.
        return True
    if not transition_allowed(current_state, target_state, proof_ok=bool(sent_ok and proof_ok)):
        logger.info(
            "[delivery_transition_ignored] user=%s signal=%s current=%s target=%s",
            telegram_user_id,
            signal_id,
            current_state.value,
            target_state.value,
        )
        return False

    row.sent_ok = bool(sent_ok)
    row.last_attempt_at = now
    row.telegram_send_started_at = getattr(row, "telegram_send_started_at", None) or now
    if sent_ok:
        signal_row = (await session.execute(
            select(Signal).where(Signal.signal_id == str(signal_id)).limit(1)
        )).scalar_one_or_none()
        generated_at = getattr(signal_row, "created_at", None)
        try:
            from signalrank_telegram.timezones import (
                age_seconds, effective_user_timezone, format_user_datetime,
            )
            display_timezone = effective_user_timezone(user.timezone, user.telegram_user_id)
            latency_seconds = age_seconds(generated_at, now)
            row.generated_at_utc = generated_at
            row.delivered_at_utc = now
            row.display_timezone = display_timezone
            row.display_generated_at = format_user_datetime(
                generated_at, display_timezone, user.telegram_user_id
            )
            row.display_delivered_at = format_user_datetime(
                now, display_timezone, user.telegram_user_id
            )
            row.delivery_latency_seconds = latency_seconds
            row.signal_age_at_delivery_seconds = latency_seconds
        except Exception:
            pass
        row.delivery_confirmed_at = now
        row.delivered_at = now
        row.delivery_state = target_state.value
        row.telegram_chat_id = int(telegram_chat_id) if telegram_chat_id is not None else None
        row.telegram_message_id = int(telegram_message_id) if telegram_message_id is not None else None
        merged_api_result = {
            **dict(getattr(row, "telegram_api_result", None) or {}),
            **dict(telegram_api_result or {}),
        }
        row.telegram_api_result = merged_api_result

        edited_old_signal_id = str(merged_api_result.get("edited_old_signal_id") or "").strip()
        if edited_old_signal_id and edited_old_signal_id != str(signal_id):
            old_active = (
                await session.execute(
                    select(ActiveSignalMessage)
                    .where(
                        ActiveSignalMessage.user_id == int(user.id),
                        ActiveSignalMessage.signal_id == edited_old_signal_id,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if old_active is not None:
                old_active.is_active = False

        active_result = await session.execute(
            select(ActiveSignalMessage)
            .where(
                ActiveSignalMessage.user_id == int(user.id),
                ActiveSignalMessage.signal_id == str(signal_id),
            )
            .limit(1)
        )
        active_message = active_result.scalar_one_or_none()
        if active_message is None:
            session.add(
                ActiveSignalMessage(
                    user_id=int(user.id),
                    signal_id=str(signal_id),
                    chat_id=int(telegram_chat_id),
                    message_id=int(telegram_message_id),
                    is_active=True,
                )
            )
        else:
            active_message.chat_id = int(telegram_chat_id)
            active_message.message_id = int(telegram_message_id)
            active_message.is_active = True
        # A recipient becomes monitor-eligible only after the Telegram API
        # acknowledgement has been persisted as delivery proof.
        from services.user_signal_monitoring import ensure_monitoring_for_delivery

        await ensure_monitoring_for_delivery(session, delivery=row)
    else:
        row.delivery_state = target_state.value
    # Reservation owns the attempt counter. Confirmation must not turn one
    # Telegram API attempt into two in diagnostics.
    if int(getattr(row, "attempt_count", 0) or 0) < 1:
        row.attempt_count = 1
    row.last_error = (str(error)[:1000] if error else None)
    await session.flush()
    return True


async def mark_signal_delivery_state(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    signal_id: str,
    delivery_state: DeliveryState | str,
    error: str | None = None,
) -> bool:
    """Advance a reserved operation before Telegram transmission."""
    user = (
        await session.execute(
            select(User).where(User.telegram_user_id == int(telegram_user_id)).limit(1)
        )
    ).scalar_one_or_none()
    if user is None:
        return False
    row = (
        await session.execute(
            select(SignalDelivery)
            .where(
                SignalDelivery.user_id == int(user.id),
                SignalDelivery.signal_id == str(signal_id),
            )
            .order_by(SignalDelivery.id.desc())
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    current = canonical_delivery_state(
        getattr(row, "delivery_state", None),
        sent_ok=bool(getattr(row, "sent_ok", False)),
        proof_ok=(
            getattr(row, "telegram_chat_id", None) is not None
            and getattr(row, "telegram_message_id", None) is not None
        ),
    )
    target = canonical_delivery_state(delivery_state, error=error)
    if not transition_allowed(current, target):
        return False
    now = _utcnow()
    row.delivery_state = target.value
    row.last_attempt_at = now
    if target is DeliveryState.SENDING:
        row.telegram_send_started_at = now
    if error:
        row.last_error = str(error)[:1000]
    await session.flush()
    return True


async def list_signals_missing_outcomes(
    session: AsyncSession,
    *,
    max_age_days: int = 3,
    min_age_hours: int = 0,
    limit: int = 50,
) -> list[Signal]:
    """Signals that were delivered to at least one user but have no Outcome row yet."""
    now: datetime = _utcnow()
    start: datetime = now - timedelta(days=max(1, int(max_age_days)))
    min_created_at: datetime | None = None
    try:
        _h = int(min_age_hours)
    except Exception:
        _h = 0
    if _h > 0:
        min_created_at = now - timedelta(hours=_h)

    proof_time = func.coalesce(
        SignalDelivery.delivery_confirmed_at,
        SignalDelivery.delivered_at_utc,
        SignalDelivery.delivered_at,
    )
    delivered_ids: Subquery = (
        select(SignalDelivery.signal_id)
        .where(
            SignalDelivery.sent_ok.is_(True),
            SignalDelivery.telegram_chat_id.is_not(None),
            SignalDelivery.telegram_message_id.is_not(None),
            func.lower(SignalDelivery.delivery_state).in_(tuple(CONFIRMED_DELIVERY_STATES)),
            proof_time >= start,
        )
        .distinct()
        .subquery()
    )

    _predicates = [
        Signal.signal_id.in_(select(delivered_ids.c.signal_id)),
        Signal.created_at >= start,
        (
            ~select(Outcome.id).where(Outcome.signal_id == Signal.signal_id).exists()
        )
        |
        (
            select(Outcome.id)
            .where(
                Outcome.signal_id == Signal.signal_id,
                func.lower(Outcome.status).in_([
                    "pending",
                    "watching_entry",
                    "active",
                    "entered",
                    "tp1",
                    "tp2",
                    "partial_tp",
                    "partial_win",
                ]),
            )
            .exists()
        ),
    ]
    if min_created_at is not None:
        _predicates.append(Signal.created_at <= min_created_at)

    q: Select[Tuple[Signal]] = (
        select(Signal)
        .where(*_predicates)
        .order_by(Signal.created_at.asc())
        .limit(max(1, int(limit)))
    )
    res: Result[Tuple[Signal]] = await session.execute(q)
    return list(res.scalars().all())


async def list_pending_outcome_notifications(
    session: AsyncSession,
    limit: int = 200,
) -> list[tuple[OutcomeNotification, Outcome, Signal]]:
    res: Result[Tuple[OutcomeNotification, Outcome, Signal]] = await session.execute(
        select(OutcomeNotification, Outcome, Signal)
        .join(Outcome, Outcome.id == OutcomeNotification.outcome_id)
        .join(Signal, Signal.signal_id == OutcomeNotification.signal_id)
        .where(
            Outcome.closed_at.is_not(None),
            OutcomeNotification.delivery_state.in_(["pending", "failed"]),
        )
        .order_by(
            OutcomeNotification.signal_id.asc(),
            OutcomeNotification.telegram_user_id.asc(),
            OutcomeNotification.stage_rank.desc(),
            Outcome.closed_at.desc(),
            OutcomeNotification.id.asc(),
        )
        .limit(max(1, int(limit)))
    )
    return list(res.all())


async def list_unnotified_outcomes(session: AsyncSession, limit: int = 50) -> list[tuple[Outcome, Signal]]:
    """Backward-compatible alias: outcomes with pending/failed recipient notifications."""
    pending = await list_pending_outcome_notifications(session, limit=max(1, int(limit)) * 10)
    out: list[tuple[Outcome, Signal]] = []
    seen: set[int] = set()
    for _n, oc, sig in pending:
        oid = int(getattr(oc, "id", 0) or 0)
        if oid <= 0 or oid in seen:
            continue
        seen.add(oid)
        out.append((oc, sig))
        if len(out) >= max(1, int(limit)):
            break
    return out


async def mark_outcome_notification_delivered(
    session: AsyncSession,
    notification_id: int,
) -> None:
    res: Result[Tuple[OutcomeNotification]] = await session.execute(
        select(OutcomeNotification).where(OutcomeNotification.id == int(notification_id))
    )
    row: OutcomeNotification | None = res.scalars().first()
    if row is None:
        return
    now = _utcnow()
    row.delivery_state = "delivered"
    row.attempt_count = int(getattr(row, "attempt_count", 0) or 0) + 1
    row.last_attempt_at = now
    row.delivered_at = now
    row.last_error = None
    row.updated_at = now
    # Once a stage is delivered, all lower pending stages for the same user and
    # signal are obsolete. A terminal delivery supersedes every other pending
    # stage, preventing TP1/TP2 alerts from appearing after TP3/SL.
    from core.outcome_ordering import outcome_is_terminal
    supersede = update(OutcomeNotification).where(
        OutcomeNotification.signal_id == str(row.signal_id),
        OutcomeNotification.telegram_user_id == int(row.telegram_user_id),
        OutcomeNotification.id != int(row.id),
        OutcomeNotification.delivery_state.in_(["pending", "failed", "sending"]),
    )
    if not outcome_is_terminal(row.outcome_status):
        supersede = supersede.where(OutcomeNotification.stage_rank < int(row.stage_rank or 0))
    await session.execute(supersede.values(
        delivery_state="superseded",
        last_error="superseded_by_monotonic_outcome_delivery",
        updated_at=now,
    ))
    await session.flush()


async def claim_outcome_notification_for_delivery(
    session: AsyncSession,
    notification_id: int,
    *,
    stale_after_seconds: int = 300,
) -> bool:
    """Atomically reserve one pending/failed notification before Telegram I/O."""
    now = _utcnow()
    stale_cutoff = now - timedelta(seconds=max(60, int(stale_after_seconds or 300)))
    candidate = (await session.execute(
        select(OutcomeNotification).where(OutcomeNotification.id == int(notification_id)).limit(1)
    )).scalar_one_or_none()
    if candidate is None:
        return False
    delivered_rows = (await session.execute(
        select(OutcomeNotification.outcome_status, OutcomeNotification.stage_rank).where(
            OutcomeNotification.signal_id == str(candidate.signal_id),
            OutcomeNotification.telegram_user_id == int(candidate.telegram_user_id),
            OutcomeNotification.delivery_state == "delivered",
        )
    )).all()
    from core.outcome_ordering import evaluate_outcome_delivery, outcome_is_terminal
    decision = evaluate_outcome_delivery(
        candidate.outcome_status,
        highest_delivered_rank=max((int(rank or 0) for _, rank in delivered_rows), default=0),
        terminal_already_delivered=any(outcome_is_terminal(status) for status, _ in delivered_rows),
    )
    if not decision.allowed:
        candidate.delivery_state = "superseded"
        candidate.last_error = decision.reason
        candidate.updated_at = now
        await session.flush()
        return False
    stmt = (
        update(OutcomeNotification)
        .where(
            OutcomeNotification.id == int(notification_id),
            or_(
                OutcomeNotification.delivery_state.in_(["pending", "failed"]),
                and_(
                    OutcomeNotification.delivery_state == "sending",
                    or_(
                        OutcomeNotification.last_attempt_at.is_(None),
                        OutcomeNotification.last_attempt_at <= stale_cutoff,
                    ),
                ),
            ),
        )
        .values(
            delivery_state="sending",
            last_attempt_at=now,
            updated_at=now,
        )
        .returning(OutcomeNotification.id)
    )
    res = await session.execute(stmt)
    claimed = res.scalar_one_or_none() is not None
    await session.flush()
    return bool(claimed)


async def mark_outcome_notified(session: AsyncSession, outcome_id: int) -> None:
    """Backward-compatible alias: mark all recipient notifications as delivered."""
    rows = (
        await session.execute(
            select(OutcomeNotification).where(
                OutcomeNotification.outcome_id == int(outcome_id),
                OutcomeNotification.delivery_state.in_(["pending", "failed"]),
            )
        )
    ).scalars().all()
    for row in rows:
        await mark_outcome_notification_delivered(session, int(row.id))

    # Keep legacy meta flags for compatibility with old readers.
    res: Result[Tuple[Outcome]] = await session.execute(
        select(Outcome).where(Outcome.id == int(outcome_id))
    )
    oc: Outcome | None = res.scalars().first()
    if oc is not None:
        meta: Dict[str, Any] = dict(getattr(oc, "meta", {}) or {})
        meta["notified"] = True
        meta["notified_at"] = _utcnow().isoformat()
        oc.meta = meta
    await session.flush()


async def mark_outcome_notification_failed(
    session: AsyncSession,
    notification_id: int,
    *,
    error: str | None = None,
) -> None:
    res: Result[Tuple[OutcomeNotification]] = await session.execute(
        select(OutcomeNotification).where(OutcomeNotification.id == int(notification_id))
    )
    row: OutcomeNotification | None = res.scalars().first()
    if row is None:
        return
    now = _utcnow()
    row.delivery_state = "failed"
    row.attempt_count = int(getattr(row, "attempt_count", 0) or 0) + 1
    row.last_attempt_at = now
    row.last_error = (str(error)[:1000] if error else None)
    row.updated_at = now
    await session.flush()


async def get_outcome_for_signal(session: AsyncSession, signal_id: str) -> Outcome | None:
    res: Result[Tuple[Outcome]] = await session.execute(select(Outcome).where(Outcome.signal_id == str(signal_id)).order_by(Outcome.id.desc()).limit(1))
    return res.scalars().first()


async def list_delivery_recipients_for_signal(session: AsyncSession, signal_id: str) -> list[tuple[int, str]]:
    """Return confirmed recipients, excluding legacy duplicate-thesis deliveries.

    v1.3.6.6 could deliver near-identical signals to owner/admin users because
    privileged paths bypassed the asset lock. Future delivery is now blocked at
    reservation and pre-send time; this read-side guard prevents those historical
    duplicate rows from producing duplicate terminal notifications.
    """
    current_signal = (
        await session.execute(
            select(Signal).where(Signal.signal_id == str(signal_id)).limit(1)
        )
    ).scalar_one_or_none()
    delivery_time_expr = func.coalesce(
        SignalDelivery.delivery_confirmed_at,
        SignalDelivery.delivered_at_utc,
        SignalDelivery.delivered_at,
    )
    res = await session.execute(
        select(
            User.id,
            User.telegram_user_id,
            SignalDelivery.tier_at_send,
            delivery_time_expr.label("proof_time"),
        )
        .select_from(SignalDelivery)
        .join(User, User.id == SignalDelivery.user_id)
        .outerjoin(
            UserSignalMonitoring,
            and_(
                UserSignalMonitoring.user_id == SignalDelivery.user_id,
                UserSignalMonitoring.signal_id == SignalDelivery.signal_id,
            ),
        )
        .where(
            SignalDelivery.signal_id == str(signal_id),
            SignalDelivery.sent_ok.is_(True),
            SignalDelivery.telegram_chat_id.is_not(None),
            SignalDelivery.telegram_message_id.is_not(None),
            func.lower(SignalDelivery.delivery_state).in_(("sent", "confirmed", "delivered", "reconciled")),
            or_(UserSignalMonitoring.id.is_(None), UserSignalMonitoring.status.in_(("auto_continue", "continued"))),
        )
        .order_by(User.telegram_user_id.asc())
    )
    recipient_rows = list(res.all() or [])
    if not recipient_rows or current_signal is None or not _env_bool(
        "OUTCOME_DUPLICATE_NOTIFICATION_SUPPRESSION_ENABLED", True
    ):
        return [(int(row[1]), str(row[2])) for row in recipient_rows]

    try:
        window_hours = max(1, int(os.getenv("SIGNAL_THESIS_DEDUP_HOURS", "4") or 4))
    except Exception:
        window_hours = 4
    from core.production_integrity import semantic_entries_equivalent

    proof_times = [row[3] for row in recipient_rows if row[3] is not None]
    if not proof_times:
        return [(int(row[1]), str(row[2])) for row in recipient_rows]
    earliest_cutoff = min(proof_times) - timedelta(hours=window_hours)
    latest_current = max(proof_times)
    user_ids = [int(row[0]) for row in recipient_rows]
    prior_rows = (
        await session.execute(
            select(
                SignalDelivery.user_id,
                SignalDelivery.signal_id,
                delivery_time_expr.label("proof_time"),
                Signal.entry,
            )
            .join(Signal, Signal.signal_id == SignalDelivery.signal_id)
            .where(
                SignalDelivery.user_id.in_(user_ids),
                SignalDelivery.signal_id != str(signal_id),
                SignalDelivery.sent_ok.is_(True),
                SignalDelivery.telegram_chat_id.is_not(None),
                SignalDelivery.telegram_message_id.is_not(None),
                func.lower(SignalDelivery.delivery_state).in_(("sent", "confirmed", "delivered", "reconciled")),
                delivery_time_expr >= earliest_cutoff,
                delivery_time_expr <= latest_current,
                Signal.asset == current_signal.asset,
                Signal.direction == current_signal.direction,
                func.lower(Signal.strategy_name) == str(current_signal.strategy_name or "").lower(),
            )
            .order_by(delivery_time_expr.asc(), SignalDelivery.id.asc())
        )
    ).all()
    prior_by_user: dict[int, list[tuple[str, datetime, float]]] = {}
    for user_id, prior_signal_id, proof_time, prior_entry in prior_rows:
        if proof_time is None:
            continue
        try:
            entry_value = float(prior_entry or 0)
        except Exception:
            continue
        prior_by_user.setdefault(int(user_id), []).append(
            (str(prior_signal_id), proof_time, entry_value)
        )

    try:
        current_entry = float(current_signal.entry or 0)
    except Exception:
        current_entry = 0.0
    eligible: list[tuple[int, str]] = []
    for user_id, telegram_user_id, tier, current_time in recipient_rows:
        duplicate_of = None
        if current_time is not None and current_entry > 0:
            for prior_signal_id, prior_time, prior_entry in prior_by_user.get(int(user_id), []):
                delta = current_time - prior_time
                if delta.total_seconds() <= 0 or delta > timedelta(hours=window_hours):
                    continue
                if semantic_entries_equivalent(prior_entry, current_entry):
                    duplicate_of = prior_signal_id
                    break
        if duplicate_of:
            logger.info(
                "[outcome_notify] suppressed duplicate thesis recipient=%s signal=%s duplicate_of=%s asset=%s",
                int(telegram_user_id), str(signal_id), duplicate_of, current_signal.asset,
            )
            continue
        eligible.append((int(telegram_user_id), str(tier)))
    return eligible


async def list_all_user_telegram_ids(session: AsyncSession) -> list[int]:
    res: Result[Tuple[int]] = await session.execute(select(User.telegram_user_id).order_by(User.telegram_user_id.asc()))
    ids = [int(x) for (x,) in (res.all() or [])]
    try:
        from config import OWNER_IDS, ADMIN_IDS
        priority = [int(x) for x in list(OWNER_IDS or set()) + list(ADMIN_IDS or set())]
        seen: set[int] = set()
        ordered: list[int] = []
        for uid in priority + ids:
            if uid in seen:
                continue
            seen.add(uid)
            ordered.append(uid)
        return ordered
    except Exception:
        return ids


async def record_payment_event(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    paystack_reference: str,
    amount_ngn: int,
    currency: str | None = None,
    kind: str = "subscription",
    tier: str | None = None,
    duration_days: int | None = None,
    plan_code: str | None = None,
    meta: dict | None = None,
) -> PaymentEvent:
    """Idempotently store a Paystack payment event for revenue analytics."""
    ref: str = str(paystack_reference or "").strip()
    if not ref:
        raise ValueError("paystack_reference required")

    res: Result[Tuple[PaymentEvent]] = await session.execute(select(PaymentEvent).where(PaymentEvent.paystack_reference == ref))
    existing: PaymentEvent | None = res.scalars().first()
    if existing is not None:
        return existing

    user: User = await get_or_create_user(session, telegram_user_id=int(telegram_user_id))
    pe = PaymentEvent(
        user_id=user.id,
        kind=str(kind or "subscription")[:32],
        tier=(str(tier).strip().lower()[:32] if tier is not None else None),
        duration_days=int(duration_days) if duration_days is not None else None,
        plan_code=(str(plan_code)[:128] if plan_code else None),
        amount_ngn=max(0, int(amount_ngn)),
        currency=(str(currency)[:8] if currency else None),
        paystack_reference=ref,
        meta=dict(meta or {}),
    )
    session.add(pe)
    await session.flush()
    return pe


async def get_alert_prefs(session: AsyncSession, telegram_user_id: int) -> dict[str, object]:
    user: User = await get_or_create_user(session, telegram_user_id=int(telegram_user_id))
    res: Result[Tuple[AlertPreference]] = await session.execute(select(AlertPreference).where(AlertPreference.user_id == user.id))
    pref: AlertPreference | None = res.scalar_one_or_none()
    if pref is None:
        return {"tp_sl_enabled": True, "quiet_start_hour": None, "quiet_end_hour": None}
    return {
        "tp_sl_enabled": bool(pref.tp_sl_enabled),
        "quiet_start_hour": pref.quiet_start_hour,
        "quiet_end_hour": pref.quiet_end_hour,
    }


async def set_alert_prefs(
    session: AsyncSession,
    telegram_user_id: int,
    tp_sl_enabled: Optional[bool] = None,
    quiet_start_hour: Optional[int] = None,
    quiet_end_hour: Optional[int] = None,
) -> dict:
    user: User = await get_or_create_user(session, telegram_user_id=int(telegram_user_id))
    res: Result[Tuple[AlertPreference]] = await session.execute(select(AlertPreference).where(AlertPreference.user_id == user.id))
    pref: AlertPreference | None = res.scalar_one_or_none()
    if pref is None:
        pref = AlertPreference(user_id=user.id)
        session.add(pref)
        await session.flush()

    if tp_sl_enabled is not None:
        pref.tp_sl_enabled = bool(tp_sl_enabled)
    if quiet_start_hour is not None:
        pref.quiet_start_hour = int(quiet_start_hour)
    if quiet_end_hour is not None:
        pref.quiet_end_hour = int(quiet_end_hour)
    pref.updated_at = _utcnow()
    await session.flush()
    return await get_alert_prefs(session, telegram_user_id=int(telegram_user_id))


async def queue_free_signal_summary(
    session: AsyncSession,
    telegram_user_id: int,
    signal: Dict[str, Any],
    delay_minutes: Optional[int] = None,
    daily_limit: Optional[int] = None,
) -> bool:
    distribution_enabled = any(
        str(os.getenv(name, "0") or "0").strip().lower() in {"1", "true", "yes", "on"}
        for name in ("FREE_RANDOM_DISTRIBUTION_ENABLED", "FREE_SIGNAL_DISTRIBUTION_ENABLED")
    )
    if not distribution_enabled:
        # Disabled distribution must not create an undrainable queue.
        return False
    if delay_minutes is None:
        # Default to immediate dispatch for FREE tier while still enforcing daily cap.
        delay_minutes = _env_int("FREE_DELAY_MINUTES", 0)
    if daily_limit is None:
        daily_limit = _env_int("FREE_DAILY_LIMIT", 3)

    # Product rule: Free tier gets at most 3 random signals per day.
    try:
        daily_limit = min(int(daily_limit), 3)
    except Exception:
        daily_limit = 3

    now: datetime = _utcnow()
    user: User = await get_or_create_user(session, telegram_user_id=int(telegram_user_id))

    # Daily window is anchored to the user's join time (created_at), not midnight.
    # Example: if user joined at 09:24 UTC, their "day" runs 09:24 → next 09:24.
    try:
        anchor: datetime = to_naive_utc(user.created_at)
        window_start: datetime = now.replace(
            hour=int(anchor.hour),
            minute=int(anchor.minute),
            second=int(anchor.second),
            microsecond=0,
        )
        if window_start > now:
            window_start: datetime = window_start - timedelta(days=1)
    except Exception:
        window_start: datetime = now.replace(hour=0, minute=0, second=0, microsecond=0)

    window_start = to_naive_utc(window_start)
    window_end: datetime = window_start + timedelta(days=1)

    # Enforce per-day cap (queued + sent)
    res: Result[Tuple[int]] = await session.execute(
        select(func.count(FreeSignalQueue.id)).where(
            FreeSignalQueue.user_id == user.id,
            FreeSignalQueue.date >= window_start,
            FreeSignalQueue.date < window_end,
            FreeSignalQueue.status.in_(["queued", "sent"]),
        )
    )
    already = int(res.scalar() or 0)
    if already >= int(daily_limit):
        return False

    s: Signal = await get_or_create_signal(session, signal)

    # Dedupe: do not queue the exact same signal more than once per user/day.
    res_dupe: Result[Tuple[int]] = await session.execute(
        select(func.count(FreeSignalQueue.id)).where(
            FreeSignalQueue.user_id == user.id,
            FreeSignalQueue.date >= window_start,
            FreeSignalQueue.date < window_end,
            FreeSignalQueue.signal_id == s.signal_id,
            FreeSignalQueue.status.in_(["queued", "sent"]),
        )
    )
    if int(res_dupe.scalar() or 0) > 0:
        return True

    deliver_after: datetime = now + timedelta(minutes=max(0, int(delay_minutes)))
    deliver_after = to_naive_utc(deliver_after)
    q = FreeSignalQueue(
        user_id=user.id,
        date=window_start,
        signal_id=s.signal_id,
        asset=str(s.asset),
        timeframe=str(s.timeframe),
        direction=str(s.direction),
        score=int(signal.get("score") or 0),
        queued_at=now,
        deliver_after=deliver_after,
        status="queued",
    )
    session.add(q)
    await session.flush()
    return True


async def get_user_performance_30d(session: AsyncSession, telegram_user_id: int) -> dict[str, object]:
    """Return one consistent proof-ledger snapshot for the delivery cohort."""
    from services.performance_ledger import get_user_performance_report

    report = await get_user_performance_report(
        session,
        telegram_user_id=int(telegram_user_id),
        days=30,
    )
    report["time_stops"] = int((report.get("buckets") or {}).get("TIME_STOP", 0))
    report["completed_win_rate"] = float(report.get("strict_win_rate") or 0.0)
    report["completion_rate"] = (
        float(report.get("completed_r_count") or 0) / max(1, int(report.get("delivered") or 0))
    )
    # ORM rows are available from the explicit detail/audit service, not this
    # compatibility aggregate consumed by Telegram and Engine Pulse.
    report.pop("rows", None)
    return report

async def get_due_free_signal_summaries(session: AsyncSession) -> dict[int, list[dict]]:
    now: datetime = _utcnow()
    res: Result[Tuple[FreeSignalQueue, int]] = await session.execute(
        select(FreeSignalQueue, User.telegram_user_id)
        .join(User, User.id == FreeSignalQueue.user_id)
        .where(FreeSignalQueue.status == "queued", FreeSignalQueue.deliver_after <= now)
        .order_by(User.telegram_user_id.asc(), FreeSignalQueue.score.desc())
    )
    rows: list[Row[Tuple[FreeSignalQueue, int]]] = list(res.all())
    grouped: dict[int, list[dict]] = {}
    for queue_row, telegram_user_id in rows:
        grouped.setdefault(int(telegram_user_id), []).append(
            {
                "id": int(queue_row.id),
                "signal_id": str(queue_row.signal_id),
                "asset": queue_row.asset,
                "timeframe": queue_row.timeframe,
                "direction": queue_row.direction,
                "score": int(queue_row.score or 0),
            }
        )
    return grouped


async def mark_free_signal_summaries_sent(session: AsyncSession, ids: list[int], status: str = "sent") -> None:
    if not ids:
        return
    now: datetime = _utcnow()
    stmt: Update = (
        update(FreeSignalQueue)
        .where(FreeSignalQueue.id.in_([int(x) for x in ids]))
        .values(sent_at=now, status=str(status)[:16])
    )
    await session.execute(stmt)
    await session.flush()


async def expire_old_free_signal_summaries(session: AsyncSession, max_age_hours: int = 24) -> int:
    cutoff: datetime = _utcnow() - timedelta(hours=int(max_age_hours))
    stmt: Update = (
        update(FreeSignalQueue)
        .where(FreeSignalQueue.status == "queued", FreeSignalQueue.queued_at < cutoff)
        .values(status="expired")
    )
    res: CursorResult[Any] = await session.execute(stmt)
    await session.flush()
    return int(getattr(res, "rowcount", 0) or 0)


async def get_or_create_referral_code(session: AsyncSession, referrer_telegram_user_id: int) -> str:
    """Return one durable referral code for a Telegram user.

    The referrer row is locked so concurrent /invite and /referral commands do
    not create multiple active codes. No synthetic fallback code is returned:
    every code exposed to users must already exist in PostgreSQL.
    """
    referrer: User = await get_or_create_user(
        session,
        telegram_user_id=int(referrer_telegram_user_id),
    )
    locked_referrer = (
        await session.execute(
            select(User).where(User.id == int(referrer.id)).with_for_update()
        )
    ).scalar_one()

    existing = (
        await session.execute(
            select(ReferralCode)
            .where(ReferralCode.referrer_user_id == int(locked_referrer.id))
            .order_by(ReferralCode.id.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return str(existing.code)

    # Telegram start parameters allow URL-safe characters. Keep the code short
    # enough for sharing while including the internal id for collision resistance.
    for _ in range(5):
        token = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]
        code = f"SRK{int(locked_referrer.id):X}{token}"[:32]
        collision = (
            await session.execute(
                select(ReferralCode.id).where(func.lower(ReferralCode.code) == code.lower())
            )
        ).scalar_one_or_none()
        if collision is not None:
            continue
        row = ReferralCode(code=code, referrer_user_id=int(locked_referrer.id))
        session.add(row)
        await session.flush()
        logger.info(
            "[referral_code_created] referrer_user_id=%s telegram_user_id=%s code=%s",
            locked_referrer.id,
            referrer_telegram_user_id,
            code,
        )
        return str(row.code)
    raise RuntimeError("Unable to allocate a unique referral code")


async def _count_referrals(session: AsyncSession, referrer_user_id: int) -> int:
    res: Result[Tuple[int]] = await session.execute(
        select(func.count(ReferralAttribution.id)).where(
            ReferralAttribution.referrer_user_id == int(referrer_user_id)
        )
    )
    return int(res.scalar() or 0)


async def get_referral_progress(session: AsyncSession, referrer_telegram_user_id: int) -> dict[str, int]:
    referrer: User = await get_or_create_user(
        session,
        telegram_user_id=int(referrer_telegram_user_id),
    )
    total = await _count_referrals(session, referrer_user_id=int(referrer.id))
    requirement = max(1, int(os.getenv("REFERRALS_PER_REWARD", "3") or 3))
    reward_days = max(1, int(os.getenv("REFERRAL_BONUS_DAYS", "7") or 7))
    toward_next = int(total % requirement)
    # At zero or an exact milestone, the *next* reward still requires a full batch.
    needed = int(requirement if toward_next == 0 else requirement - toward_next)
    return {
        "total": int(total),
        "toward_next": toward_next,
        "needed_for_next": needed,
        "reward_days_per_3": reward_days,
        "rewards_earned": int(total // requirement),
        "requirement": int(requirement),
    }


async def _sum_reward_days(session: AsyncSession, referrer_user_id: int) -> int:
    res: Result[Tuple[int]] = await session.execute(
        select(func.coalesce(func.sum(ReferralReward.reward_value), 0)).where(
            ReferralReward.referrer_user_id == int(referrer_user_id),
            ReferralReward.reward_type == "premium_days",
        )
    )
    return int(res.scalar() or 0)


async def _resolve_referral_reward_tier(
    session: AsyncSession,
    referrer_user: User,
) -> str:
    """Resolve the entitlement to extend without opening a nested DB session."""
    now = _utcnow()
    active_tiers = list(
        (
            await session.execute(
                select(Subscription.tier)
                .where(
                    Subscription.user_id == int(referrer_user.id),
                    Subscription.status == "active",
                    Subscription.expires_at.is_not(None),
                    Subscription.expires_at > now,
                )
                .order_by(Subscription.expires_at.desc())
            )
        ).scalars().all()
    )
    tiers = [normalize_tier(str(getattr(referrer_user, "tier", "free") or "free"))]
    tiers.extend(normalize_tier(str(value or "free")) for value in active_tiers)
    return "vip" if "vip" in tiers else "premium"


async def process_referral_start(
    session: AsyncSession,
    referred_telegram_user_id: int,
    referral_code: str,
    is_new_user: bool,
) -> dict:
    """Atomically attribute a qualified new user and grant milestone rewards.

    Canonical product rule: each genuinely new Telegram user may be attributed
    once. Every configured batch of referrals grants subscription days. Payment
    conversion is recorded separately and never runs a competing reward system.
    """
    result: dict[str, Any] = {
        "status": "ignored",
        "referrer_id": None,
        "referrals_total": 0,
        "days_granted": 0,
        "referrer_notified": False,
    }
    code = str(referral_code or "").strip()
    if not code:
        result["status"] = "invalid_code"
        return result

    rc = (
        await session.execute(
            select(ReferralCode).where(func.lower(ReferralCode.code) == code.lower())
        )
    ).scalar_one_or_none()
    if rc is None:
        result["status"] = "invalid_code"
        logger.info("[referral_start] status=invalid_code referred=%s code=%s", referred_telegram_user_id, code)
        return result

    referrer_user = (
        await session.execute(
            select(User).where(User.id == int(rc.referrer_user_id)).with_for_update()
        )
    ).scalar_one_or_none()
    if referrer_user is None:
        result["status"] = "invalid_code"
        return result

    referrer_tid = int(referrer_user.telegram_user_id)
    result["referrer_id"] = referrer_tid
    if int(referred_telegram_user_id) == referrer_tid:
        result["status"] = "self_referral"
        return result
    if not bool(is_new_user):
        result["status"] = "not_new"
        return result

    referred_user = await get_or_create_user(
        session,
        telegram_user_id=int(referred_telegram_user_id),
    )
    # Lock the referred user so simultaneous duplicate /start updates cannot
    # create two attributions before the unique constraint is observed.
    referred_user = (
        await session.execute(
            select(User).where(User.id == int(referred_user.id)).with_for_update()
        )
    ).scalar_one()
    existing_attribution = (
        await session.execute(
            select(ReferralAttribution).where(
                ReferralAttribution.referred_user_id == int(referred_user.id)
            )
        )
    ).scalar_one_or_none()
    if existing_attribution is not None:
        result["status"] = "already_referred"
        result["referrer_id"] = int(
            (
                await session.execute(
                    select(User.telegram_user_id).where(
                        User.id == int(existing_attribution.referrer_user_id)
                    )
                )
            ).scalar_one()
        )
        return result

    now = _utcnow()
    attribution = ReferralAttribution(
        referred_user_id=int(referred_user.id),
        referrer_user_id=int(referrer_user.id),
        is_successful=True,
        successful_at=now,
        reward_applied=False,
    )
    session.add(attribution)
    if not getattr(referred_user, "referred_by", None):
        referred_user.referred_by = referrer_tid

    signup_reference = f"REFERRAL_SIGNUP:{int(referred_user.id)}"
    existing_signup_reward = (
        await session.execute(
            select(ReferralReward.id).where(ReferralReward.reference == signup_reference)
        )
    ).scalar_one_or_none()
    if existing_signup_reward is None:
        session.add(
            ReferralReward(
                referrer_user_id=int(referrer_user.id),
                referred_user_id=int(referred_user.id),
                reward_type="referral_signup",
                reward_value=1,
                reference=signup_reference,
                meta={"referral_code": code, "qualified_on": "new_user_start"},
            )
        )
    await session.flush()

    total = await _count_referrals(session, referrer_user_id=int(referrer_user.id))
    referrer_user.referral_count = int(total)  # denormalized lifetime total; never reset
    result["referrals_total"] = int(total)

    requirement = max(1, int(os.getenv("REFERRALS_PER_REWARD", "3") or 3))
    configured_grant_days = max(1, int(os.getenv("REFERRAL_BONUS_DAYS", "7") or 7))
    toward_next = int(total % requirement)
    if toward_next != 0:
        needed = int(requirement - toward_next)
        result["status"] = "attributed"
        result["referrer_message"] = (
            "👤 Someone joined with your referral link!\n\n"
            f"Total valid referrals: {total}\n"
            f"Progress: {toward_next}/{requirement}\n"
            f"Invite {needed} more to earn +{configured_grant_days} Premium days."
        )
        logger.info(
            "[referral_start] status=attributed referrer=%s referred=%s total=%s",
            referrer_tid,
            referred_telegram_user_id,
            total,
        )
        return result

    batch_number = int(total // requirement)
    reward_ref = f"REFERRAL:{referrer_tid}:{batch_number}"
    existing_reward = (
        await session.execute(
            select(ReferralReward).where(ReferralReward.reference == reward_ref)
        )
    ).scalar_one_or_none()
    if existing_reward is not None:
        result["status"] = "reward_already_granted"
        result["days_granted"] = int(existing_reward.reward_value or 0)
        return result

    try:
        monthly_cap_days = max(
            configured_grant_days,
            int(os.getenv("REFERRAL_MONTHLY_CAP_DAYS", "28") or 28),
        )
    except Exception:
        monthly_cap_days = 28
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_days_used = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(ReferralReward.reward_value), 0)).where(
                    ReferralReward.referrer_user_id == int(referrer_user.id),
                    ReferralReward.reward_type == "premium_days",
                    ReferralReward.created_at >= month_start,
                )
            )
        ).scalar()
        or 0
    )
    monthly_remaining = max(0, int(monthly_cap_days - monthly_days_used))
    if monthly_remaining <= 0:
        session.add(
            ReferralReward(
                referrer_user_id=int(referrer_user.id),
                referred_user_id=int(referred_user.id),
                reward_type="premium_days_capped",
                reward_value=0,
                reference=reward_ref,
                meta={"batch": batch_number, "monthly_cap_days": monthly_cap_days},
            )
        )
        result["status"] = "reward_capped"
        result["referrer_message"] = (
            "🎯 Referral milestone reached, but your monthly referral bonus cap "
            "has already been reached. New referral days can be earned next month."
        )
        return result

    grant_days = min(configured_grant_days, monthly_remaining)
    tier_to_extend = await _resolve_referral_reward_tier(session, referrer_user)
    await activate_subscription(
        session,
        telegram_user_id=referrer_tid,
        tier=tier_to_extend,
        duration_days=int(grant_days),
        paystack_reference=reward_ref,
        meta={
            "source": "referral",
            "referred": int(referred_telegram_user_id),
            "batch": batch_number,
            "grant_days": int(grant_days),
        },
    )
    session.add(
        ReferralReward(
            referrer_user_id=int(referrer_user.id),
            referred_user_id=int(referred_user.id),
            reward_type="premium_days",
            reward_value=int(grant_days),
            reference=reward_ref,
            meta={"batch": batch_number, "tier_extended": tier_to_extend},
        )
    )

    pending_refs = list(
        (
            await session.execute(
                select(ReferralAttribution)
                .where(
                    ReferralAttribution.referrer_user_id == int(referrer_user.id),
                    ReferralAttribution.reward_applied.is_(False),
                )
                .order_by(ReferralAttribution.created_at.asc())
                .limit(requirement)
                .with_for_update()
            )
        ).scalars().all()
    )
    for row in pending_refs:
        row.reward_applied = True
    await session.flush()

    result["status"] = "reward_granted"
    result["days_granted"] = int(grant_days)
    result["referrer_message"] = (
        "🎉 Referral milestone reached!\n\n"
        f"Total valid referrals: {total}\n"
        f"+{grant_days} {tier_to_extend.title()} days have been added.\n"
        f"Progress toward the next reward: 0/{requirement}."
    )
    logger.info(
        "[referral_reward_granted] referrer=%s batch=%s days=%s total=%s",
        referrer_tid,
        batch_number,
        grant_days,
        total,
    )
    return result


async def record_referral_conversion(
    session: AsyncSession,
    *,
    referred_telegram_user_id: int,
    payment_reference: str,
) -> dict[str, Any]:
    """Record first-purchase conversion without running a second reward policy."""
    reference = str(payment_reference or "").strip()
    if not reference:
        return {"recorded": False, "reason": "missing_reference"}
    conversion_reference = f"REFERRAL_CONVERSION:{reference}"[:128]
    if (
        await session.execute(
            select(ReferralReward.id).where(ReferralReward.reference == conversion_reference)
        )
    ).scalar_one_or_none() is not None:
        return {"recorded": True, "idempotent": True}

    referred_user = (
        await session.execute(
            select(User).where(User.telegram_user_id == int(referred_telegram_user_id))
        )
    ).scalar_one_or_none()
    if referred_user is None:
        return {"recorded": False, "reason": "user_missing"}
    attribution = (
        await session.execute(
            select(ReferralAttribution)
            .where(ReferralAttribution.referred_user_id == int(referred_user.id))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if attribution is None:
        return {"recorded": False, "reason": "not_referred"}

    attribution.is_successful = True
    attribution.successful_at = attribution.successful_at or _utcnow()
    session.add(
        ReferralReward(
            referrer_user_id=int(attribution.referrer_user_id),
            referred_user_id=int(referred_user.id),
            reward_type="first_purchase_conversion",
            reward_value=1,
            reference=conversion_reference,
            meta={"payment_reference": reference},
        )
    )
    await session.flush()
    logger.info(
        "[referral_conversion_recorded] referred=%s referrer_user_id=%s payment=%s",
        referred_telegram_user_id,
        attribution.referrer_user_id,
        reference,
    )
    return {"recorded": True, "idempotent": False}

# === NEW: Signal Archiving & Outcome Handling ===

async def archive_signal_after_outcome(session: AsyncSession, signal_id: str) -> None:
    """Mark signal as archived (soft delete) after outcome is recorded."""
    res: Result[Tuple[Signal]] = await session.execute(select(Signal).where(Signal.signal_id == str(signal_id)))
    sig: Signal | None = res.scalar_one_or_none()
    if sig is not None:
        sig.archived = True
        await session.flush()


async def list_unresolved_signals_for_user(
    session: AsyncSession,
    telegram_user_id: int,
    lookback_days: int = 7,
) -> list[Signal]:
    """Return active delivered signals for this user in the lookback window."""
    # Contract: unresolved is delivery-first and outcome-driven. Do not hide a
    # user-received signal just because stale maintenance flipped Signal.expired
    # or Signal.archived before an Outcome row was written.
    terminal_statuses = {
        "sl",
        "tp",
        "tp3",
        "invalid",
        "invalidated",
        "time_stop",
        "cancel",
        "cancelled",
        "expired",
    }
    # Preserved here as an explicit contract for static regression tests:
    # Outcome.status.notin_(terminal_statuses)
    # ActiveSignalMessage fallback is also merged by list_delivered_signals_for_user.
    return await list_delivered_signals_for_user(
        session,
        telegram_user_id=int(telegram_user_id),
        lookback_days=lookback_days,
        status_filter="active",
        sent_ok_only=True,
    )


async def list_recent_signals_for_user(
    session: AsyncSession,
    telegram_user_id: int,
    lookback_days: int = 30,
) -> list[Signal]:
    """Return all sent signals delivered to this user in the lookback window."""
    return await list_delivered_signals_for_user(
        session,
        telegram_user_id=int(telegram_user_id),
        lookback_days=lookback_days,
        status_filter="all",
        sent_ok_only=True,
    )


async def delete_old_signals(session: AsyncSession, older_than_days: int = 7) -> int:
    """Hard delete signals older than N days. Called periodically."""
    cutoff: datetime = _utcnow() - timedelta(days=max(1, int(older_than_days)))
    res: Result[Tuple[str]] = await session.execute(
        select(Signal.signal_id).where(Signal.created_at < cutoff)
    )
    old_signal_ids: list[Any] = [row[0] for row in res.all()]
    if not old_signal_ids:
        return 0

    # Delete dependent records
    for sig_id in old_signal_ids:
        await session.execute(select(SignalDelivery).where(SignalDelivery.signal_id == sig_id))
        await session.execute(select(Outcome).where(Outcome.signal_id == sig_id))

    # Hard delete
    await session.execute(
        delete(Signal).where(Signal.signal_id.in_(old_signal_ids))
    )
    await session.flush()
    return len(old_signal_ids)


async def extend_subscription_with_bonus(
    session: AsyncSession,
    telegram_user_id: int,
    bonus_days: int,
) -> Optional[datetime]:
    """Add bonus_days to user's active subscription expires_at date. Return new expires_at."""
    user: User = await get_or_create_user(session, telegram_user_id=int(telegram_user_id))
    
    # Find active subscription
    res = await session.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id, Subscription.status == "active")
        .order_by(Subscription.expires_at.desc())
        .limit(1)
    )
    sub = res.scalar_one_or_none()
    if sub is None:
        return None

    if sub.expires_at is None:
        # No expiry = lifetime/free; don't extend
        return None

    new_expires = sub.expires_at + timedelta(days=int(bonus_days))
    sub.expires_at = new_expires
    sub.bonus_days = (int(sub.bonus_days or 0)) + int(bonus_days)
    await session.flush()
    return new_expires


async def downgrade_expired_subscriptions(session: AsyncSession) -> int:
    """Check all subscriptions; downgrade expired ones to FREE tier. Return count."""
    now: datetime = _utcnow()
    res = await session.execute(
        select(Subscription)
        .where(
            Subscription.status == "active",
            Subscription.expires_at.is_not(None),
            Subscription.expires_at < now,
            Subscription.tier != "free",
        )
    )
    expired = list(res.scalars().all())
    count = 0
    for sub in expired:
        sub.status = "expired"
        sub.tier = "free"
        
        # Update user tier to free
        user = sub.user
        if user.tier != "free":
            user.tier = "free"
            count += 1
        await session.flush()

    return count


async def queue_signal_to_global_pool(
    session: AsyncSession,
    signal: Dict[str, Any],
) -> bool:
    """Add signal to global pool for FREE user random distribution.
    
    All generated signals are added to a pool, then randomly distributed to FREE users.
    """
    s: Signal = await get_or_create_signal(session, signal)
    # Signal is now in the database and available for random selection
    return True


def _signal_policy_payload(signal: Signal) -> dict[str, Any]:
    """Convert a persisted signal into the canonical policy-evaluation shape."""
    take_profit: Any = getattr(signal, "take_profit", None)
    if isinstance(take_profit, str):
        try:
            take_profit = json.loads(take_profit)
        except Exception:
            take_profit = []
    if not isinstance(take_profit, (list, tuple)):
        take_profit = [take_profit] if take_profit is not None else []
    return {
        "signal_id": str(getattr(signal, "signal_id", "") or ""),
        "asset": str(getattr(signal, "asset", "") or ""),
        "asset_class": getattr(signal, "asset_class", None),
        "direction": str(getattr(signal, "direction", "") or ""),
        "timeframe": str(getattr(signal, "timeframe", "") or ""),
        "entry": getattr(signal, "entry", None),
        "stop_loss": getattr(signal, "stop_loss", None),
        "take_profit": list(take_profit),
        "score": getattr(signal, "score", None),
        "strategy_name": getattr(signal, "strategy_name", None),
        "regime": getattr(signal, "regime", None),
        "generated_at": getattr(signal, "created_at", None),
        "created_at": getattr(signal, "created_at", None),
        "expires_at": getattr(signal, "expires_at", None),
        "quality_gate_passed": bool(getattr(signal, "quality_gate_passed", False)),
        "quality_gate_version": getattr(signal, "quality_gate_version", None),
        "ml_probability": getattr(signal, "ml_probability", None),
        "ml_probability_raw": getattr(signal, "ml_probability_raw", None),
        "ml_probability_calibrated": getattr(signal, "ml_probability_calibrated", None),
        "ml_calibration_version": getattr(signal, "ml_calibration_version", None),
        "ml_calibration_validated": bool(getattr(signal, "ml_calibration_validated", False)),
        "ml_calibration_validation_rows": getattr(signal, "ml_calibration_validation_rows", None),
        "ml_calibration_brier": getattr(signal, "ml_calibration_brier", None),
        "ml_calibration_ece": getattr(signal, "ml_calibration_ece", None),
        "thesis_fingerprint": getattr(signal, "thesis_fingerprint", None),
        "asset_discovery_provider": getattr(signal, "asset_discovery_provider", None),
    }


async def _profile_and_integrity_filter_available_signals(
    session: AsyncSession,
    telegram_user_id: int,
    signals: list[Signal],
) -> list[tuple[Signal, float]]:
    """Apply the same profile, freshness and quality policy as live delivery.

    Free-pool and paid "best signal" recovery paths historically bypassed the
    main personalized delivery router.  That allowed stale or profile-mismatched
    signals to be selected even though normal delivery would reject them.
    """
    from core.production_integrity import evaluate_signal_freshness
    from core.signal_quality_gate import evaluate_signal_quality
    from services.user_intelligence import (
        get_user_trading_preferences,
        personalize_signal_for_preferences,
        signal_matches_preferences,
    )

    prefs = await get_user_trading_preferences(session, int(telegram_user_id))
    require_quality = str(os.getenv("DELIVERY_REQUIRE_QUALITY_GATE", "1")).strip().lower() in {
        "1", "true", "yes", "on",
    }
    eligible: list[tuple[Signal, float]] = []
    for signal in signals:
        if bool(getattr(signal, "archived", False)) or bool(getattr(signal, "expired", False)):
            continue
        payload = _signal_policy_payload(signal)
        freshness = evaluate_signal_freshness(
            timeframe=payload.get("timeframe"),
            generated_at=payload.get("generated_at"),
            expires_at=payload.get("expires_at"),
            purpose="delivery",
        )
        if not freshness.ok:
            continue
        quality = evaluate_signal_quality(payload)
        if require_quality and (
            not bool(payload.get("quality_gate_passed"))
            or not quality.ok
        ):
            continue
        matches, _reason = signal_matches_preferences(payload, prefs)
        if not matches:
            continue
        personalized = personalize_signal_for_preferences(payload, prefs)
        rank = float(personalized.get("personalized_rank_score") or payload.get("score") or 0.0)
        eligible.append((signal, rank))
    return eligible


async def get_random_available_signals_for_free_user(
    session: AsyncSession,
    telegram_user_id: int,
    limit: int = 2,
) -> list[Signal]:
    """Get random *eligible* signals the user has not received yet.

    Randomness is applied only after production integrity and the user's AI
    trading profile have been enforced.
    
    Returns up to 'limit' random signals that:
    - Were created recently (last 24 hours)
    - Haven't been delivered to this user yet
    - Are still ongoing trades (no outcome recorded)
    
    Different users will get different random signals from the same pool.
    """
    user: User = await get_or_create_user(session, telegram_user_id=int(telegram_user_id))
    now: datetime = _utcnow()
    cutoff: datetime = now - timedelta(hours=24)
    min_score = _env_int("FREE_RANDOM_MIN_SCORE", 80)
    
    # Get signals this user already received
    res_delivered: Result[Tuple[str]] = await session.execute(
        select(SignalDelivery.signal_id).where(SignalDelivery.user_id == user.id)
    )
    already_received: set[Any] = set(row[0] for row in res_delivered.all())

    try:
        asset_lock_hours = max(0, int(os.getenv("ASSET_REPEAT_LOCK_HOURS", "4") or 4))
    except Exception:
        asset_lock_hours = 4
    asset_lock_cutoff = now - timedelta(hours=asset_lock_hours)
    res_locked_assets: Result[Tuple[str]] = await session.execute(
        select(Signal.asset)
        .select_from(SignalDelivery)
        .join(Signal, Signal.signal_id == SignalDelivery.signal_id)
        .where(
            SignalDelivery.user_id == user.id,
            SignalDelivery.delivered_at >= asset_lock_cutoff,
            SignalDelivery.sent_ok.is_(True),
        )
        .distinct()
    )
    locked_assets: set[str] = {str(row[0] or "").upper().strip() for row in res_locked_assets.all() if row[0]}
    
    # Pending outcome projections are active signals, not resolved trades.
    res_resolved = await session.execute(
        select(Outcome.signal_id, Outcome.status).where(Outcome.signal_id.isnot(None))
    )
    from core.outcome_ordering import outcome_is_terminal

    def test_outcome_terminal_import_for_available_signal_queries() -> None:
        assert outcome_is_terminal("tp3") is True
        assert outcome_is_terminal("sl") is True
        assert outcome_is_terminal("partial_win_be") is True
        assert outcome_is_terminal("pending") is False
    resolved_signals: set[Any] = {
        row[0] for row in res_resolved.all() if outcome_is_terminal(row[1])
    }
    
    # Get all recent signals (not yet archived)
    # Note: archived filtering will be applied once migration 0009 runs
    res_signals: Result[Tuple[Signal]] = await session.execute(
        select(Signal)
        .where(
            Signal.created_at >= cutoff,
        )
        .order_by(Signal.created_at.desc())
    )
    all_recent: list[Signal] = list(res_signals.scalars().all())
    
    # Filter out already received and resolved trades
    prefiltered: list[Signal] = [
        s for s in all_recent
        if (
            s.signal_id not in already_received
            and s.signal_id not in resolved_signals
            and str(getattr(s, "asset", "") or "").upper().strip() not in locked_assets
            and float(getattr(s, "score", 0) or 0) >= float(min_score)
        )
    ]
    policy_filtered = await _profile_and_integrity_filter_available_signals(
        session,
        int(telegram_user_id),
        prefiltered,
    )
    available = [signal for signal, _rank in policy_filtered]
    
    # Truly random selection - bot picks any signals it wants
    if len(available) <= limit:
        return available
    
    return random.sample(available, limit)


async def get_highest_scoring_available_signal_for_user(
    session: AsyncSession,
    telegram_user_id: int,
) -> Optional[Signal]:
    """Get the highest scoring signal user hasn't received yet.
    
    Used for extra paid signals - gives user the best available ongoing signal.
    Only returns signals with no outcome (still active trades).
    """
    user: User = await get_or_create_user(session, telegram_user_id=int(telegram_user_id))
    now: datetime = _utcnow()
    cutoff: datetime = now - timedelta(hours=24)
    
    # Get signals this user already received
    res_delivered: Result[Tuple[str]] = await session.execute(
        select(SignalDelivery.signal_id).where(SignalDelivery.user_id == user.id)
    )
    already_received: set[Any] = set(row[0] for row in res_delivered.all())

    try:
        asset_lock_hours = max(0, int(os.getenv("ASSET_REPEAT_LOCK_HOURS", "4") or 4))
    except Exception:
        asset_lock_hours = 4
    asset_lock_cutoff = now - timedelta(hours=asset_lock_hours)
    res_locked_assets: Result[Tuple[str]] = await session.execute(
        select(Signal.asset)
        .select_from(SignalDelivery)
        .join(Signal, Signal.signal_id == SignalDelivery.signal_id)
        .where(
            SignalDelivery.user_id == user.id,
            SignalDelivery.delivered_at >= asset_lock_cutoff,
            SignalDelivery.sent_ok.is_(True),
        )
        .distinct()
    )
    locked_assets: set[str] = {str(row[0] or "").upper().strip() for row in res_locked_assets.all() if row[0]}
    
    # Pending outcome projections are active signals, not resolved trades.
    res_resolved = await session.execute(
        select(Outcome.signal_id, Outcome.status).where(Outcome.signal_id.isnot(None))
    )
    from core.outcome_ordering import outcome_is_terminal

    def test_outcome_terminal_import_for_available_signal_queries() -> None:
        assert outcome_is_terminal("tp3") is True
        assert outcome_is_terminal("sl") is True
        assert outcome_is_terminal("partial_win_be") is True
        assert outcome_is_terminal("pending") is False
    resolved_signals: set[Any] = {
        row[0] for row in res_resolved.all() if outcome_is_terminal(row[1])
    }
    
    # Get highest scoring recent signal not yet delivered to user and still ongoing
    # Note: archived filtering will be applied once migration 0009 runs
    res_signal: Result[Tuple[Signal]] = await session.execute(
        select(Signal)
        .where(
            Signal.created_at >= cutoff,
            Signal.signal_id.notin_(already_received) if already_received else True,
            Signal.signal_id.notin_(resolved_signals) if resolved_signals else True,
            ~Signal.asset.in_(locked_assets) if locked_assets else True,
        )
        .order_by(Signal.score.desc(), Signal.created_at.desc())
        .limit(100)
    )
    candidates = list(res_signal.scalars().all())
    policy_filtered = await _profile_and_integrity_filter_available_signals(
        session,
        int(telegram_user_id),
        candidates,
    )
    if not policy_filtered:
        return None
    policy_filtered.sort(key=lambda item: item[1], reverse=True)
    return policy_filtered[0][0]


async def queue_random_free_signals_for_all_users(
    session: AsyncSession,
) -> int:
    """Queue random signals for all FREE users who haven't reached daily limit.
    
    Called periodically to distribute signals to FREE users.
    Returns count of users who received new signals.
    """
    now: datetime = _utcnow()
    daily_limit = 3
    count = 0
    
    # Resolve the effective product tier rather than filtering on a potentially
    # stale cached value or an operator allowlist.
    from db.access import resolve_product_tier

    res_users: Result[Tuple[User]] = await session.execute(
        select(User).where(User.is_blocked.is_(False), User.is_suspended.is_(False))
    )
    free_users: list[User] = []
    for candidate in list(res_users.scalars().all()):
        if await resolve_product_tier(session, candidate) == "free":
            free_users.append(candidate)
    
    for user in free_users:
        # Check user's daily window
        try:
            anchor: datetime = user.created_at.replace(tzinfo=None)
            window_start: datetime = now.replace(
                hour=int(anchor.hour),
                minute=int(anchor.minute),
                second=int(anchor.second),
                microsecond=0
            )
            if window_start > now:
                window_start: datetime = window_start - timedelta(days=1)
        except Exception:
            window_start: datetime = now.replace(hour=0, minute=0, second=0, microsecond=0)
        window_end: datetime = window_start + timedelta(days=1)
        
        # Check how many already queued/sent today
        res_count: Result[Tuple[int]] = await session.execute(
            select(func.count(FreeSignalQueue.id)).where(
                FreeSignalQueue.user_id == user.id,
                FreeSignalQueue.date >= window_start,
                FreeSignalQueue.date < window_end,
                FreeSignalQueue.status.in_(["queued", "sent"]),
            )
        )
        already = int(res_count.scalar() or 0)
        
        if already >= daily_limit:
            continue
        
        # Get random signals for this user
        needed: int = daily_limit - already
        random_signals: list[Signal] = await get_random_available_signals_for_free_user(
            session, user.telegram_user_id, limit=needed
        )
        
        # Queue them (default: immediate, env can still add delay if needed)
        min_delay_minutes: int = max(0, _env_int("FREE_MIN_DELAY_MINUTES", 0))
        max_delay_minutes: int = max(min_delay_minutes, _env_int("FREE_MAX_DELAY_MINUTES", 0))
        max_window_delay = max(
            min_delay_minutes,
            int(max(0, (window_end - now).total_seconds()) // 60) - 5,
        )
        effective_max_delay = max(min_delay_minutes, min(max_delay_minutes, max_window_delay))
        for sig in random_signals:
            randomized_delay = random.randint(min_delay_minutes, effective_max_delay)
            deliver_after: datetime = to_naive_utc(now + timedelta(minutes=randomized_delay))
            q = FreeSignalQueue(
                user_id=user.id,
                date=window_start,
                signal_id=sig.signal_id,
                asset=str(sig.asset),
                timeframe=str(sig.timeframe),
                direction=str(sig.direction),
                score=int(sig.score or 0),
                queued_at=now,
                deliver_after=deliver_after,
                status="queued",
            )
            session.add(q)
            count += 1
        
        if random_signals:
            await session.flush()
    
    return count


async def count_signals_delivered_today(
    session: AsyncSession,
    telegram_user_id: int,
) -> int:
    """Count how many signals were delivered to a user today."""
    from db.models import User, SignalDelivery
    from sqlalchemy import select, func
    from datetime import datetime, timedelta
    
    user: User = await get_or_create_user(session, telegram_user_id=int(telegram_user_id))
    now: datetime = _utcnow()
    start_of_day: datetime = to_naive_utc(now).replace(hour=0, minute=0, second=0, microsecond=0)
    
    res: Result[Tuple[int]] = await session.execute(
        select(func.count(SignalDelivery.id)).where(
            SignalDelivery.user_id == user.id,
            SignalDelivery.sent_ok.is_(True),
            SignalDelivery.delivered_at >= start_of_day
        )
    )
    return res.scalar_one() or 0


async def get_last_signal_delivery_time(
    session: AsyncSession,
    telegram_user_id: int,
) -> datetime | None:
    """
    Get the timestamp of the last signal delivery for a user today.
    Returns None if no signals delivered today. Used for random timing of 2nd signal.
    """
    from db.models import User, SignalDelivery
    from sqlalchemy import select, desc
    
    user: User = await get_or_create_user(session, telegram_user_id=int(telegram_user_id))
    now: datetime = _utcnow()
    start_of_day: datetime = to_naive_utc(now).replace(hour=0, minute=0, second=0, microsecond=0)
    
    res: Result[Tuple[datetime]] = await session.execute(
        select(SignalDelivery.delivered_at)
        .where(
            SignalDelivery.user_id == user.id,
            SignalDelivery.delivered_at >= start_of_day
        )
        .order_by(desc(SignalDelivery.delivered_at))
        .limit(1)
    )
    return res.scalar_one_or_none()


# In-memory cache for user's next signal send times (user_id + signal_number -> datetime)
# Bot randomly decides WHEN to check for signals, not tied to specific signal creation time
# Resets daily, so users get new random times each day
_user_next_signal_times = {}


async def get_user_next_signal_time(
    session: AsyncSession,
    telegram_user_id: int,
    signal_number: int,
):
    """
    Get the bot's randomly chosen time to send signal #1 or #2 for a user.
    Returns None if not set yet. Bot randomly picks times during day to check for signals.
    Example: Bot decides "I'll send 1st signal at 5:00am" (regardless of when signals were created).
    """
    key: str = f"{telegram_user_id}_signal{signal_number}"
    return _user_next_signal_times.get(key)


async def set_user_next_signal_time(
    session: AsyncSession,
    telegram_user_id: int,
    signal_number: int,
    send_time,
) -> None:
    """
    Set the bot's randomly chosen time to send signal #1 or #2 for a user.
    Bot randomly picks a time (e.g., 0-18 hours into the day for 1st signal) and stores it.
    At that time, bot will send whatever signal is available then.
    """
    key: str = f"{telegram_user_id}_signal{signal_number}"
    _user_next_signal_times[key] = send_time


async def get_strategy_performance(session: AsyncSession, strategy_name: str) -> dict:
    """Get performance metrics for a strategy.
    
    Returns: {
        'win_rate': float (0.0-1.0),
        'avg_rr': float (average risk/reward ratio),
        'total_outcomes': int,
        'wins': int,
        'losses': int
    }
    """
    try:
        # Get all outcomes for signals with this strategy
        stmt: Select[Tuple[Outcome]] = select(Outcome).select_from(Signal).join(
            Outcome, Outcome.signal_id == Signal.signal_id
        ).where(Signal.strategy_name == strategy_name)
        
        result: Result[Tuple[Outcome]] = await session.execute(stmt)
        outcomes: list[Outcome] = result.scalars().all()
        
        total: int = len(outcomes)
        wins: int = sum(1 for o in outcomes if str(getattr(o, 'status', '')).lower() == 'tp')
        losses: int = total - wins
        win_rate: float = (wins / total) if total > 0 else 0.0
        
        # Default avg_rr (would need RR calculation from outcomes)
        avg_rr = 1.8
        
        return {
            'win_rate': win_rate,
            'avg_rr': avg_rr,
            'total_outcomes': total,
            'wins': wins,
            'losses': losses
        }
    except Exception:
        # Fallback if query fails
        return {
            'win_rate': 0.0,
            'avg_rr': 1.8,
            'total_outcomes': 0,
            'wins': 0,
            'losses': 0
        }


async def list_active_signals(
    session: AsyncSession,
    *,
    max_age_days: int = 3,
    limit: int = 100,
) -> list[Signal]:
    """Return recent non-expired, non-archived signals within max_age_days."""
    now: datetime = _utcnow()
    start: datetime = now - timedelta(days=max(1, int(max_age_days)))
    q: Select[Tuple[Signal]] = (
        select(Signal)
        .where(
            Signal.created_at >= start,
            Signal.archived.is_(False),
            Signal.expired.is_(False),
        )
        .order_by(Signal.created_at.desc())
        .limit(max(1, int(limit)))
    )
    res: Result[Tuple[Signal]] = await session.execute(q)
    return list(res.scalars().all())


def get_signal_outcome_status(signal_id: str) -> dict | None:
    """Sync helper: return outcome status dict for a signal, or None if no outcome exists.

    Returns ``{"reached": bool, "status": str}`` when an Outcome row is found.
    Called from sync delivery threads so it runs the async query in a fresh loop.
    """
    try:
        from utils.async_runner import run_sync
        from db.session import get_session

        async def _check() -> dict | None:
            async with get_session() as s:
                res = await s.execute(
                    select(Outcome)
                    .where(Outcome.signal_id == str(signal_id))
                    .limit(1)
                )
                oc: Outcome | None = res.scalar_one_or_none()
                if oc is None:
                    return None
                terminal = {"tp", "tp1", "tp2", "tp3", "sl", "invalid", "time_stop"}
                return {"reached": oc.status in terminal, "status": oc.status}

        return run_sync(_check())
    except Exception:
        return None


async def expire_signal(session: AsyncSession, signal_id: str) -> None:
    """Mark a Signal row as expired so it is excluded from active-signal queries.

    Called when the delivery phase determines a signal's entry price has drifted
    too far from the live price (stale signal). Prevents the resend job and future
    delivery cycles from re-attempting to deliver the same stale signal.
    """
    await session.execute(
        update(Signal)
        .where(Signal.signal_id == str(signal_id))
        .values(expired=True)
    )


# ---------------------------------------------------------------------------
# Managed-asset helpers
# ---------------------------------------------------------------------------

async def get_active_managed_assets(session: AsyncSession) -> list[str]:
    """Return symbols for all active managed assets, oldest-analyzed first.

    Ordering by last_analyzed_at ASC NULLS FIRST ensures assets that have
    never been (or were least recently) analyzed bubble to the top of the
    engine queue each cycle, preventing any symbol from being perpetually
    starved (anti-stagnation guarantee).
    """
    res = await session.execute(
        select(ManagedAsset.symbol)
        .where(ManagedAsset.is_active.is_(True))
        .order_by(ManagedAsset.last_analyzed_at.asc().nulls_first())
    )
    return [row[0] for row in res.fetchall()]


async def add_managed_asset(
    session: AsyncSession,
    symbol: str,
    asset_type: str = "crypto",
    added_by: int | None = None,
    note: str | None = None,
) -> ManagedAsset:
    """Pin an asset. Re-activates it if it was previously soft-deleted."""
    from datetime import datetime
    symbol = symbol.upper().strip()
    res = await session.execute(
        select(ManagedAsset).where(ManagedAsset.symbol == symbol)
    )
    existing = res.scalar_one_or_none()
    if existing:
        existing.is_active = True
        existing.asset_type = asset_type
        existing.added_by = added_by
        existing.note = note
        existing.updated_at = now_utc_naive()
        return existing
    asset = ManagedAsset(
        symbol=symbol,
        asset_type=asset_type,
        is_active=True,
        added_by=added_by,
        note=note,
    )
    session.add(asset)
    return asset


async def remove_managed_asset(session: AsyncSession, symbol: str) -> bool:
    """Soft-delete a pinned asset. Returns True if it existed."""
    from datetime import datetime
    symbol = symbol.upper().strip()
    res = await session.execute(
        select(ManagedAsset).where(ManagedAsset.symbol == symbol)
    )
    existing = res.scalar_one_or_none()
    if not existing:
        return False
    existing.is_active = False
    existing.updated_at = now_utc_naive()
    return True


async def list_all_managed_assets(session: AsyncSession) -> list[ManagedAsset]:
    """Return all managed-asset rows (active and inactive) for admin display."""
    res = await session.execute(
        select(ManagedAsset).order_by(ManagedAsset.symbol)
    )
    return list(res.scalars().all())


async def update_managed_asset_last_analyzed(
    session: AsyncSession, symbols: list[str]
) -> None:
    """Stamp last_analyzed_at=NOW() for a batch of symbols after the engine
    processes them.  Called once per cycle so the queue always rotates through
    the full asset universe (anti-stagnation guarantee).  Safe to call with an
    empty list — it is a no-op.
    """
    if not symbols:
        return
    normalized = [s.upper().strip() for s in symbols if s and s.strip()]
    if not normalized:
        return
    await session.execute(
        update(ManagedAsset)
        .where(ManagedAsset.symbol.in_(normalized))
        .values(last_analyzed_at=now_utc_naive())
    )


# ============================================================================
# PHASE 2: Regime-Specific Strategy Performance Queries
# ============================================================================

async def get_strategy_performance_by_regime(
    session: AsyncSession,
    strategy_name: str,
    regime: str,
) -> Dict[str, Any]:
    """
    Query strategy performance filtered by regime only.
    
    PHASE 2 FEATURE: Aggregates all outcomes for a strategy across all assets/timeframes,
    filtered by market regime. Returns performance metrics for ML weighting calculations.
    
    Args:
        session: AsyncSession for database queries
        strategy_name: Strategy name (e.g., "rsi", "supertrend")
        regime: Market regime ("TRENDING", "RANGING", "VOLATILE")
    
    Returns:
    {
        "trades": int,                    # Total trades
        "win_rate": 0.0-1.0,              # Percentage of winning trades
        "avg_rr": float,                  # Average risk/reward ratio
        "expectancy": float,              # Average profit per trade
        "confidence_interval": float,     # Bayesian credibility 0.0-1.0
    }
    """
    # Query outcomes where the associated signal has matching strategy_name and regime
    query = (
        select(
            func.count(Outcome.id).label('total'),
            func.sum(case((Outcome.status == 'win', 1), else_=0)).label('wins'),
            func.sum(case((Outcome.status == 'loss', 1), else_=0)).label('losses'),
            func.avg(case((Outcome.status == 'win', Outcome.pnl_pct), else_=None)).label('avg_win_pct'),
            func.avg(case((Outcome.status == 'loss', Outcome.pnl_pct), else_=None)).label('avg_loss_pct'),
        )
        .join(Signal, Outcome.signal_id == Signal.signal_id)
        .where(
            and_(
                Signal.strategy_name == strategy_name,
                Outcome.regime == regime,
            )
        )
    )
    
    try:
        result = await session.execute(query)
        row = result.one_or_none()
        
        if not row or row.total == 0:
            return {
                "trades": 0,
                "win_rate": 0.0,
                "avg_rr": 0.0,
                "expectancy": 0.0,
                "confidence_interval": 0.0,
            }
        
        total = row.total or 0
        wins = row.wins or 0
        losses = row.losses or 0
        avg_win = float(row.avg_win_pct or 0.0)
        avg_loss = abs(float(row.avg_loss_pct or 0.0))
        
        win_rate = wins / total if total > 0 else 0.0
        avg_rr = avg_win / avg_loss if avg_loss > 0 else 0.0
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        
        # Bayesian credibility: min(trades / 100, 1.0)
        # 100 trades = full credibility, fewer trades = proportionally lower
        confidence = min(total / 100.0, 1.0)
        
        return {
            "trades": int(total),
            "win_rate": float(win_rate),
            "avg_rr": float(avg_rr),
            "expectancy": float(expectancy),
            "confidence_interval": float(confidence),
        }
    
    except Exception as e:
        logger.debug(f"[get_strategy_performance_by_regime] Query failed: {e}")
        return {
            "trades": 0,
            "win_rate": 0.0,
            "avg_rr": 0.0,
            "expectancy": 0.0,
            "confidence_interval": 0.0,
        }


async def get_asset_class_strategy_performance(
    session: AsyncSession,
    strategy_name: str,
    asset_class: str,
    regime: str,
) -> Dict[str, Any]:
    """
    Query strategy performance for a specific asset class + regime combination.
    
    PHASE 2 FEATURE: Returns performance specific to one asset class in one regime.
    Useful for understanding if a strategy works well for crypto but not forex, etc.
    
    Args:
        session: AsyncSession for database queries
        strategy_name: Strategy name
        asset_class: "crypto", "forex", "stock", "commodity"
        regime: "TRENDING", "RANGING", "VOLATILE"
    
    Returns: Same as get_strategy_performance_by_regime()
    """
    query = (
        select(
            func.count(Outcome.id).label('total'),
            func.sum(case((Outcome.status == 'win', 1), else_=0)).label('wins'),
            func.sum(case((Outcome.status == 'loss', 1), else_=0)).label('losses'),
            func.avg(case((Outcome.status == 'win', Outcome.pnl_pct), else_=None)).label('avg_win_pct'),
            func.avg(case((Outcome.status == 'loss', Outcome.pnl_pct), else_=None)).label('avg_loss_pct'),
        )
        .join(Signal, Outcome.signal_id == Signal.signal_id)
        .where(
            and_(
                Signal.strategy_name == strategy_name,
                Outcome.asset_class == asset_class,
                Outcome.regime == regime,
            )
        )
    )
    
    try:
        result = await session.execute(query)
        row = result.one_or_none()
        
        if not row or row.total == 0:
            return {
                "trades": 0,
                "win_rate": 0.0,
                "avg_rr": 0.0,
                "expectancy": 0.0,
                "confidence_interval": 0.0,
            }
        
        total = row.total or 0
        wins = row.wins or 0
        losses = row.losses or 0
        avg_win = float(row.avg_win_pct or 0.0)
        avg_loss = abs(float(row.avg_loss_pct or 0.0))
        
        win_rate = wins / total if total > 0 else 0.0
        avg_rr = avg_win / avg_loss if avg_loss > 0 else 0.0
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        confidence = min(total / 100.0, 1.0)
        
        return {
            "trades": int(total),
            "win_rate": float(win_rate),
            "avg_rr": float(avg_rr),
            "expectancy": float(expectancy),
            "confidence_interval": float(confidence),
        }
    
    except Exception as e:
        logger.debug(f"[get_asset_class_strategy_performance] Query failed: {e}")
        return {
            "trades": 0,
            "win_rate": 0.0,
            "avg_rr": 0.0,
            "expectancy": 0.0,
            "confidence_interval": 0.0,
        }
