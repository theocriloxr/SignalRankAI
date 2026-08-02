"""
engine/realtime_outcome_tracker.py - Real-time async TP/SL outcome detection.

Replaces the sluggish 3-minute APScheduler loop with a persistent async task
that polls open signals every `CHECK_INTERVAL_SECONDS` seconds (default: 15)
using high-frequency REST calls or WebSocket price feeds.

Key behaviours:
  - Monitors all unresolved signals.
  - Detects TP1/TP2/TP3/SL hits instantly.
  - On TP1 hit: moves SL to break-even (trailing SL) via MT5 bridge + notifies users.
  - On final TP/SL: sends branded PnL "flex" card notification.
  - Persists outcome to the `outcomes` table.

Environment:
    OUTCOME_CHECK_INTERVAL_SECONDS  - Poll interval (default: 20)
    ACTIVE_SIGNAL_LOOKBACK_HOURS    - How far back to look for open signals (default: 168)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select

logger = logging.getLogger(__name__)

ENTRY_ZONE_PCT = float(os.getenv("ENTRY_ZONE_PCT", "0.003"))
BE_BUFFER_PCT = float(os.getenv("BE_BUFFER_PCT", "0.001"))
TICK_INTERVAL = float(os.getenv("TICK_INTERVAL_SECONDS", "30.0"))
_EXCURSION_CACHE: Dict[str, Dict[str, float]] = {}
_DELIVERY_PROOF_STATES = ("sent", "delivered", "confirmed", "reconciled")


def _record_excursion(signal_id: str, direction: str, entry: float, price: float) -> Dict[str, float]:
    """Accumulate signed MFE/MAE in memory between persisted lifecycle events."""
    try:
        entry_f = float(entry)
        price_f = float(price)
        if entry_f <= 0 or price_f <= 0:
            return dict(_EXCURSION_CACHE.get(str(signal_id), {}))
        signed_pct = (
            ((entry_f - price_f) / entry_f) * 100.0
            if str(direction or "").lower() == "short"
            else ((price_f - entry_f) / entry_f) * 100.0
        )
        current = _EXCURSION_CACHE.setdefault(str(signal_id), {"mfe_pct": 0.0, "mae_pct": 0.0})
        current["mfe_pct"] = max(float(current.get("mfe_pct", 0.0)), signed_pct, 0.0)
        current["mae_pct"] = min(float(current.get("mae_pct", 0.0)), signed_pct, 0.0)
        return dict(current)
    except Exception:
        return dict(_EXCURSION_CACHE.get(str(signal_id), {}))


def _utc_now_naive() -> datetime:
    """Naive UTC timestamp for legacy DB columns that store UTC without tzinfo."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _session_scope(get_session: Any, **kwargs: Any) -> Any:
    """Open a prioritized session while tolerating legacy test/session shims."""
    try:
        return get_session(**kwargs)
    except TypeError:
        return get_session()


def _outcome_db_priority() -> str:
    """Outcome state and user notifications are operational, never best-effort."""
    raw = str(os.getenv("OUTCOME_TRACKER_DB_PRIORITY", "critical") or "critical").strip().lower()
    return raw if raw in {"interactive", "critical"} else "critical"


def _outcome_db_timeout() -> float:
    try:
        return max(1.0, float(os.getenv("OUTCOME_DB_ADMISSION_TIMEOUT_SECONDS", "12") or 12))
    except (TypeError, ValueError):
        return 12.0


def _database_tp_progress(lifecycle: Any, outcome: Any) -> int:
    """Derive authoritative target progress from durable lifecycle/outcome data."""
    from core.signal_lifecycle import (
        highest_tp_for_state,
        lifecycle_state_for_outcome,
    )

    progress = highest_tp_for_state(getattr(lifecycle, "state", None))
    progress = max(
        progress,
        highest_tp_for_state(lifecycle_state_for_outcome(getattr(outcome, "status", None))),
    )
    try:
        progress = max(progress, int((getattr(outcome, "meta", None) or {}).get("tp_hit_index") or 0))
    except Exception:
        pass
    if lifecycle is not None:
        for index in (1, 2, 3):
            if getattr(lifecycle, f"tp{index}_hit_at", None) is not None:
                progress = max(progress, index)
    return max(0, min(3, int(progress)))


@dataclass(frozen=True, slots=True)
class OutcomePriceObservation:
    asset: str
    price: float | None
    provider: str
    quote_time: str | None
    provider_trusted: bool
    reason: str | None = None
    request_id: str | None = None


async def _get_outcome_quote(symbol: str) -> OutcomePriceObservation:
    """Fetch one typed, attributable quote for an asset outcome cycle."""
    canonical = str(symbol or "").upper().strip()
    try:
        from data.get_live_price import get_live_price_result
        from data.provider_types import (
            LivePriceFailure,
            LivePriceQuote,
            validate_quote_for_final_delivery,
        )

        result = await get_live_price_result(
            canonical,
            timeout=max(1.0, float(os.getenv("OUTCOME_QUOTE_TIMEOUT_SECONDS", "5") or 5)),
        )
        if isinstance(result, LivePriceFailure):
            return OutcomePriceObservation(
                canonical, None, str(result.provider or "all"), None, False,
                str(result.reason or "quote_unavailable"), str(result.request_id or "") or None,
            )
        if not isinstance(result, LivePriceQuote):
            return OutcomePriceObservation(canonical, None, "unknown", None, False, "invalid_quote_contract")

        trust = validate_quote_for_final_delivery(result, market_open=True)
        trusted = bool(trust.ok)
        reason = None if trusted else str(trust.reason or "quote_untrusted")
        quote_time = (
            datetime.fromtimestamp(float(result.source_timestamp), tz=timezone.utc).isoformat()
            if result.source_timestamp is not None
            else None
        )
        return OutcomePriceObservation(
            asset=canonical,
            price=float(result.price) if trusted else None,
            provider=str(result.provider or "unknown"),
            quote_time=quote_time,
            provider_trusted=trusted,
            reason=reason,
            request_id=str(result.request_id or "") or None,
        )
    except Exception as exc:
        return OutcomePriceObservation(
            canonical, None, "all", None, False,
            f"quote_fetch_error:{type(exc).__name__}", None,
        )


async def _fetch_outcome_quotes(
    signals: List[Dict[str, Any]],
) -> Dict[str, OutcomePriceObservation]:
    """Fetch exactly one logical quote per unique asset for this cycle."""
    assets = sorted(
        {
            str(signal.get("asset") or signal.get("symbol") or "").upper().strip()
            for signal in signals
            if str(signal.get("asset") or signal.get("symbol") or "").strip()
        }
    )
    concurrency = max(1, int(os.getenv("OUTCOME_QUOTE_MAX_CONCURRENCY", "8") or 8))
    semaphore = asyncio.Semaphore(concurrency)

    async def _one(asset: str) -> tuple[str, OutcomePriceObservation]:
        async with semaphore:
            return asset, await _get_outcome_quote(asset)

    rows = await asyncio.gather(*(_one(asset) for asset in assets))
    return dict(rows)


async def _publish_outcome_snapshot(
    signal: Dict[str, Any],
    observation: OutcomePriceObservation,
    *,
    lifecycle_state: str,
    highest_tp_hit: int,
) -> None:
    from engine.outcome_snapshots import (
        build_outcome_snapshot,
        read_cached_outcome_snapshot,
        write_outcome_snapshot,
    )

    price = observation.price
    quote_time = observation.quote_time
    if price is None:
        previous = await read_cached_outcome_snapshot(str(signal.get("signal_id") or ""))
        if previous is not None:
            price = previous.price
            quote_time = previous.quote_time

    snapshot = build_outcome_snapshot(
        signal,
        state=lifecycle_state,
        highest_tp_hit=highest_tp_hit,
        price=price,
        quote_time=quote_time,
        provider=observation.provider,
        provider_trusted=observation.provider_trusted,
        provider_reason=observation.reason,
    )
    await write_outcome_snapshot(snapshot)


class SignalState:
    PENDING = "PENDING"
    ENTRY_FILLED = "ENTRY_FILLED"
    PARTIAL_TP1 = "PARTIAL_TP1"
    PARTIAL_TP2 = "PARTIAL_TP2"
    CLOSED_TP3 = "CLOSED_TP3"
    CLOSED_SL = "CLOSED_SL"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"

    TERMINAL = {CLOSED_TP3, CLOSED_SL, EXPIRED, INVALIDATED}


class TrackedSignal:
    """Compact state-machine representation used by tick-level outcome tests."""

    __slots__ = (
        "signal_id",
        "asset",
        "direction",
        "entry",
        "stop_loss",
        "tp_levels",
        "timeframe",
        "state",
        "sl_current",
        "highest_tp_hit",
        "entry_filled_at",
        "created_at",
        "expires_at",
    )

    def __init__(self, row: Any) -> None:
        self.signal_id = str(getattr(row, "signal_id", "") or "")
        self.asset = str(getattr(row, "asset", "") or "").upper().strip()
        self.direction = str(getattr(row, "direction", "long") or "long").lower()
        self.entry = float(getattr(row, "entry", 0) or 0)
        self.stop_loss = float(getattr(row, "stop_loss", 0) or 0)
        self.timeframe = str(getattr(row, "timeframe", "1h") or "1h").lower()
        self.created_at = getattr(row, "created_at", None)
        self.expires_at = getattr(row, "expires_at", None)
        self.state = SignalState.PENDING
        self.sl_current = self.stop_loss
        self.highest_tp_hit = 0
        self.entry_filled_at = None
        self.tp_levels = _parse_tp_levels(getattr(row, "take_profit", None))

    @property
    def is_terminal(self) -> bool:
        return self.state in SignalState.TERMINAL

    @property
    def is_long(self) -> bool:
        return self.direction == "long"


def evaluate_tick(signal: TrackedSignal, price: float) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Evaluate one live tick against a tracked signal's linear lifecycle."""
    if signal.is_terminal:
        return None, None

    now = datetime.now(timezone.utc)
    if signal.expires_at and signal.state == SignalState.PENDING:
        try:
            expires_at = signal.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if now >= expires_at:
                return SignalState.EXPIRED, {"expired_at": now.isoformat()}
        except Exception:
            pass

    try:
        p = float(price)
    except Exception:
        return None, None
    if p <= 0 or signal.entry <= 0:
        return None, None

    if signal.state == SignalState.PENDING:
        entry_tolerance = signal.entry * ENTRY_ZONE_PCT
        price_at_entry = abs(p - signal.entry) <= entry_tolerance
        if signal.is_long and p <= signal.sl_current:
            return SignalState.INVALIDATED, {"price": p, "reason": "SL hit before entry"}
        if not signal.is_long and p >= signal.sl_current:
            return SignalState.INVALIDATED, {"price": p, "reason": "SL hit before entry"}
        if price_at_entry or (signal.is_long and p <= signal.entry) or (not signal.is_long and p >= signal.entry):
            signal.entry_filled_at = now
            return SignalState.ENTRY_FILLED, {"fill_price": p, "filled_at": now.isoformat()}
        return None, None

    if signal.is_long and p <= signal.sl_current:
        return SignalState.CLOSED_SL, {
            "exit_price": p,
            "sl_level": signal.sl_current,
            "highest_tp_hit": signal.highest_tp_hit,
            "break_even_stop": signal.sl_current > signal.stop_loss,
        }
    if not signal.is_long and p >= signal.sl_current:
        return SignalState.CLOSED_SL, {
            "exit_price": p,
            "sl_level": signal.sl_current,
            "highest_tp_hit": signal.highest_tp_hit,
            "break_even_stop": signal.sl_current < signal.stop_loss,
        }

    for idx in range(signal.highest_tp_hit, len(signal.tp_levels)):
        tp_price = float(signal.tp_levels[idx])
        tp_hit = (signal.is_long and p >= tp_price) or (not signal.is_long and p <= tp_price)
        if not tp_hit:
            break

        tp_number = idx + 1
        signal.highest_tp_hit = tp_number
        if tp_number == 1:
            if signal.is_long:
                signal.sl_current = max(signal.sl_current, signal.entry * (1 + BE_BUFFER_PCT))
            else:
                signal.sl_current = min(signal.sl_current, signal.entry * (1 - BE_BUFFER_PCT))
            return SignalState.PARTIAL_TP1, {
                "tp_number": 1,
                "tp_price": tp_price,
                "exit_price": p,
                "sl_moved_to_be": signal.sl_current,
            }
        if tp_number == 2:
            return SignalState.PARTIAL_TP2, {
                "tp_number": 2,
                "tp_price": tp_price,
                "exit_price": p,
                "remaining_stop": signal.sl_current,
            }
        return SignalState.CLOSED_TP3, {
            "tp_number": tp_number,
            "tp_price": tp_price,
            "exit_price": p,
            "full_close": True,
        }

    return None, None


def state_to_db_outcome(state: str, highest_tp_hit: int) -> str:
    if state == SignalState.CLOSED_TP3:
        return "tp3" if highest_tp_hit >= 3 else ("tp2" if highest_tp_hit == 2 else "tp1")
    if state == SignalState.CLOSED_SL:
        return "sl"
    if state == SignalState.EXPIRED:
        return "expired"
    if state == SignalState.INVALIDATED:
        return "invalidated"
    if state == SignalState.PARTIAL_TP1:
        return "tp1"
    if state == SignalState.PARTIAL_TP2:
        return "tp2"
    return "unknown"


async def _write_outcome_to_db(signal: TrackedSignal, new_state: str, transition: dict) -> None:
    """Persist a state-machine transition through the existing outcome writer."""
    exit_price = float(
        transition.get("exit_price")
        or transition.get("tp_price")
        or transition.get("fill_price")
        or signal.entry
    )
    status = state_to_db_outcome(new_state, signal.highest_tp_hit)
    if status != "unknown":
        await _persist_outcome(signal.signal_id, status, signal.entry, exit_price)


async def _broadcast_state_change(signal: TrackedSignal, new_state: str, transition: dict) -> None:
    """Broadcast state changes by delegating to the target tracker's notifier."""
    status = state_to_db_outcome(new_state, signal.highest_tp_hit)
    if status == "unknown":
        return
    signal_dict = {
        "signal_id": signal.signal_id,
        "asset": signal.asset,
        "direction": signal.direction,
        "entry": signal.entry,
        "stop_loss": signal.stop_loss,
        "timeframe": signal.timeframe,
    }
    price = float(
        transition.get("exit_price")
        or transition.get("tp_price")
        or transition.get("fill_price")
        or signal.entry
    )
    await _notify_outcome(signal_dict, status, price)


def _check_interval() -> int:
    try:
        return max(5, int(os.getenv("OUTCOME_CHECK_INTERVAL_SECONDS", "20")))
    except Exception:
        return 20


def _lookback_hours() -> int:
    try:
        return int(os.getenv("ACTIVE_SIGNAL_LOOKBACK_HOURS", "168"))
    except Exception:
        return 168


async def _fetch_active_signals() -> List[Dict[str, Any]]:
    """Return all unresolved signals from DB created within lookback window."""
    try:
        from db.session import get_session
        from db.models import Signal, SignalDelivery, Outcome, SignalLifecycle
        from db.priority import DBPriority
        from sqlalchemy import select, or_, exists, and_, func
        cutoff = _utc_now_naive() - timedelta(hours=_lookback_hours())
        limit = max(50, int(os.getenv("OUTCOME_ACTIVE_SIGNAL_LIMIT", "1000") or 1000))
        async with _session_scope(
            get_session,
            priority=_outcome_db_priority(),
            label="outcome_tracker.fetch_active_signals",
            timeout_seconds=_outcome_db_timeout(),
        ) as session:
            stmt = (
                select(Signal, Outcome, SignalLifecycle)
                .outerjoin(Outcome, Outcome.signal_id == Signal.signal_id)
                .outerjoin(SignalLifecycle, SignalLifecycle.signal_id == Signal.signal_id)
                .where(Signal.archived.is_(False))
                .where(Signal.created_at >= cutoff)
                .where(
                    exists(
                        select(SignalDelivery.id).where(
                            and_(
                                SignalDelivery.signal_id == Signal.signal_id,
                                SignalDelivery.sent_ok.is_(True),
                                SignalDelivery.telegram_chat_id.is_not(None),
                                SignalDelivery.telegram_message_id.is_not(None),
                                func.lower(SignalDelivery.delivery_state).in_(_DELIVERY_PROOF_STATES),
                            )
                        )
                    )
                )
                .where(
                    or_(
                        Outcome.id.is_(None),
                        Outcome.status.in_(["tp1", "tp2"]),
                    )
                )
                .limit(limit)
            )
            res = await session.execute(stmt)
            rows = res.all()
            return [
                {
                    "signal_id": s.signal_id,
                    "asset": s.asset,
                    "direction": s.direction,
                    "entry": s.entry,
                    "stop_loss": s.stop_loss,
                    "take_profit": s.take_profit,
                    "created_at": s.created_at,
                    "timeframe": s.timeframe,
                    "score": s.score,
                    "ml_probability": getattr(s, "ml_probability", None),
                    "prev_outcome_status": str(getattr(o, "status", "") or "").lower() if o is not None else None,
                    "prev_outcome_meta": dict(getattr(o, "meta", {}) or {}) if o is not None else {},
                    "expires_at": s.expires_at,
                    "lifecycle_state": str(getattr(lifecycle, "state", "") or "WATCHING_FOR_ENTRY"),
                    "highest_tp_hit": _database_tp_progress(lifecycle, o),
                    "lifecycle_last_price": getattr(lifecycle, "last_price", None),
                    "entry_touched_at": getattr(lifecycle, "entry_touched_at", None),
                    "outcome_category": "LIVE_DELIVERED",
                    "outcome_eligibility_reason": "verified_delivery_query",
                }
                for s, o, lifecycle in rows
            ]
    except Exception as exc:
        try:
            from db.session import DatabaseWorkDeferred
            if isinstance(exc, DatabaseWorkDeferred):
                logger.info(
                    "[outcome_tracker] fetch deferred by DB admission controller: %s",
                    exc,
                )
                return []
        except Exception:
            pass

        diagnostics = None
        try:
            from db.session import get_pool_diagnostics
            diagnostics = get_pool_diagnostics()
        except Exception:
            diagnostics = None
        logger.error(
            "[outcome_tracker] fetch_active_signals error err_type=%s err=%s db_diagnostics=%s",
            type(exc).__name__,
            exc,
            diagnostics,
            exc_info=True,
        )
        return []


async def _fetch_delivered_untracked_signals(limit: int = 100) -> List[Dict[str, Any]]:
    """Find delivered signals that still do not have any outcome row.

    This supports outcome backfill and ensures delivered signals are eventually
    marked for analytics/training even when live tracking missed them.
    """
    try:
        from db.session import get_session
        from db.models import Signal, SignalDelivery, Outcome
        from sqlalchemy import select, or_, and_, func

        lookback_hours = int(os.getenv("OUTCOME_BACKFILL_LOOKBACK_HOURS", "168") or 168)
        limit = max(0, int(os.getenv("OUTCOME_BACKFILL_SIGNAL_LIMIT", str(limit)) or limit))
        if limit <= 0:
            return []
        cutoff = _utc_now_naive() - timedelta(hours=max(24, lookback_hours))

        async with get_session(priority=_outcome_db_priority(), label="engine_realtime_outcome_tracker", timeout_seconds=_outcome_db_timeout()) as session:
            stmt = (
                select(Signal)
                .join(SignalDelivery, SignalDelivery.signal_id == Signal.signal_id)
                .outerjoin(Outcome, Outcome.signal_id == Signal.signal_id)
                .where(Outcome.id.is_(None))
                .where(SignalDelivery.sent_ok.is_(True))
                .where(SignalDelivery.telegram_chat_id.is_not(None))
                .where(SignalDelivery.telegram_message_id.is_not(None))
                .where(func.lower(SignalDelivery.delivery_state).in_(_DELIVERY_PROOF_STATES))
                .where(Signal.created_at >= cutoff)
                .order_by(Signal.created_at.asc())
                .limit(max(1, int(limit)))
            )
            res = await session.execute(stmt)
            rows = res.scalars().all()
            await session.commit()

        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for s in rows:
            sid = str(getattr(s, "signal_id", "") or "")
            if not sid or sid in seen:
                continue
            seen.add(sid)
            out.append(
                {
                    "signal_id": sid,
                    "asset": s.asset,
                    "direction": s.direction,
                    "entry": s.entry,
                    "stop_loss": s.stop_loss,
                    "take_profit": s.take_profit,
                    "created_at": s.created_at,
                    "timeframe": s.timeframe,
                    "score": s.score,
                    "ml_probability": getattr(s, "ml_probability", None),
                    "prev_outcome_status": None,
                    "prev_outcome_meta": {},
                    "expires_at": s.expires_at,
                    "lifecycle_state": "WATCHING_FOR_ENTRY",
                    "highest_tp_hit": 0,
                    "lifecycle_last_price": None,
                    "entry_touched_at": None,
                    "outcome_category": "LIVE_DELIVERED",
                    "outcome_eligibility_reason": "verified_delivery_backfill_query",
                }
            )
        return out
    except Exception as exc:
        logger.debug("[outcome_tracker] fetch_delivered_untracked_signals skipped: %s", exc)
        return []


async def _fetch_signal_for_reconciliation(signal_id: str) -> Optional[Dict[str, Any]]:
    """Load one proof-backed signal regardless of delivery-state casing.

    Telegram delivery rows historically used both upper- and lower-case state
    values. Successful API sends with a message id are authoritative proof even
    when ``delivery_confirmed_at`` was not populated by an older release.
    """
    ref = str(signal_id or "").strip()
    if not ref:
        return None
    try:
        from db.models import Outcome, Signal, SignalDelivery, SignalLifecycle
        from db.session import get_session
        from sqlalchemy import and_, exists, func, select

        async with _session_scope(
            get_session,
            priority=_outcome_db_priority(),
            label="outcome_tracker.reconcile_signal",
            timeout_seconds=_outcome_db_timeout(),
        ) as session:
            stmt = (
                select(Signal, Outcome, SignalLifecycle)
                .outerjoin(Outcome, Outcome.signal_id == Signal.signal_id)
                .outerjoin(SignalLifecycle, SignalLifecycle.signal_id == Signal.signal_id)
                .where(Signal.signal_id == ref)
                .where(Signal.archived.is_(False))
                .where(
                    exists(
                        select(SignalDelivery.id).where(
                            and_(
                                SignalDelivery.signal_id == Signal.signal_id,
                                SignalDelivery.sent_ok.is_(True),
                                SignalDelivery.telegram_chat_id.is_not(None),
                                SignalDelivery.telegram_message_id.is_not(None),
                                func.lower(SignalDelivery.delivery_state).in_(_DELIVERY_PROOF_STATES),
                            )
                        )
                    )
                )
                .limit(1)
            )
            row = (await session.execute(stmt)).first()
            await session.commit()

        if row is None:
            return None
        signal_row, outcome_row, lifecycle = row
        return {
            "signal_id": signal_row.signal_id,
            "asset": signal_row.asset,
            "direction": signal_row.direction,
            "entry": signal_row.entry,
            "stop_loss": signal_row.stop_loss,
            "take_profit": signal_row.take_profit,
            "created_at": signal_row.created_at,
            "timeframe": signal_row.timeframe,
            "score": signal_row.score,
            "ml_probability": getattr(signal_row, "ml_probability", None),
            "prev_outcome_status": (
                str(getattr(outcome_row, "status", "") or "").lower()
                if outcome_row is not None
                else None
            ),
            "prev_outcome_meta": (
                dict(getattr(outcome_row, "meta", {}) or {})
                if outcome_row is not None
                else {}
            ),
            "expires_at": signal_row.expires_at,
            "lifecycle_state": str(
                getattr(lifecycle, "state", "") or "WATCHING_FOR_ENTRY"
            ),
            "highest_tp_hit": _database_tp_progress(lifecycle, outcome_row),
            "lifecycle_last_price": getattr(lifecycle, "last_price", None),
            "entry_touched_at": getattr(lifecycle, "entry_touched_at", None),
            "outcome_category": "LIVE_DELIVERED",
            "outcome_eligibility_reason": "interactive_reconciliation",
        }
    except Exception as exc:
        logger.warning(
            "[outcome_tracker] reconcile lookup failed signal=%s err=%s",
            ref[:16],
            exc,
        )
        return None


async def _get_live_price(symbol: str) -> Optional[float]:
    """Fetch live price for a symbol (same logic as stale validator)."""
    try:
        from engine.stale_signal_validator import _get_live_price_async
        return await asyncio.wait_for(_get_live_price_async(symbol), timeout=5.0)
    except Exception:
        return None


def _parse_tp_levels(take_profit_raw: Any) -> List[float]:
    """Parse take_profit field which may be a JSON list, comma string, or float."""
    def _coerce_tp(value: Any) -> Optional[float]:
        try:
            if isinstance(value, dict):
                value = value.get("price") or value.get("tp") or value.get("target") or value.get("value")
            if value in (None, ""):
                return None
            parsed = float(value)
            return parsed if parsed > 0 else None
        except Exception:
            return None

    if isinstance(take_profit_raw, list):
        return [v for v in (_coerce_tp(x) for x in take_profit_raw) if v is not None]
    if isinstance(take_profit_raw, (int, float)):
        parsed = _coerce_tp(take_profit_raw)
        return [parsed] if parsed is not None else []
    s = str(take_profit_raw).strip()
    # Try JSON first
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            return [v for v in (_coerce_tp(x) for x in parsed) if v is not None]
        coerced = _coerce_tp(parsed)
        return [coerced] if coerced is not None else []
    except Exception:
        pass
    # Comma-separated
    parts = [p.strip() for p in s.split(",") if p.strip()]
    out = []
    for p in parts:
        try:
            out.append(float(p))
        except Exception:
            pass
    return out or []


def _check_hit(
    direction: str,
    entry: float,
    stop_loss: float,
    tp_levels: List[float],
    price: float,
) -> Optional[str]:
    """Return hit label ('sl', 'tp1', 'tp2', 'tp3', 'tp') or None."""
    d = direction.lower()
    if d == "long":
        if price <= stop_loss:
            return "sl"
        max_idx = 0
        for i, tp in enumerate(tp_levels, 1):
            if price >= tp:
                max_idx = i
        if max_idx > 0:
            return f"tp{max_idx}" if max_idx <= 3 else "tp"
    else:  # short
        if price >= stop_loss:
            return "sl"
        max_idx = 0
        for i, tp in enumerate(tp_levels, 1):
            if price <= tp:
                max_idx = i
        if max_idx > 0:
            return f"tp{max_idx}" if max_idx <= 3 else "tp"
    return None


def _halfway_to_tp1_reached(direction: str, entry: float, tp1: float, price: float) -> bool:
    """True when price reaches 50% of path to TP1 but TP1 is not yet hit."""
    try:
        d = str(direction or "long").lower()
        midpoint = float(entry) + ((float(tp1) - float(entry)) * 0.5)
        if d == "short":
            return float(price) <= midpoint and float(price) > float(tp1)
        return float(price) >= midpoint and float(price) < float(tp1)
    except Exception:
        return False


def _risk_free_cache_key(signal_id: str) -> str:
    return f"risk_free_half_tp1:{str(signal_id)}"


def _risk_free_recipient_cache_key(telegram_user_id: int, signal: Dict[str, Any]) -> str:
    asset = str(signal.get("asset") or "").upper().strip()
    direction = str(signal.get("direction") or "long").lower().strip()
    timeframe = str(signal.get("timeframe") or "").lower().strip()
    return f"risk_free_half_tp1_user:{int(telegram_user_id)}:{asset}:{direction}:{timeframe}"


def _tp_progress_cache_key(signal_id: str) -> str:
    return f"tp_progress:{str(signal_id)}"


def _retrace_warn_cache_key(signal_id: str) -> str:
    return f"tp_retrace_warned:{str(signal_id)}"


async def _mark_risk_free_triggered(signal_id: str, ttl_seconds: int = 7 * 24 * 3600) -> bool:
    """Returns True only once per signal for the configured TTL window."""
    try:
        from core.redis_state import state
        key = _risk_free_cache_key(signal_id)
        if await state.cache_get(key):
            return False
        await state.cache_set(key, "1", ex=max(3600, int(ttl_seconds)))
        return True
    except Exception:
        # Warning: allows duplicate notifications if Redis is down.
        # Accepted trade-off — missing a notification is worse than a duplicate.
        return True


async def _mark_risk_free_recipient_triggered(
    telegram_user_id: int,
    signal: Dict[str, Any],
    ttl_seconds: int | None = None,
) -> bool:
    """Returns True once per user+asset+direction+timeframe cooldown window."""
    try:
        from core.redis_state import state

        ttl = int(ttl_seconds or os.getenv("RISK_FREE_USER_COOLDOWN_SECONDS", str(12 * 3600)) or 12 * 3600)
        key = _risk_free_recipient_cache_key(int(telegram_user_id), signal)
        if await state.cache_get(key):
            return False
        await state.cache_set(key, "1", ex=max(300, int(ttl)))
        return True
    except Exception:
        return True


async def _get_tp_progress(signal: Dict[str, Any]) -> int:
    """Return DB-authoritative TP progress; Redis remains projection-only."""
    from core.signal_lifecycle import highest_tp_for_state, lifecycle_state_for_outcome

    try:
        meta = dict(signal.get("prev_outcome_meta") or {})
        db_idx = int(meta.get("tp_hit_index") or 0)
    except Exception:
        db_idx = 0
    durable = max(
        int(signal.get("highest_tp_hit") or 0),
        db_idx,
        highest_tp_for_state(signal.get("lifecycle_state")),
        highest_tp_for_state(lifecycle_state_for_outcome(signal.get("prev_outcome_status"))),
    )
    return max(0, min(3, int(durable)))


async def _set_tp_progress(signal_id: str, idx: int, ttl_seconds: int = 10 * 24 * 3600) -> None:
    try:
        from core.redis_state import state
        await state.cache_set(
            _tp_progress_cache_key(signal_id),
            str(max(0, int(idx))),
            ex=max(3600, int(ttl_seconds)),
        )
    except Exception:
        pass


async def _mark_retrace_warned(signal_id: str, ttl_seconds: int = 10 * 24 * 3600) -> bool:
    try:
        from core.redis_state import state
        key = _retrace_warn_cache_key(signal_id)
        if await state.cache_get(key):
            return False
        await state.cache_set(key, "1", ex=max(3600, int(ttl_seconds)))
        return True
    except Exception:
        return True


def _retrace_warning_triggered(direction: str, sl: float, best_tp_price: float, price: float, zone_pct: float = 0.20) -> bool:
    """True when price retraces into SL danger zone after at least one TP hit.

    zone_pct=0.20 means: notify when price is within 20% of distance to SL from
    the best TP that was reached.
    """
    try:
        z = min(0.9, max(0.01, float(zone_pct)))
        d = str(direction or "long").lower()
        if d == "short":
            # Example: TP=62, SL=100 -> threshold=92.4 (about 90)
            threshold = float(sl) - (float(sl) - float(best_tp_price)) * z
            return float(price) >= threshold
        threshold = float(sl) + (float(best_tp_price) - float(sl)) * z
        return float(price) <= threshold
    except Exception:
        return False
    except Exception:
        # If Redis is unavailable, allow trigger (idempotency is still mostly safe).
        return True


async def _persist_outcome(signal_id: str, status: str, entry: float, price: float) -> None:
    """Persist the outcome projection after lifecycle CAS accepted a transition."""
    try:
        from core.signal_lifecycle import outcome_transition_allowed
        from db.session import get_session
        from db.models import Outcome, Signal
        from db.priority import DBPriority
        from db.pg_features import (
            queue_outcome_notifications_for_outcome,
            upsert_outcome,
        )
        from sqlalchemy import select
        from sqlalchemy import update as sa_update
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        pct: Optional[float] = None
        r_mult: Optional[float] = None

        status_l = str(status or "").lower()
        terminal = status_l in {
            "sl", "tp3", "tp", "invalid", "time_stop", "partial_win_be",
            "missed_entry", "expired",
        }

        vip_fill_outcome = "pending"
        sentiment_outcome = "pending"

        # Fetch signal data for ML training data logging BEFORE creating session
        signal_data = None
        existing_outcome_meta: Dict[str, Any] = {}
        try:
            async with _session_scope(get_session, priority=DBPriority.CRITICAL) as _session:
                result = await _session.execute(
                    select(Signal).where(Signal.signal_id == signal_id)
                )
                signal_data = result.scalar_one_or_none()
                outcome_result = await _session.execute(
                    select(Outcome).where(Outcome.signal_id == signal_id)
                )
                existing_outcome = outcome_result.scalar_one_or_none()
                existing_outcome_meta = dict(getattr(existing_outcome, "meta", {}) or {})
        except Exception:
            pass

        tp_hit_index = int(existing_outcome_meta.get("tp_hit_index") or 0)
        if status_l.startswith("tp") and status_l != "tp":
            try:
                tp_hit_index = max(tp_hit_index, int(status_l[2:]))
            except Exception:
                pass
        elif status_l == "tp":
            tp_hit_index = max(tp_hit_index, 3)

        canonical_outcome = "pending"
        if status_l in {"tp", "tp3"}:
            canonical_outcome = "win"
        elif status_l in {"tp1", "tp2"} or (status_l == "sl" and tp_hit_index > 0):
            canonical_outcome = "partial_win"
        elif status_l == "sl":
            canonical_outcome = "loss"
        elif status_l == "time_stop":
            canonical_outcome = "time_stop"
        elif status_l == "partial_win_be":
            canonical_outcome = "partial_win"
        elif status_l in {"missed_entry", "expired"}:
            canonical_outcome = status_l

        try:
            direction = str(getattr(signal_data, "direction", "") or "").lower() if signal_data is not None else ""
            stop_loss = float(getattr(signal_data, "stop_loss", 0) or 0) if signal_data is not None else 0.0
            entry_f = float(entry or 0)
            price_f = float(price or 0)
            if entry_f > 0 and price_f > 0:
                signed_move = (entry_f - price_f) if direction == "short" else (price_f - entry_f)
                pct = (signed_move / entry_f) * 100.0
                risk_distance = abs(entry_f - stop_loss) if stop_loss > 0 else 0.0
                if risk_distance > 0:
                    r_mult = signed_move / risk_distance
                else:
                    r_mult = signed_move / (abs(entry_f) + 1e-9)
                if status_l == "sl" and r_mult is not None and r_mult > 0:
                    r_mult = -abs(r_mult)
                    pct = -abs(float(pct or 0.0))
                elif status_l in {"tp", "tp1", "tp2", "tp3"} and r_mult is not None and r_mult < 0:
                    r_mult = abs(r_mult)
                    pct = abs(float(pct or 0.0))
        except Exception:
            pass

        async with _session_scope(get_session, priority=DBPriority.CRITICAL) as session:
            # Serialize outcome projection changes. Lifecycle is authoritative,
            # and this guard prevents stale/replayed writers from downgrading it.
            locked_outcome = None
            try:
                locked_result = await session.execute(
                    select(Outcome)
                    .where(Outcome.signal_id == signal_id)
                    .with_for_update()
                )
                locked_outcome = locked_result.scalar_one_or_none()
            except Exception:
                locked_outcome = None
            current_status = str(getattr(locked_outcome, "status", "") or "").lower()
            if current_status and not outcome_transition_allowed(current_status, status_l):
                logger.info(
                    "[outcome_transition_rejected] signal=%s current=%s target=%s",
                    str(signal_id)[:8], current_status, status_l,
                )
                rollback = getattr(session, "rollback", None)
                if rollback is not None:
                    await rollback()
                return
            if locked_outcome is not None:
                locked_meta = dict(getattr(locked_outcome, "meta", {}) or {})
                existing_outcome_meta.update(locked_meta)
                tp_hit_index = max(tp_hit_index, int(locked_meta.get("tp_hit_index") or 0))
                if status_l == "sl" and tp_hit_index > 0:
                    canonical_outcome = "partial_win"

            excursion = dict(_EXCURSION_CACHE.get(str(signal_id), {}))
            outcome_meta = {
                "close_price": float(price),
                "last_event_price": float(price),
                "tp_hit_index": int(tp_hit_index),
                "tp1_hit": bool(tp_hit_index >= 1),
                "tp2_hit": bool(tp_hit_index >= 2),
                "tp3_hit": bool(tp_hit_index >= 3),
                "reversed_after_tp": bool(status_l == "sl" and tp_hit_index > 0),
                "mfe_pct": float(excursion.get("mfe_pct", existing_outcome_meta.get("mfe_pct", 0.0)) or 0.0),
                "mae_pct": float(excursion.get("mae_pct", existing_outcome_meta.get("mae_pct", 0.0)) or 0.0),
            }
            _outcome = await upsert_outcome(
                session,
                str(signal_id),
                status_l,
                r_multiple=r_mult,
                percent=pct,
                closed_at=now,
                canonical_outcome=canonical_outcome,
                vip_fill_outcome=vip_fill_outcome,
                sentiment_outcome=sentiment_outcome,
                meta=outcome_meta,
                queue_notifications=False,
            )
            await session.execute(
                sa_update(Signal)
                .where(Signal.signal_id == signal_id)
                .values(
                    mfe_pct=outcome_meta["mfe_pct"],
                    mae_pct=outcome_meta["mae_pct"],
                )
            )
            if terminal:
                # new requirement: do not archive unresolved tracked states
                # (tp1/tp2 are tracked states); archive only terminal outcomes.
                await session.execute(
                    sa_update(Signal)
                    .where(Signal.signal_id == signal_id)
                    .values(archived=True)
                )
            # Preserve the existing tier-aware fallback outbox. The canonical
            # lifecycle dispatcher cross-marks these rows after successful
            # event delivery, while upsert_outcome is told not to double-queue.
            await queue_outcome_notifications_for_outcome(
                session,
                int(getattr(_outcome, "id")),
                str(signal_id),
                status_l,
            )
            await session.commit()
            if terminal:
                _EXCURSION_CACHE.pop(str(signal_id), None)
            
            # NEW: Log to ML training data table for model retraining
            if terminal and status_l not in {"missed_entry", "expired"} and signal_data is not None:
                try:
                    from engine.ml_logger import log_ml_training_data
                    _outcome_status = canonical_outcome if canonical_outcome != "pending" else status_l
                    _ml_saved = await log_ml_training_data(
                        session,
                        signal_id=str(signal_id),
                        asset=str(getattr(signal_data, "asset", "") or ""),
                        timeframe=str(getattr(signal_data, "timeframe", "") or ""),
                        direction=str(getattr(signal_data, "direction", "") or ""),
                        entry=float(getattr(signal_data, "entry", 0) or 0),
                        stop_loss=float(getattr(signal_data, "stop_loss", 0) or 0),
                        take_profit=str(getattr(signal_data, "take_profit", "") or ""),
                        ml_probability=float(getattr(signal_data, "ml_probability", 0) or 0) if getattr(signal_data, "ml_probability", None) else None,
                        outcome_status=_outcome_status,
                        outcome_r_multiple=float(r_mult) if r_mult is not None else None,
                        outcome_percent=float(pct) if pct is not None else None,
                        outcome_meta=outcome_meta,
                        signals_created_at=getattr(signal_data, "created_at", None),
                        outcome_closed_at=now,
                    )
                    r_label = f"{float(r_mult):.2f}" if r_mult is not None else "n/a"
                    if _ml_saved:
                        logger.info(
                            "[outcome_tracker] ML training data persisted: %s outcome=%s r=%s",
                            signal_id[:8], _outcome_status, r_label,
                        )
                    else:
                        logger.warning(
                            "[outcome_tracker] ML training persistence returned false; retry required: %s outcome=%s",
                            signal_id[:8], _outcome_status,
                        )
                except Exception as _ml_train_err:
                    logger.debug(f"[outcome_tracker] ML training data logging failed: {_ml_train_err}")
            
        logger.info("[outcome_tracker] Outcome persisted: %s -> %s @ %.5f", signal_id[:8], status_l, price)
    except Exception as exc:
        logger.error("[outcome_tracker] persist_outcome error: %s", exc)


async def _notify_retrace_warning(signal: Dict[str, Any], price: float, best_tp_idx: int) -> None:
    """Notify recipients that price retraced dangerously near SL after TP progress."""
    try:
        from db.session import get_session
        from db.models import SignalDelivery, User
        from sqlalchemy import select, or_, and_, func
        from signalrank_telegram.bot import _send_message_sync
        from telegram import Bot
        from config import config

        signal_id = str(signal.get("signal_id") or "")
        if not signal_id:
            return
        asset = str(signal.get("asset") or "")
        direction = str(signal.get("direction") or "long").upper()
        sl = float(signal.get("stop_loss") or 0)

        txt = (
            "⚠️ <b>TP Retrace Warning</b>\n\n"
            f"🪙 <b>{asset}</b> {direction}\n"
            f"📊 Ref: <code>{signal_id[:8]}</code>\n"
            f"✅ Highest TP reached: <b>TP{int(best_tp_idx)}</b>\n"
            f"📉 Price retraced close to SL danger zone\n"
            f"💰 Current: <b>{float(price):.5f}</b> | SL: <b>{float(sl):.5f}</b>"
        )

        bot_token = (config.TELEGRAM_BOT_TOKEN or "").strip()
        if not bot_token:
            return
        bot = Bot(token=bot_token)

        async with get_session(priority=_outcome_db_priority(), label="engine_realtime_outcome_tracker", timeout_seconds=_outcome_db_timeout()) as session:
            rows = (
                await session.execute(
                    select(SignalDelivery, User)
                    .join(User, User.id == SignalDelivery.user_id)
                    .where(SignalDelivery.signal_id == signal_id)
                )
            ).all()
            for _delivery, user in rows:
                try:
                    _send_message_sync(bot, chat_id=int(user.telegram_user_id), text=txt, parse_mode="HTML")
                except Exception as exc:
                    logger.debug("[outcome_tracker] retrace warn user notify failed: %s", exc)
    except Exception as exc:
        logger.debug("[outcome_tracker] retrace warning send failed: %s", exc)


def _h(text: str) -> str:
    """Escape text for Telegram HTML parse_mode."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _fmt_price(price: float) -> str:
    """Format price with appropriate decimal places."""
    if price >= 1000:
        return f"{price:,.2f}"
    if price >= 1:
        return f"{price:.5f}"
    return f"{price:.8f}"


def _build_outcome_message(
    signal_id: str,
    asset: str,
    direction: str,
    entry: float,
    price: float,
    status: str,
    pnl_pct: float,
    tier_at_send: str,
) -> str:
    """Build a tier-appropriate HTML outcome message.

    Free users get a stripped-down version (signal ref + outcome label only).
    Premium/VIP users get the full PnL breakdown.
    """
    pnl_sign = "+" if pnl_pct >= 0 else ""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    status_u = status.upper()
    is_tp = status.startswith("tp")
    is_sl = status == "sl"
    tier = str(tier_at_send or "free").lower()
    is_free = tier == "free"

    from core.signal_identity import make_display_signal_id

    ref_short = _h(make_display_signal_id(signal_id))
    asset_h = _h(asset)
    dir_h = _h(direction)

    if is_tp:
        tp_level_num = 1
        try:
            if status in {"tp3", "tp"}:
                tp_level_num = 3
            elif status == "tp2":
                tp_level_num = 2
            elif status in {"tp1", "partial_tp"}:
                tp_level_num = 1
        except Exception:
            tp_level_num = 1

        suggested_sl_line = ""
        try:
            if direction.upper() == "LONG":
                if tp_level_num == 1:
                    suggested_sl = entry
                    suggested_sl_line = f"\n🛡️ Suggested SL: <code>{_h(_fmt_price(suggested_sl))}</code> (break-even)"
                elif tp_level_num == 2:
                    suggested_sl = entry + ((price - entry) * 0.5)
                    suggested_sl_line = f"\n🛡️ Suggested SL: <code>{_h(_fmt_price(suggested_sl))}</code> (lock gains)"
                else:
                    suggested_sl = price
                    suggested_sl_line = f"\n🛡️ Suggested SL: <code>{_h(_fmt_price(suggested_sl))}</code> (trail tight)"
            else:
                if tp_level_num == 1:
                    suggested_sl = entry
                    suggested_sl_line = f"\n🛡️ Suggested SL: <code>{_h(_fmt_price(suggested_sl))}</code> (break-even)"
                elif tp_level_num == 2:
                    suggested_sl = entry - ((entry - price) * 0.5)
                    suggested_sl_line = f"\n🛡️ Suggested SL: <code>{_h(_fmt_price(suggested_sl))}</code> (lock gains)"
                else:
                    suggested_sl = price
                    suggested_sl_line = f"\n🛡️ Suggested SL: <code>{_h(_fmt_price(suggested_sl))}</code> (trail tight)"
        except Exception:
            suggested_sl_line = ""

        if is_free:
            # Free: proof of result — minimal info to build trust
            return (
                f"🎯 <b>TAKE PROFIT HIT</b>\n\n"
                f"🪙 <b>{asset_h}</b> {dir_h}\n"
                f"📊 Ref: <code>{ref_short}</code>\n"
                f"\U0001F4CC Signal ID: <code>{ref_short}</code>\n"
                f"🏆 {status_u} reached!\n"
                f"{suggested_sl_line}\n"
                f"🕐 {_h(now_str)}\n\n"
                f"<i>Upgrade to Premium for full PnL details.</i>"
            )
        # Premium / VIP full message
        return (
            f"🎯🔥 <b>TAKE PROFIT HIT</b>\n\n"
            f"🪙 <b>{asset_h}</b> {dir_h}\n"
            f"📊 Ref: <code>{ref_short}</code>\n\n"
            f"\U0001F4CC Signal ID: <code>{ref_short}</code>\n"
            f"📥 Entry: <code>{_h(_fmt_price(entry))}</code>\n"
            f"💰 Close: <code>{_h(_fmt_price(price))}</code>\n"
            f"📈 ROI: <b>{_h(pnl_sign + f'{pnl_pct:.2f}%')}</b>\n\n"
            f"🏆 <b>{status_u} reached!</b>{suggested_sl_line}\n"
            f"💪 Screenshot &amp; share your win!\n"
            f"🕐 {_h(now_str)}\n\n"
            f"<i>SignalRankAI — Trade smarter.</i>"
        )

    if is_sl:
        if is_free:
            return (
                f"🛑 <b>STOP LOSS HIT</b>\n\n"
                f"🪙 <b>{asset_h}</b> {dir_h}\n"
                f"📊 Ref: <code>{ref_short}</code>\n"
                f"\U0001F4CC Signal ID: <code>{ref_short}</code>\n"
                f"🕐 {_h(now_str)}\n\n"
                f"<i>Upgrade to Premium for full details &amp; next signals.</i>"
            )
        return (
            f"🛑 <b>STOP LOSS HIT</b>\n\n"
            f"🪙 <b>{asset_h}</b> {dir_h}\n"
            f"📊 Ref: <code>{ref_short}</code>\n\n"
            f"\U0001F4CC Signal ID: <code>{ref_short}</code>\n"
            f"📥 Entry: <code>{_h(_fmt_price(entry))}</code>\n"
            f"💰 SL hit: <code>{_h(_fmt_price(price))}</code>\n"
            f"📉 Loss: <b>{_h(pnl_sign + f'{pnl_pct:.2f}%')}</b>\n\n"
            f"🔄 The next setup is loading...\n"
            f"🕐 {_h(now_str)}\n\n"
            f"<i>SignalRankAI — Risk managed.</i>"
        )

    # Generic closed status
    return (
        f"📌 <b>Signal Closed</b>\n\n"
        f"🪙 <b>{asset_h}</b> | Ref: <code>{ref_short}</code>\n"
        f"\U0001F4CC Signal ID: <code>{ref_short}</code>\n"
        f"Status: <b>{_h(status_u)}</b> @ <code>{_h(_fmt_price(price))}</code>\n"
        f"🕐 {_h(now_str)}"
    )


def _outcome_monitoring_keyboard(signal_id: str, status: str):
    """Continue/Stop controls appear only for non-terminal TP1 and TP2."""
    status_l = str(status or "").lower()
    stage = 1 if status_l in {"tp1", "partial_tp"} else (2 if status_l == "tp2" else 0)
    if stage == 0:
        return None
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    ref = str(signal_id or "")[:36]
    next_label = "Continue to TP2/TP3" if stage == 1 else "Continue to TP3"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            f"\u25b6\ufe0f {next_label}",
            callback_data=f"sigmon_continue_{stage}_{ref}",
        ),
        InlineKeyboardButton(
            f"\u23f9 Stop at TP{stage}",
            callback_data=f"sigmon_stop_{stage}_{ref}",
        ),
    ]])


async def _notify_outcome(signal: Dict[str, Any], status: str, price: float) -> None:
    """Send branded PnL notification to queued recipients (idempotent, personal-only)."""
    try:
        from db.session import get_session
        from db.models import OutcomeNotification, User
        from db.pg_features import (
            claim_outcome_notification_for_delivery,
            mark_outcome_notification_delivered,
            mark_outcome_notification_failed,
        )
        from sqlalchemy import select, or_, and_, func
        from signalrank_telegram.bot import _send_message_sync
        from telegram import Bot
        from config import config

        signal_id = str(signal["signal_id"])
        asset = str(signal["asset"])
        direction = signal.get("direction", "long").upper()
        entry = float(signal.get("entry", 0))
        status_l = str(status or "").lower()[:16]

        if direction == "LONG":
            pnl_pct = ((price - entry) / entry) * 100
        else:
            pnl_pct = ((entry - price) / entry) * 100

        # TP1 → move SL to break-even (trailing stop), done before sending messages
        if status == "tp1":
            await _apply_trailing_sl_to_breakeven(signal, price)

        # Send to all recipients of this signal only
        bot_token = (config.TELEGRAM_BOT_TOKEN or "").strip()
        if not bot_token:
            return
        bot = Bot(token=bot_token)

        async with get_session(priority=_outcome_db_priority(), label="engine_realtime_outcome_tracker", timeout_seconds=_outcome_db_timeout()) as session:
            stale_claim_seconds = max(
                60,
                int(os.getenv("OUTCOME_NOTIFICATION_CLAIM_STALE_SECONDS", "300") or 300),
            )
            stale_sending_cutoff = _utc_now_naive() - timedelta(seconds=stale_claim_seconds)
            q = (
                select(OutcomeNotification)
                .where(
                    OutcomeNotification.signal_id == signal_id,
                    OutcomeNotification.outcome_status == status_l,
                    or_(
                        OutcomeNotification.delivery_state.in_(["pending", "failed"]),
                        and_(
                            OutcomeNotification.delivery_state == "sending",
                            or_(
                                OutcomeNotification.last_attempt_at.is_(None),
                                OutcomeNotification.last_attempt_at <= stale_sending_cutoff,
                            ),
                        ),
                    ),
                )
                .order_by(OutcomeNotification.id.asc())
                .limit(500)
            )
            notifications = (await session.execute(q)).scalars().all()

            for row in notifications:
                try:
                    user_row = (
                        await session.execute(
                            select(User).where(User.telegram_user_id == int(row.telegram_user_id)).limit(1)
                        )
                    ).scalar_one_or_none()
                    if user_row is None:
                        claimed = await claim_outcome_notification_for_delivery(session, int(row.id))
                        if not claimed:
                            continue
                        await session.commit()
                        await mark_outcome_notification_failed(
                            session,
                            int(row.id),
                            error="recipient_missing",
                        )
                        await session.commit()
                        continue

                    from services.user_signal_monitoring import monitoring_allows_event
                    recipient_allowed = not (
                        bool(getattr(user_row, "is_blocked", False))
                        or bool(getattr(user_row, "is_suspended", False))
                    ) and await monitoring_allows_event(
                        session,
                        user_id=int(user_row.id),
                        signal_id=signal_id,
                        event_type=status_l,
                    )
                    if not recipient_allowed:
                        claimed = await claim_outcome_notification_for_delivery(session, int(row.id))
                        if not claimed:
                            continue
                        row.delivery_state = "suppressed"
                        row.attempt_count = int(row.attempt_count or 0) + 1
                        row.last_error = "monitoring_stopped_or_access_revoked"
                        row.updated_at = _utc_now_naive()
                        await session.commit()
                        continue

                    tier_at_send = str(getattr(row, "tier_at_send", "free") or "free").lower()
                    tp_level_num = 0
                    if status_l in {"tp1", "partial_tp"}:
                        tp_level_num = 1
                    elif status_l == "tp2":
                        tp_level_num = 2
                    elif status_l in {"tp3", "tp"}:
                        tp_level_num = 3

                    can_receive_tp = False
                    if tp_level_num > 0:
                        if tier_at_send == "free":
                            can_receive_tp = tp_level_num == 1
                        elif tier_at_send == "premium":
                            can_receive_tp = tp_level_num in {1, 2}
                        elif tier_at_send in {"vip", "admin", "owner"}:
                            can_receive_tp = tp_level_num in {1, 2, 3}
                        else:
                            can_receive_tp = False
                    if tp_level_num > 0 and not can_receive_tp:
                        claimed = await claim_outcome_notification_for_delivery(session, int(row.id))
                        if not claimed:
                            continue
                        await session.commit()
                        await mark_outcome_notification_delivered(session, int(row.id))
                        await session.commit()
                        continue

                    claimed = await claim_outcome_notification_for_delivery(session, int(row.id))
                    if not claimed:
                        continue
                    await session.commit()

                    body = _build_outcome_message(
                        signal_id=signal_id,
                        asset=asset,
                        direction=direction,
                        entry=entry,
                        price=price,
                        status=status,
                        pnl_pct=pnl_pct,
                        tier_at_send=tier_at_send,
                    )
                    if status_l in {"tp1", "partial_tp", "tp2"}:
                        body += (
                            "\n\nMonitoring will continue automatically unless you choose Stop."
                        )

                    _send_message_sync(
                        bot,
                        chat_id=int(row.telegram_user_id),
                        text=body,
                        parse_mode="HTML",
                        reply_markup=_outcome_monitoring_keyboard(signal_id, status_l),
                    )
                    await mark_outcome_notification_delivered(session, int(row.id))
                    await session.commit()
                except Exception as exc:
                    await mark_outcome_notification_failed(session, int(row.id), error=str(exc))
                    await session.commit()
                    logger.debug("[outcome_tracker] notify user %s error: %s", getattr(row, "telegram_user_id", "?"), exc)

    except Exception as exc:
        logger.error("[outcome_tracker] _notify_outcome error: %s", exc)


async def _notify_risk_free_update(signal: Dict[str, Any], price: float) -> None:
    """Broadcast one-time risk-free update when halfway to TP1 is reached."""
    try:
        from db.session import get_session
        from db.models import SignalDelivery, User
        from sqlalchemy import select
        from signalrank_telegram.bot import _send_message_sync
        from telegram import Bot
        from config import config

        signal_id = str(signal.get("signal_id") or "")
        if not signal_id:
            return

        entry = float(signal.get("entry", 0) or 0)
        asset = str(signal.get("asset", "") or "")
        timeframe = str(signal.get("timeframe", "") or "")
        direction = str(signal.get("direction", "long") or "long").upper()

        if entry > 0:
            if direction == "SHORT":
                move_pct = ((entry - float(price)) / entry) * 100.0
            else:
                move_pct = ((float(price) - entry) / entry) * 100.0
        else:
            move_pct = 0.0

        text = (
            "🛡️ <b>Risk-Free Update</b>\n\n"
            f"🪙 <b>{asset}</b> {direction} ({timeframe})\n"
            f"📊 Ref: <code>{signal_id[:8]}</code>\n"
            f"💹 Price moved <b>{move_pct:+.2f}%</b> toward TP1\n\n"
            "✅ 50% to TP1 reached — stop-loss moved to breakeven (risk-free)."
        )

        bot_token = (config.TELEGRAM_BOT_TOKEN or "").strip()
        if not bot_token:
            return
        bot = Bot(token=bot_token)

        async with get_session(priority=_outcome_db_priority(), label="engine_realtime_outcome_tracker", timeout_seconds=_outcome_db_timeout()) as session:
            rows = (
                await session.execute(
                    select(SignalDelivery, User)
                    .join(User, User.id == SignalDelivery.user_id)
                    .where(SignalDelivery.signal_id == signal_id)
                )
            ).all()
            for _delivery, user in rows:
                try:
                    _tier_at_send = str(getattr(_delivery, "tier_at_send", "free") or "free").lower()
                    if _tier_at_send not in {"premium", "vip", "admin", "owner", "free_fomo"}:
                        continue
                    if _tier_at_send == "free":
                        continue
                    if not await _mark_risk_free_recipient_triggered(int(user.telegram_user_id), signal):
                        logger.debug(
                            "[outcome_tracker] risk-free user cooldown user=%s asset=%s tf=%s direction=%s",
                            getattr(user, "telegram_user_id", "?"),
                            asset,
                            timeframe,
                            direction,
                        )
                        continue
                    _send_message_sync(bot, chat_id=int(user.telegram_user_id), text=text, parse_mode="HTML")
                except Exception as exc:
                    logger.debug("[outcome_tracker] risk-free notify user=%s error: %s", getattr(user, "id", "?"), exc)
    except Exception as exc:
        logger.debug("[outcome_tracker] risk-free notify failed: %s", exc)


async def _apply_trailing_sl_to_breakeven(signal: Dict[str, Any], tp1_price: float) -> None:
    """Move SL to break-even when TP1 is hit, via MT5 bridge and DB update."""
    signal_id = signal.get("signal_id", "")
    entry = float(signal.get("entry", 0))
    asset = signal.get("asset", "")

    # Update DB trades table SL to break-even
    try:
        from db.session import get_session
        from db.models import Trade
        from sqlalchemy import update as sa_update
        async with get_session(priority=_outcome_db_priority(), label="engine_realtime_outcome_tracker", timeout_seconds=_outcome_db_timeout()) as session:
            await session.execute(
                sa_update(Trade)
                .where(Trade.signal_id == signal_id)
                .where(Trade.status == "open")
                .values(stop_loss=entry)
            )
            await session.commit()
        logger.info("[outcome_tracker] SL moved to break-even for signal %s entry=%.5f", signal_id[:8], entry)
    except Exception as exc:
        logger.debug("[outcome_tracker] DB trailing SL update error: %s", exc)

    # If user has MT5 linked, update via MetaApi
    try:
        from db.session import get_session
        from db.models import Trade, User
        from sqlalchemy import select, join
        from services.mt5_client import update_stop_loss, get_user_mt5_account_id
        async with get_session(priority=_outcome_db_priority(), label="engine_realtime_outcome_tracker", timeout_seconds=_outcome_db_timeout()) as session:
            stmt = (
                select(Trade, User)
                .join(User, Trade.symbol == User.telegram_user_id.cast(str))
                .where(Trade.signal_id == signal_id)
                .where(Trade.status == "open")
                .limit(10)
            )
            rows = (await session.execute(stmt)).fetchall()
            for trade, user in rows:
                acct_id = await get_user_mt5_account_id(user.telegram_user_id)
                if acct_id and trade.trade_metadata.get("mt5_order_id"):
                    await update_stop_loss(
                        acct_id,
                        trade.trade_metadata["mt5_order_id"],
                        entry,
                    )
    except Exception:
        pass  # MT5 bridge is optional


class RealtimeOutcomeTracker:
    """Async task that continuously monitors open signals for TP/SL hits."""

    def __init__(self) -> None:
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._ml_retrain_task: Optional[asyncio.Task] = None
        self._last_retrain_ts: float = 0.0

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._loop(), name="outcome_tracker")
        logger.info("[outcome_tracker] Started (interval=%ds)", _check_interval())
        try:
            await self._task
        finally:
            self.running = False

    async def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._ml_retrain_task and not self._ml_retrain_task.done():
            self._ml_retrain_task.cancel()
            try:
                await self._ml_retrain_task
            except asyncio.CancelledError:
                pass
        logger.info("[outcome_tracker] Stopped")

    async def _loop(self) -> None:
        while self.running:
            try:
                await self._check_all()
            except Exception as exc:
                logger.error("[outcome_tracker] loop error: %s", exc)
            await asyncio.sleep(_check_interval())

    async def _dispatch_pending_notifications(self) -> None:
        """Run notification delivery outside lifecycle transition transactions."""
        try:
            from engine.signal_lifecycle import dispatch_pending_event_notifications

            await dispatch_pending_event_notifications(
                limit=int(os.getenv("LIFECYCLE_NOTIFICATION_RETRY_LIMIT", "100") or 100)
            )
        except Exception as exc:
            logger.debug("[lifecycle] pending notification retry skipped: %s", exc)

    async def _run_ml_retrain(self) -> None:
        try:
            from ml import train_model as _train_model

            ok = await _train_model.main()
            logger.info("[outcome_tracker] ML retraining complete (ok=%s).", bool(ok))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("[outcome_tracker] ML retraining failed: %s", exc)

    async def _check_all(self) -> None:
        signals = await _fetch_active_signals()
        logger.info("[outcome_tracker] active_scan fetched=%d", len(signals))
        # Backfill previously delivered-but-untracked signals so every delivered
        # signal eventually receives an outcome state for analytics/training.
        backfill_limit = max(0, int(os.getenv("OUTCOME_BACKFILL_SIGNAL_LIMIT", "100") or 100))
        backfill = await _fetch_delivered_untracked_signals(limit=backfill_limit)
        logger.info("[outcome_tracker] reconciliation_backfill fetched=%d", len(backfill))
        if backfill:
            known = {str(s.get("signal_id") or "") for s in signals}
            for item in backfill:
                sid = str(item.get("signal_id") or "")
                if sid and sid not in known:
                    signals.append(item)
        if not signals:
            await self._dispatch_pending_notifications()
            return

        logger.debug("[outcome_tracker] Checking %d active signals", len(signals))
        quotes = await _fetch_outcome_quotes(signals)

        # Track which users had outcomes updated
        updated_users = set()
        update_user_perf = str(
            os.getenv("OUTCOME_TRACKER_UPDATE_USER_PERF", "0") or "0"
        ).strip().lower() in {"1", "true", "yes", "y", "on"}
        max_concurrency = max(1, int(os.getenv("OUTCOME_TRACKER_MAX_CONCURRENCY", "2") or 2))
        signal_semaphore = asyncio.Semaphore(max_concurrency)

        async def wrapped_check_signal(sig):
            async with signal_semaphore:
                signal_id = str(sig.get("signal_id") or "")
                asset = str(sig.get("asset") or sig.get("symbol") or "").upper().strip()
                try:
                    await self._check_signal(sig, observation=quotes.get(asset))
                except Exception as exc:
                    logger.exception(
                        "[outcome_tracker] signal_check_failed signal=%s asset=%s error=%s",
                        signal_id,
                        asset,
                        exc,
                    )
                    return

                if not update_user_perf:
                    return

                # Update performance only for recipients with durable Telegram
                # delivery proof. Keep this lookup isolated from lifecycle work so
                # an analytics failure cannot mask a successful outcome transition.
                try:
                    from db.session import get_session
                    from db.models import SignalDelivery, User

                    async with _session_scope(get_session, noncritical=True) as session:
                        rows = await session.execute(
                            select(User.telegram_user_id)
                            .join(SignalDelivery, SignalDelivery.user_id == User.id)
                            .where(SignalDelivery.signal_id == signal_id)
                            .where(SignalDelivery.sent_ok.is_(True))
                            .where(SignalDelivery.telegram_chat_id.is_not(None))
                            .where(SignalDelivery.telegram_message_id.is_not(None))
                            .where(
                                func.lower(SignalDelivery.delivery_state).in_(
                                    _DELIVERY_PROOF_STATES
                                )
                            )
                        )
                        for (telegram_user_id,) in rows.all():
                            if telegram_user_id is not None:
                                updated_users.add(int(telegram_user_id))
                except Exception as exc:
                    logger.exception(
                        "[outcome_tracker] recipient_lookup_failed signal=%s error=%s",
                        signal_id,
                        exc,
                    )

        tasks = [wrapped_check_signal(sig) for sig in signals]
        await asyncio.gather(*tasks, return_exceptions=True)
        await self._dispatch_pending_notifications()

        # Retrain ML periodically without blocking the outcome loop or Telegram
        # callbacks. Dataset reads use reserved-capacity-aware maintenance lanes
        # and CPU fitting runs in a worker thread.
        now_ts = datetime.now(timezone.utc).timestamp()
        retrain_interval = int(os.getenv("OUTCOME_TRACKER_ML_RETRAIN_INTERVAL_SECONDS", "21600") or 21600)
        min_interval = max(900, retrain_interval)
        retrain_due = (now_ts - float(self._last_retrain_ts or 0.0)) >= float(min_interval)
        retrain_running = bool(self._ml_retrain_task and not self._ml_retrain_task.done())
        if retrain_due and not retrain_running:
            logger.info("[outcome_tracker] Scheduling ML retraining after outcome tracking...")
            self._last_retrain_ts = now_ts
            self._ml_retrain_task = asyncio.create_task(
                self._run_ml_retrain(),
                name="ml-retrain",
            )

        # Update user performance for all affected users
        if update_user_perf:
            try:
                from db.session import get_session
                from db.pg_features import get_user_performance_30d
                async with _session_scope(get_session, noncritical=True) as session:
                    for user_id in updated_users:
                        try:
                            perf = await get_user_performance_30d(session, int(user_id))
                            logger.info(f"[outcome_tracker] Updated performance for user {user_id}: {perf}")
                        except Exception as exc:
                            logger.warning(f"[outcome_tracker] Failed to update performance for user {user_id}: {exc}")
            except Exception as exc:
                logger.error(f"[outcome_tracker] Bulk user performance update failed: {exc}")

    async def _check_signal(
        self,
        signal: Dict[str, Any],
        observation: OutcomePriceObservation | None = None,
    ) -> None:
        from core.signal_lifecycle import (
            ACTIVE_TRADE,
            MISSED_ENTRY,
            TERMINAL_SIGNAL_STATES,
            WATCHING_FOR_ENTRY,
            highest_tp_for_state,
            normalize_lifecycle_state,
            outcome_status_for_lifecycle,
            outcome_transition_allowed,
        )
        from engine.signal_lifecycle import (
            entry_was_touched,
            event_state,
            record_lifecycle_event,
            update_lifecycle_observation,
        )

        symbol = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()
        signal_id = str(signal.get("signal_id") or "")
        lifecycle_state = normalize_lifecycle_state(signal.get("lifecycle_state"))
        prev_tp = int(await _get_tp_progress(signal) or 0)
        lifecycle_cas_enabled = str(
            os.getenv("OUTCOME_LIFECYCLE_ENABLED", "1") or "1"
        ).strip().lower() in {"1", "true", "yes", "on"}
        observation = observation or await _get_outcome_quote(symbol)

        async def publish_snapshot() -> None:
            await _publish_outcome_snapshot(
                signal,
                observation,
                lifecycle_state=lifecycle_state,
                highest_tp_hit=prev_tp,
            )

        # An unavailable/untrusted provider updates only the read projection;
        # it must never advance or close authoritative lifecycle state.
        if observation.price is None:
            await publish_snapshot()
            return
        price = float(observation.price)

        tp_levels = _parse_tp_levels(signal.get("take_profit"))
        if not tp_levels:
            await publish_snapshot()
            return

        entry = float(signal["entry"])
        sl = float(signal["stop_loss"])
        direction = signal.get("direction", "long")
        lifecycle_state = normalize_lifecycle_state(
            await update_lifecycle_observation(signal, price)
        )
        signal["lifecycle_state"] = lifecycle_state
        prev_tp = max(prev_tp, highest_tp_for_state(lifecycle_state))

        # Repair a missing/lagging Outcome projection after a lifecycle event
        # committed but its downstream upsert failed. Replays remain monotonic.
        projected_status = outcome_status_for_lifecycle(lifecycle_state)
        previous_status = str(signal.get("prev_outcome_status") or "").lower()
        if (
            projected_status
            and projected_status != previous_status
            and outcome_transition_allowed(previous_status, projected_status)
        ):
            projection_price = float(signal.get("lifecycle_last_price") or price)
            await _persist_outcome(signal_id, projected_status, entry, projection_price)
            signal["prev_outcome_status"] = projected_status
        if lifecycle_state in TERMINAL_SIGNAL_STATES:
            await publish_snapshot()
            return

        # Entry is authoritative. A signal cannot hit TP or SL until the market
        # has actually traded through its entry level.
        entry_gating_enabled = str(
            os.getenv("SIGNAL_ENTRY_GATING_ENABLED", "1") or "1"
        ).strip().lower() in {"1", "true", "yes", "on"}
        if entry_gating_enabled and lifecycle_state == WATCHING_FOR_ENTRY:
            expires_at = signal.get("expires_at")
            is_expired = False
            if isinstance(expires_at, datetime):
                compare_now = datetime.now(timezone.utc) if expires_at.tzinfo else _utc_now_naive()
                is_expired = compare_now >= expires_at
            if is_expired:
                accepted = await record_lifecycle_event(
                    signal, "missed_entry", price, {"reason": "entry_not_touched"}
                )
                if accepted or not lifecycle_cas_enabled:
                    lifecycle_state = MISSED_ENTRY
                    signal["lifecycle_state"] = lifecycle_state
                    await _persist_outcome(signal_id, "missed_entry", entry, price)
                await publish_snapshot()
                return
            if not entry_was_touched(direction, entry, price):
                await publish_snapshot()
                return
            if await record_lifecycle_event(signal, "entry_touched", price):
                logger.info("[outcome_tracker] Entry touched: %s price=%.5f", signal_id[:8], price)
            lifecycle_state = ACTIVE_TRADE
            signal["lifecycle_state"] = lifecycle_state
        elif not entry_gating_enabled and lifecycle_state == WATCHING_FOR_ENTRY:
            # Preserve the legacy bypass while still advancing the canonical
            # graph through its explicit activation transition.
            await record_lifecycle_event(
                signal,
                "entry_touched",
                price,
                {"reason": "entry_gating_disabled"},
            )
            lifecycle_state = ACTIVE_TRADE
            signal["lifecycle_state"] = lifecycle_state

        _record_excursion(signal_id, direction, entry, price)

        # Normalize TP ladder before any checks.
        if str(direction).lower() == "short":
            tp_levels = sorted(tp_levels, reverse=True)
        else:
            tp_levels = sorted(tp_levels)

        # Explicit risk-free trigger at 50% to TP1 (one-time per signal).
        try:
            tp1 = float(tp_levels[0])
            if _halfway_to_tp1_reached(direction, entry, tp1, price):
                if await _mark_risk_free_triggered(signal_id):
                    await _apply_trailing_sl_to_breakeven(signal, price)
                    await record_lifecycle_event(
                        signal,
                        "halfway_to_tp1",
                        price,
                        {"tp1": float(tp1), "stop_moved_to": float(entry)},
                    )
                    await _notify_risk_free_update(signal, price)
                    logger.info(
                        "[outcome_tracker] Risk-free trigger: %s halfway_to_tp1 price=%.5f entry=%.5f tp1=%.5f",
                        signal_id[:8], price, float(entry), float(tp1),
                    )
        except Exception as exc:
            logger.debug("[outcome_tracker] risk-free trigger check failed for %s: %s", signal_id[:8], exc)

        # Retrace warning after TP progress: notify once when price is within
        # 20% of SL distance from best TP reached (example short: 62->100 warns ~92.4).
        try:
            if prev_tp >= 1:
                best_tp_price = float(tp_levels[min(prev_tp - 1, len(tp_levels) - 1)])
                zone_pct = float(os.getenv("TP_RETRACE_SL_ZONE_PCT", "0.20") or 0.20)
                ml_prob = signal.get("ml_probability")
                ml_gate = float(os.getenv("TP_RETRACE_MIN_ML_CONF", "0.55") or 0.55)
                ml_allows_warning = (ml_prob is None) or (float(ml_prob) <= ml_gate)
                if ml_allows_warning and _retrace_warning_triggered(direction, sl, best_tp_price, price, zone_pct=zone_pct):
                    if await _mark_retrace_warned(signal_id):
                        await _notify_retrace_warning(signal, price, prev_tp)
                        logger.info(
                            "[outcome_tracker] Retrace warning: %s tp=%d price=%.5f sl=%.5f",
                            signal_id[:8], prev_tp, price, float(sl),
                        )
        except Exception as exc:
            logger.debug("[outcome_tracker] retrace warning check failed for %s: %s", signal_id[:8], exc)

        hit = _check_hit(direction, entry, sl, tp_levels, price)
        if hit:
            hit_l = str(hit).lower()
            logger.info(
                "[outcome_tracker] Hit detected: %s -> %s @ %.5f (entry=%.5f sl=%.5f)",
                signal_id[:8], hit_l, price, entry, sl,
            )
            if hit_l.startswith("tp"):
                try:
                    target_tp = 3 if hit_l == "tp" else int(hit_l[2:] or 0)
                except Exception:
                    target_tp = 0
                target_tp = max(0, min(3, target_tp))
                for tp_index in range(prev_tp + 1, target_tp + 1):
                    event_type = f"tp{tp_index}_hit"
                    accepted = await record_lifecycle_event(
                        signal,
                        event_type,
                        price,
                        {"highest_tp_hit": tp_index},
                    )
                    if not accepted and lifecycle_cas_enabled:
                        continue
                    await _persist_outcome(signal_id, f"tp{tp_index}", entry, price)
                    await _set_tp_progress(signal_id, tp_index)
                    prev_tp = tp_index
                    lifecycle_state = event_state(event_type)
                    signal["lifecycle_state"] = lifecycle_state
                await publish_snapshot()
                return

            event_type = "breakeven_stop" if prev_tp >= 1 else "sl_hit"
            persist_status = "partial_win_be" if prev_tp >= 1 else "sl"
            accepted = await record_lifecycle_event(
                signal,
                event_type,
                price,
                {"highest_tp_hit": prev_tp},
            )
            if accepted or not lifecycle_cas_enabled:
                lifecycle_state = event_state(event_type)
                signal["lifecycle_state"] = lifecycle_state
                await _persist_outcome(signal_id, persist_status, entry, price)
            await publish_snapshot()
            return

        # Time-stop stale unresolved delivered signals by timeframe SLA.
        try:
            tf = str(signal.get("timeframe") or "").strip().lower()
            tf_hours_default = {
                "15m": 12,
                "1h": 48,
                "4h": 7 * 24,
                "1d": 30 * 24,
            }
            force_hours = int(
                os.getenv(
                    "OUTCOME_TIME_STOP_HOURS",
                    str(tf_hours_default.get(tf, int(os.getenv("OUTCOME_FORCE_CLOSE_HOURS", "72") or 72))),
                )
                or 72
            )
        except Exception:
            force_hours = 72
        created_at = signal.get("created_at")
        try:
            if isinstance(created_at, datetime):
                now = datetime.now(timezone.utc) if created_at.tzinfo else _utc_now_naive()
                age_h = (now - created_at).total_seconds() / 3600.0
            else:
                age_h = 0.0
        except Exception:
            age_h = 0.0
        # Persist transient SLA countdown in shared cache for fast read-side visibility.
        try:
            from core.redis_state import state
            remaining_h = max(0.0, float(max(24, force_hours)) - float(age_h))
            await state.cache_set(f"sla_countdown_hours:{signal_id}", f"{remaining_h:.4f}", ex=3600)
        except Exception:
            pass
        if age_h >= float(max(24, force_hours)):
            logger.info(
                "[outcome_tracker] Time-stop stale signal %s age_h=%.1f status=time_stop",
                signal_id[:8],
                age_h,
            )
            event_type = "missed_entry" if lifecycle_state == WATCHING_FOR_ENTRY else "expired"
            persist_status = "missed_entry" if lifecycle_state == WATCHING_FOR_ENTRY else "time_stop"
            accepted = await record_lifecycle_event(signal, event_type, price, {"reason": "time_stop"})
            if accepted or not lifecycle_cas_enabled:
                lifecycle_state = event_state(event_type)
                signal["lifecycle_state"] = lifecycle_state
                await _persist_outcome(signal_id, persist_status, entry, price)
        await publish_snapshot()


# Singleton instance
outcome_tracker = RealtimeOutcomeTracker()


async def reconcile_signal_now(signal_id: str) -> bool:
    """Perform an immediate, durable lifecycle reconciliation for one signal.

    Used by interactive Telegram buttons as a read-through repair path. It
    shares the same trusted quote validation and monotonic lifecycle writer as
    the background worker, then flushes pending notifications before returning.
    """
    signal = await _fetch_signal_for_reconciliation(signal_id)
    if signal is None:
        logger.info(
            "[outcome_tracker] interactive_reconcile signal=%s found=false",
            str(signal_id or "")[:16],
        )
        return False

    observation = await _get_outcome_quote(str(signal.get("asset") or ""))
    await outcome_tracker._check_signal(signal, observation=observation)
    await outcome_tracker._dispatch_pending_notifications()
    logger.info(
        "[outcome_tracker] interactive_reconcile signal=%s found=true price=%s provider=%s trusted=%s",
        str(signal.get("signal_id") or "")[:16],
        observation.price,
        observation.provider,
        observation.provider_trusted,
    )
    return observation.price is not None and observation.provider_trusted
