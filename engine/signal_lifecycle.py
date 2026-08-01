from __future__ import annotations

import html
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from core.signal_lifecycle import (
    ACTIVE_TRADE,
    BREAKEVEN_STOP,
    EXPIRED,
    MISSED_ENTRY,
    SL_HIT,
    TERMINAL_SIGNAL_STATES,
    SAME_CANDLE_AMBIGUITY_POLICY,
    TP1_HIT,
    TP2_HIT,
    TP3_HIT,
    WATCHING_FOR_ENTRY,
    event_transition_allowed,
    lifecycle_state_for_event,
    normalize_lifecycle_state,
)

logger = logging.getLogger(__name__)

TERMINAL_STATES = set(TERMINAL_SIGNAL_STATES)
NOTIFIABLE_EVENTS = {
    "entry_touched", "tp1_hit", "tp2_hit", "tp3_hit", "sl_hit",
    "breakeven_stop", "missed_entry", "expired",
}


def _enabled(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _should_queue_event_notification(event_type: str) -> bool:
    event = str(event_type or "").strip().lower()
    if event not in NOTIFIABLE_EVENTS:
        return False
    if event in {"tp1_hit", "tp2_hit", "tp3_hit", "sl_hit", "breakeven_stop"}:
        # The outcome-notification ledger owns TP/SL messages. Running both
        # dispatchers created duplicate and out-of-order Telegram alerts.
        return _enabled("LIFECYCLE_TP_SL_NOTIFICATIONS_ENABLED", False)
    return True


def entry_was_touched(
    direction: str,
    entry: float,
    current_price: float,
    *,
    high: float | None = None,
    low: float | None = None,
) -> bool:
    entry_f = float(entry)
    price_f = float(current_price)
    if high is not None and low is not None and float(low) <= entry_f <= float(high):
        return True
    return price_f >= entry_f if str(direction).lower() == "long" else price_f <= entry_f


def evaluate_observation(
    *,
    state: str,
    direction: str,
    entry: float,
    stop_loss: float,
    tp_levels: Iterable[float],
    current_price: float,
    highest_tp_hit: int = 0,
    high: float | None = None,
    low: float | None = None,
    expired: bool = False,
) -> list[str]:
    """Evaluate a price/candle observation without allowing exits before entry."""
    current_state = str(state or WATCHING_FOR_ENTRY).upper()
    if current_state in TERMINAL_STATES:
        return []
    if expired and current_state == WATCHING_FOR_ENTRY:
        return ["missed_entry"]

    events: list[str] = []
    if current_state == WATCHING_FOR_ENTRY:
        if not entry_was_touched(direction, entry, current_price, high=high, low=low):
            return []
        events.append("entry_touched")

    long_side = str(direction).lower() == "long"
    observation_high = float(high) if high is not None else float(current_price)
    observation_low = float(low) if low is not None else float(current_price)
    sl_touched = observation_low <= float(stop_loss) if long_side else observation_high >= float(stop_loss)
    if sl_touched:
        events.append("breakeven_stop" if int(highest_tp_hit or 0) >= 1 else "sl_hit")
        return events

    targets = sorted((float(value) for value in tp_levels), reverse=not long_side)
    for index, target in enumerate(targets, 1):
        if index <= int(highest_tp_hit or 0):
            continue
        reached = observation_high >= target if long_side else observation_low <= target
        if not reached:
            break
        events.append(f"tp{index}_hit" if index <= 3 else "tp3_hit")
    return events


def event_state(event_type: str) -> str:
    return lifecycle_state_for_event(event_type)


def _r_multiple(direction: str, entry: float, stop_loss: float, price: float) -> float | None:
    risk = abs(float(entry) - float(stop_loss))
    if risk <= 0:
        return None
    move = float(entry) - float(price) if str(direction).lower() == "short" else float(price) - float(entry)
    return move / risk


def _event_message(signal: dict, event_type: str, price: float, timezone_name: str, telegram_user_id: int) -> str:
    from signalrank_telegram.timezones import format_user_datetime

    asset = html.escape(str(signal.get("asset") or "Signal"))
    direction = html.escape(str(signal.get("direction") or "").upper())
    event_time = format_user_datetime(_utc_now_naive(), timezone_name, telegram_user_id, include_date=False)
    labels = {
        "entry_touched": ("Entry Triggered", "Signal is now active."),
        "tp1_hit": ("TP1 Hit", "Secure partial profit and move protection to break-even."),
        "tp2_hit": ("TP2 Hit", "Secure additional profit; TP3 remains active."),
        "tp3_hit": ("TP3 Hit", "The full target was completed."),
        "sl_hit": ("Stop Loss Hit", "Stop loss was reached before TP1."),
        "breakeven_stop": ("Protected Exit", "TP1 was reached earlier; the remainder exited near break-even."),
        "missed_entry": ("Entry Missed", "The entry was not reached before this setup expired."),
        "expired": ("Signal Expired", "This setup is no longer actionable."),
    }
    title, action = labels.get(event_type, (event_type.replace("_", " ").title(), "Lifecycle updated."))
    ref = html.escape(str(signal.get("signal_id") or signal.get("id") or "")[:12])
    ref_line = f"\nRef: <code>{ref}</code>" if ref else ""
    from core.signal_identity import public_signal_id

    ref = html.escape(public_signal_id(signal))
    ref_line = f"\n\U0001F4CC Signal ID: <code>{ref}</code>" if ref else ""
    return (
        f"<b>{html.escape(title)}</b>\n\n"
        f"<b>{asset}</b> {direction}\n"
        f"Price: <code>{float(price):.6g}</code>\n"
        f"Time: {html.escape(event_time)}{ref_line}\n\n"
        f"{html.escape(action)}"
    )


async def update_lifecycle_observation(signal: dict, price: float) -> str:
    """Create/update current lifecycle telemetry and return the persisted state."""
    if not _enabled("OUTCOME_LIFECYCLE_ENABLED", True):
        return ACTIVE_TRADE
    from db.models import SignalLifecycle, SignalTrackingEvent
    from db.priority import DBPriority
    from db.session import get_session
    from sqlalchemy import func, select

    signal_id = str(signal.get("signal_id") or "")
    now = _utc_now_naive()
    entry = float(signal.get("entry") or 0)
    stop = float(signal.get("stop_loss") or 0)
    direction = str(signal.get("direction") or "long")
    risk = abs(entry - stop)
    signed_move = entry - float(price) if direction.lower() == "short" else float(price) - entry
    pct = (signed_move / entry * 100.0) if entry > 0 else 0.0
    r_value = (signed_move / risk) if risk > 0 else 0.0

    async with get_session(priority=DBPriority.CRITICAL) as session:
        row = (await session.execute(
            select(SignalLifecycle)
            .where(SignalLifecycle.signal_id == signal_id)
            .with_for_update()
        )).scalar_one_or_none()
        if row is None:
            row = SignalLifecycle(
                signal_id=signal_id,
                state=WATCHING_FOR_ENTRY,
                generated_at=signal.get("created_at"),
                watch_started_at=now,
            )
            session.add(row)
            session.add(SignalTrackingEvent(
                signal_id=signal_id,
                event_type="generated",
                event_time=signal.get("created_at") or now,
                price=None,
                meta={"state": WATCHING_FOR_ENTRY},
            ))
        row.state = normalize_lifecycle_state(getattr(row, "state", None))
        row.last_price = float(price)
        row.last_checked_at = now
        row.max_price_seen = max(float(row.max_price_seen or price), float(price))
        row.min_price_seen = min(float(row.min_price_seen or price), float(price))
        row.mfe_pct = max(float(row.mfe_pct or 0.0), pct, 0.0)
        row.mae_pct = min(float(row.mae_pct or 0.0), pct, 0.0)
        row.mfe_r = max(float(row.mfe_r or 0.0), r_value, 0.0)
        row.mae_r = min(float(row.mae_r or 0.0), r_value, 0.0)
        row.updated_at = now
        await session.commit()
        return normalize_lifecycle_state(row.state)


async def record_lifecycle_event(signal: dict, event_type: str, price: float, meta: dict | None = None) -> bool:
    """Persist one lifecycle transition and queue one notification per confirmed recipient."""
    if not _enabled("OUTCOME_LIFECYCLE_ENABLED", True):
        return False
    from db.models import (
        SignalDelivery, SignalEventNotification, SignalLifecycle,
        SignalTrackingEvent, User,
    )
    from db.priority import DBPriority
    from db.session import get_session
    from sqlalchemy import func, select

    signal_id = str(signal.get("signal_id") or "")
    if not signal_id:
        return False
    now = _utc_now_naive()
    created_at = signal.get("created_at")
    async with get_session(priority=DBPriority.CRITICAL) as session:
        lifecycle = (await session.execute(
            select(SignalLifecycle)
            .where(SignalLifecycle.signal_id == signal_id)
            .with_for_update()
        )).scalar_one_or_none()
        if lifecycle is None:
            lifecycle = SignalLifecycle(
                signal_id=signal_id,
                state=WATCHING_FOR_ENTRY,
                generated_at=created_at,
                watch_started_at=now,
            )
            session.add(lifecycle)
            await session.flush()

        lifecycle.state = normalize_lifecycle_state(getattr(lifecycle, "state", None))
        existing = (await session.execute(
            select(SignalTrackingEvent).where(
                SignalTrackingEvent.signal_id == signal_id,
                SignalTrackingEvent.event_type == event_type,
            )
        )).scalar_one_or_none()
        was_new = existing is None

        if existing is None:
            if not event_transition_allowed(lifecycle.state, event_type):
                logger.info(
                    "[lifecycle_transition_rejected] signal=%s current=%s event=%s target=%s",
                    signal_id[:8], lifecycle.state, event_type, event_state(event_type),
                )
                await session.rollback()
                return False
            r_value = _r_multiple(
                str(signal.get("direction") or "long"),
                float(signal.get("entry") or 0),
                float(signal.get("stop_loss") or 0),
                float(price),
            )
            event_meta = dict(meta or {})
            event_meta.setdefault("same_candle_policy", SAME_CANDLE_AMBIGUITY_POLICY)
            try:
                import os
                clip_min = float(os.getenv("TRAINING_R_CLIP_MIN", "-5") or -5)
                clip_max = float(os.getenv("TRAINING_R_CLIP_MAX", "10") or 10)
                event_meta["raw_r"] = r_value
                event_meta["clipped_r"] = (
                    min(clip_max, max(clip_min, r_value)) if r_value is not None else None
                )
            except Exception:
                event_meta["raw_r"] = r_value
            for key in (
                "regime", "session", "spread", "order_book_imbalance",
                "funding_rate", "open_interest_delta", "open_interest_change",
            ):
                value = signal.get(key)
                if value is None and isinstance(signal.get("_macro"), dict):
                    value = signal["_macro"].get(key)
                if value is not None:
                    event_meta.setdefault(key, value)
            existing = SignalTrackingEvent(
                signal_id=signal_id,
                event_type=event_type,
                event_time=now,
                price=float(price),
                r_multiple=r_value,
                meta=event_meta,
            )
            session.add(existing)
            await session.flush()

            lifecycle.state = event_state(event_type)
            tp_stage = {"tp1_hit": 1, "tp2_hit": 2, "tp3_hit": 3}.get(event_type, 0)
            lifecycle.highest_tp_hit = max(int(lifecycle.highest_tp_hit or 0), int(tp_stage))
            if lifecycle.state in TERMINAL_STATES:
                lifecycle.terminal_event_type = event_type
                lifecycle.terminal_event_id = int(existing.id)
                lifecycle.terminal_price = float(price)
                lifecycle.terminal_evidence = dict(event_meta)
            lifecycle.last_price = float(price)
            lifecycle.last_checked_at = now
            lifecycle.updated_at = now
            field_map = {
                "entry_touched": "entry_touched_at", "tp1_hit": "tp1_hit_at",
                "tp2_hit": "tp2_hit_at", "tp3_hit": "tp3_hit_at",
                "sl_hit": "sl_hit_at", "breakeven_stop": "breakeven_at",
                "missed_entry": "expired_at", "expired": "expired_at",
            }
            timestamp_field = field_map.get(event_type)
            if timestamp_field:
                setattr(lifecycle, timestamp_field, now)
            if event_type == "entry_touched" and created_at:
                lifecycle.entry_latency_seconds = max(0, int((now - created_at).total_seconds()))
            base = lifecycle.entry_touched_at or created_at
            if base:
                seconds = max(0, int((now - base).total_seconds()))
                duration_field = {
                    "tp1_hit": "time_to_tp1_seconds", "tp2_hit": "time_to_tp2_seconds",
                    "tp3_hit": "time_to_tp3_seconds", "sl_hit": "time_to_sl_seconds",
                }.get(event_type)
                if duration_field:
                    setattr(lifecycle, duration_field, seconds)
            if event_type.startswith("tp1"):
                lifecycle.tp1_before_sl = True
            if event_type.startswith("tp2"):
                lifecycle.tp2_before_sl = True
            if event_type.startswith("tp3"):
                lifecycle.tp3_before_sl = True
            if event_type in {"sl_hit", "breakeven_stop"}:
                lifecycle.reversed_after_tp1 = bool(lifecycle.tp1_hit_at)
            if lifecycle.state in TERMINAL_STATES:
                lifecycle.closed_at = now

        deliveries = []
        if _should_queue_event_notification(event_type):
            deliveries = (await session.execute(
            select(SignalDelivery, User)
            .join(User, User.id == SignalDelivery.user_id)
            .where(
                SignalDelivery.signal_id == signal_id,
                SignalDelivery.sent_ok.is_(True),
                func.lower(SignalDelivery.delivery_state).in_(("sent", "confirmed", "delivered", "reconciled")),
            )
            )).all()
        from services.user_signal_monitoring import monitoring_allows_event
        for delivery, user in deliveries:
            if not await monitoring_allows_event(
                session,
                user_id=int(user.id),
                signal_id=signal_id,
                event_type=event_type,
            ):
                continue
            already = (await session.execute(
                select(SignalEventNotification.id).where(
                    SignalEventNotification.signal_id == signal_id,
                    SignalEventNotification.event_type == event_type,
                    SignalEventNotification.user_id == user.id,
                )
            )).scalar_one_or_none()
            if already is None:
                session.add(SignalEventNotification(
                    event_id=existing.id,
                    signal_id=signal_id,
                    event_type=event_type,
                    user_id=user.id,
                    telegram_user_id=user.telegram_user_id,
                    delivery_id=delivery.id,
                    chat_id=delivery.telegram_chat_id or user.telegram_user_id,
                    source_message_id=delivery.telegram_message_id,
                ))
        await session.commit()
        event_id = int(existing.id)

    # Telegram delivery is intentionally owned by the separate notification
    # dispatcher. The critical lifecycle transaction ends before network I/O.
    logger.info("[lifecycle] signal=%s event=%s price=%.6g new=%s", signal_id[:8], event_type, price, was_new)
    return was_new


def _lifecycle_notification_keyboard(signal_id: object):
    """Build durable navigation controls for proactive lifecycle alerts."""
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        ref = str(signal_id or "").strip()[:36]
        if not ref:
            return None
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📈 Monitor", callback_data=f"monitor_signal_{ref}"),
                InlineKeyboardButton("📋 Open Signal", callback_data=f"open_signal_{ref}"),
            ],
            [
                InlineKeyboardButton("🔎 Check Outcome", callback_data=f"check_outcome_{ref}"),
            ],
        ])
    except Exception:
        return None


async def claim_event_notification(notification_id: int, *, stale_after_seconds: int = 300) -> bool:
    """Atomically reserve one lifecycle outbox row before Telegram network I/O."""
    from datetime import timedelta
    from db.models import SignalEventNotification
    from db.session import get_session
    from sqlalchemy import and_, or_, update

    now = _utc_now_naive()
    stale_cutoff = now - timedelta(seconds=max(60, int(stale_after_seconds)))
    async with get_session(priority="critical", label="lifecycle.notification.claim", timeout_seconds=12) as session:
        claimed = (await session.execute(
            update(SignalEventNotification)
            .where(
                SignalEventNotification.id == int(notification_id),
                or_(
                    SignalEventNotification.delivery_state.in_(["pending", "failed"]),
                    and_(
                        SignalEventNotification.delivery_state == "sending",
                        or_(
                            SignalEventNotification.last_attempt_at.is_(None),
                            SignalEventNotification.last_attempt_at <= stale_cutoff,
                        ),
                    ),
                ),
            )
            .values(
                delivery_state="sending",
                last_attempt_at=now,
                updated_at=now,
            )
            .returning(SignalEventNotification.id)
        )).scalar_one_or_none()
        await session.commit()
        return claimed is not None


async def dispatch_event_notifications(event_id: int, signal: dict) -> None:
    if not _enabled("LIFECYCLE_EVENT_NOTIFICATIONS_ENABLED", True):
        return
    from config import config
    from db.models import AlertPreference, OutcomeNotification, SignalEventNotification, SignalTrackingEvent, User
    from db.session import get_session
    from sqlalchemy import and_, or_, select
    from telegram import Bot

    token = str(config.TELEGRAM_BOT_TOKEN or "").strip()
    if not token:
        return
    stale_cutoff = _utc_now_naive() - timedelta(seconds=int(os.getenv("LIFECYCLE_NOTIFICATION_CLAIM_STALE_SECONDS", "300") or 300))
    async with get_session(priority="critical", label="lifecycle.notification", timeout_seconds=12) as session:
        event = await session.get(SignalTrackingEvent, event_id)
        event_price = float(getattr(event, "price", 0) or signal.get("entry") or 0)
        rows = (await session.execute(
            select(SignalEventNotification, User, AlertPreference)
            .join(User, User.id == SignalEventNotification.user_id)
            .outerjoin(AlertPreference, AlertPreference.user_id == User.id)
            .where(
                SignalEventNotification.event_id == event_id,
                SignalEventNotification.sent_ok.is_(False),
                or_(
                    SignalEventNotification.delivery_state.in_(["pending", "failed"]),
                    and_(
                        SignalEventNotification.delivery_state == "sending",
                        or_(
                            SignalEventNotification.last_attempt_at.is_(None),
                            SignalEventNotification.last_attempt_at <= stale_cutoff,
                        ),
                    ),
                ),
            )
        )).all()
    if not rows:
        return

    bot = Bot(token=token)
    for notification, user, preference in rows:
        if preference is not None and not bool(preference.tp_sl_enabled):
            async with get_session(priority="critical", label="lifecycle.notification", timeout_seconds=12) as session:
                suppressed = await session.get(SignalEventNotification, notification.id)
                if suppressed is not None:
                    suppressed.delivery_state = "suppressed"
                    suppressed.error = "user_alert_preference_disabled"
                    await session.commit()
            continue
        if preference is not None and preference.quiet_start_hour is not None and preference.quiet_end_hour is not None:
            try:
                from zoneinfo import ZoneInfo
                from signalrank_telegram.timezones import effective_user_timezone

                local_hour = datetime.now(timezone.utc).astimezone(
                    ZoneInfo(effective_user_timezone(user.timezone, user.telegram_user_id))
                ).hour
                start = int(preference.quiet_start_hour)
                end = int(preference.quiet_end_hour)
                in_quiet_hours = (start <= local_hour < end) if start < end else (local_hour >= start or local_hour < end)
                if in_quiet_hours:
                    continue
            except Exception:
                pass
        if not await claim_event_notification(
            int(notification.id),
            stale_after_seconds=int(os.getenv("LIFECYCLE_NOTIFICATION_CLAIM_STALE_SECONDS", "300") or 300),
        ):
            continue
        text = _event_message(
            signal, notification.event_type, event_price,
            str(user.timezone or ""), int(user.telegram_user_id),
        )
        sent_message_id = None
        error = None
        try:
            if not _should_queue_event_notification(notification.event_type):
                async with get_session(priority="critical", label="lifecycle.notification", timeout_seconds=12) as session:
                    suppressed = await session.get(SignalEventNotification, notification.id)
                    if suppressed is not None:
                        suppressed.delivery_state = "suppressed"
                        suppressed.error = "owned_by_outcome_notification_dispatcher"
                        await session.commit()
                continue

            chat_id = int(notification.chat_id or user.telegram_user_id)
            send_kwargs = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": _lifecycle_notification_keyboard(notification.signal_id),
                "disable_notification": False,
            }
            if notification.source_message_id:
                send_kwargs.update({
                    "reply_to_message_id": int(notification.source_message_id),
                    "allow_sending_without_reply": True,
                })
            try:
                result = await bot.send_message(**send_kwargs)
            except TypeError:
                # Compatibility with older python-telegram-bot wrappers.
                send_kwargs.pop("allow_sending_without_reply", None)
                result = await bot.send_message(**send_kwargs)
            sent_message_id = int(getattr(result, "message_id", 0) or 0) or None
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:1000]

        async with get_session(priority="critical", label="lifecycle.notification", timeout_seconds=12) as session:
            row = await session.get(SignalEventNotification, notification.id)
            if row is None:
                continue
            row.sent_ok = error is None and sent_message_id is not None
            row.delivery_state = "sent" if row.sent_ok else "failed"
            row.sent_message_id = sent_message_id
            row.sent_at = _utc_now_naive() if row.sent_ok else None
            row.error = error
            row.attempt_count = int(row.attempt_count or 0) + 1
            row.last_attempt_at = _utc_now_naive()
            row.updated_at = _utc_now_naive()
            if row.sent_ok:
                outcome_status = {
                    "tp1_hit": "tp1", "tp2_hit": "tp2", "tp3_hit": "tp3",
                    "sl_hit": "sl", "breakeven_stop": "partial_win_be",
                    "missed_entry": "missed_entry", "expired": "expired",
                }.get(row.event_type)
                if outcome_status:
                    pending = (await session.execute(
                        select(OutcomeNotification).where(
                            OutcomeNotification.signal_id == row.signal_id,
                            OutcomeNotification.telegram_user_id == row.telegram_user_id,
                            OutcomeNotification.outcome_status == outcome_status,
                        )
                    )).scalars().all()
                    for fallback in pending:
                        fallback.delivery_state = "delivered"
                        fallback.delivered_at = _utc_now_naive()
            await session.commit()

    async with get_session(priority="critical", label="lifecycle.notification", timeout_seconds=12) as session:
        remaining = (await session.execute(
            select(SignalEventNotification.id).where(
                SignalEventNotification.event_id == event_id,
                SignalEventNotification.sent_ok.is_(False),
                SignalEventNotification.delivery_state.in_(["pending", "failed", "sending"]),
            )
        )).first()
        if remaining is None:
            event = await session.get(SignalTrackingEvent, event_id)
            if event is not None:
                event.notified_at = _utc_now_naive()
                await session.commit()


async def dispatch_pending_event_notifications(limit: int = 100) -> int:
    """Retry event notifications deferred by quiet hours or transient failures."""
    if not _enabled("LIFECYCLE_EVENT_NOTIFICATIONS_ENABLED", True):
        return 0
    from db.models import Signal, SignalEventNotification
    from db.session import get_session
    from sqlalchemy import and_, or_, select

    async with get_session(priority="critical", label="lifecycle.notification", timeout_seconds=12) as session:
        stale_cutoff = _utc_now_naive() - timedelta(seconds=int(os.getenv("LIFECYCLE_NOTIFICATION_CLAIM_STALE_SECONDS", "300") or 300))
        rows = (await session.execute(
            select(SignalEventNotification.event_id, Signal)
            .join(Signal, Signal.signal_id == SignalEventNotification.signal_id)
            .where(
                SignalEventNotification.sent_ok.is_(False),
                or_(
                    SignalEventNotification.delivery_state.in_(["pending", "failed"]),
                    and_(
                        SignalEventNotification.delivery_state == "sending",
                        or_(
                            SignalEventNotification.last_attempt_at.is_(None),
                            SignalEventNotification.last_attempt_at <= stale_cutoff,
                        ),
                    ),
                ),
            )
            .order_by(SignalEventNotification.created_at.asc())
            .limit(max(1, int(limit)))
        )).all()
    dispatched = 0
    seen: set[int] = set()
    for event_id, row in rows:
        if int(event_id) in seen:
            continue
        seen.add(int(event_id))
        signal = {column.key: getattr(row, column.key, None) for column in row.__table__.columns}
        await dispatch_event_notifications(int(event_id), signal)
        dispatched += 1
    return dispatched
