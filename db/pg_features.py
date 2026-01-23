from __future__ import annotations

import hashlib
import os
import random
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import Result, Select, Subquery, Update, CursorResult, Row, and_, func, select, update, delete
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
    Outcome,
    User,
    StrategyStat,  # <-- Added import for StrategyStat
)
from db.repository import activate_subscription, get_or_create_user, normalize_tier


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


def _utcnow() -> datetime:
    # IMPORTANT: Return a timezone-aware UTC datetime.
    # Our Postgres schema uses TIMESTAMP WITHOUT TIME ZONE, but using timezone-aware objects is recommended.
    from datetime import timezone
    return datetime.now(timezone.utc)


def compute_signal_fingerprint(signal: Dict[str, Any]) -> str:
    asset: str = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()
    timeframe: str = str(signal.get("timeframe") or "").lower().strip()
    direction: str = str(signal.get("direction") or "").lower().strip()

    def _round(v: Any) -> str:
        try:
            return f"{float(v):.6f}"
        except Exception:
            return str(v)

    entry: str = _round(signal.get("entry"))
    sl: str = _round(signal.get("stop_loss") or signal.get("stop"))
    tp: Any | None = signal.get("take_profit") or signal.get("targets")
    if isinstance(tp, (list, tuple)):
        tp_norm: str = ",".join(_round(x) for x in tp)  # type: ignore
    else:
        tp_norm: str = _round(tp)

    strategy_group: str = str(signal.get("strategy_group") or "").lower().strip()
    strategy_name: str = str(signal.get("strategy_name") or signal.get("strategy") or "").lower().strip()

    raw: str = f"{asset}|{timeframe}|{direction}|{entry}|{sl}|{tp_norm}|{strategy_group}|{strategy_name}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


async def get_or_create_signal(
    session: AsyncSession,
    signal: Dict[str, Any],
    dedup_hours: int = 24,
) -> Signal:
    now: datetime = _utcnow()
    cutoff: datetime = now - timedelta(hours=max(1, int(dedup_hours)))

    asset: str = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()[:32]
    timeframe: str = str(signal.get("timeframe") or "").lower().strip()[:8]
    direction: str = str(signal.get("direction") or "").lower().strip()[:8]

    entry = float(signal.get("entry") or 0)
    stop_loss = float(signal.get("stop_loss") or signal.get("stop") or 0)

    take_profit: Any = signal.get("take_profit") or signal.get("targets") or []
    # Normalize take_profit to a list if not already a list/tuple/str
    if isinstance(take_profit, str):
        tp_str: str = take_profit
    elif isinstance(take_profit, (list, tuple)):
        tp_str = str([str(x) for x in list(take_profit or [])])
    else:
        tp_str = str([str(take_profit)])

    rr_estimate = None
    try:
        rr_estimate = float(signal.get("rr_ratio"))
    except Exception:
        rr_estimate = None

    score = float(signal.get("score") or 0)
    regime: Any | None = signal.get("regime")
    strength = float(signal.get("strength") or 0)
    ml_probability_raw: Any | None = signal.get("ml_probability")
    try:
        ml_probability: float | None = float(ml_probability_raw) if ml_probability_raw is not None else None
    except Exception:
        ml_probability = None
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


    # Strict deduplication: match by fingerprint AND all key fields (asset, timeframe, direction, entry, stop_loss, take_profit, strategy_group, strategy_name)
    res: Result[Tuple[Signal]] = await session.execute(
        select(Signal).where(
            and_(
                Signal.fingerprint == fingerprint,
                Signal.asset == asset,
                Signal.timeframe == timeframe,
                Signal.direction == direction,
                Signal.entry == entry,
                Signal.stop_loss == stop_loss,
                Signal.take_profit == tp_str,
                Signal.strategy_group == strategy_group,
                Signal.strategy_name == strategy_name,
                Signal.created_at >= cutoff
            )
        )
    )
    existing: Signal | None = res.scalars().first()
    if existing is not None:
        # Best-effort update score/strength (keep newest info)
        try:
            existing.score = max(float(existing.score or 0), float(score or 0))
            existing.strength = max(float(existing.strength or 0), float(strength or 0))
        except Exception:
            pass
        await session.flush()
        # Debug log for dedup hit
        try:
            import logging
            logging.getLogger(__name__).info(f"[dedup] Existing signal found: asset={asset} tf={timeframe} dir={direction} entry={entry} sl={stop_loss} tp={tp_str} strat={strategy_group}/{strategy_name} fp={fingerprint}")
        except Exception:
            pass
        return existing

    # Debug log for new signal creation
    try:
        import logging
        logging.getLogger(__name__).info(f"[dedup] Creating new signal: asset={asset} tf={timeframe} dir={direction} entry={entry} sl={stop_loss} tp={tp_str} strat={strategy_group}/{strategy_name} fp={fingerprint}")
    except Exception:
        pass

    # Create Signal - try with ml_probability, fallback if column missing (migration pending)
    try:
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
            strategy_name=strategy_name,
            strategy_group=strategy_group,
            strength=strength,
            fingerprint=fingerprint,
            created_at=now,
        )
    except Exception:
        # Fallback if ml_probability column doesn't exist yet
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
            strategy_name=strategy_name,
            strategy_group=strategy_group,
            strength=strength,
            fingerprint=fingerprint,
            created_at=now,
        )
    session.add(s)
    await session.flush()

    # Ensure strategy_stats has a row for this strategy.
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
) -> bool:
    user: User = await get_or_create_user(session, telegram_user_id=telegram_user_id)

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


    if cutoff is not None:
        try:
            res_sig: Result[Tuple[Signal]] = await session.execute(select(Signal).where(Signal.signal_id == str(signal_id)))
            sig: Signal | None = res_sig.scalar_one_or_none()
            if sig:
                # Strict deduplication: match by user, asset, entry, stop_loss, take_profit, timeframe, direction, strategy_group, strategy_name
                res_u: Result[Tuple[int]] = await session.execute(
                    select(func.count(SignalDelivery.id))
                    .select_from(SignalDelivery)
                    .join(Signal, Signal.signal_id == SignalDelivery.signal_id)
                    .where(
                        SignalDelivery.user_id == user.id,
                        Signal.asset == sig.asset,
                        Signal.entry == sig.entry,
                        Signal.stop_loss == sig.stop_loss,
                        Signal.take_profit == sig.take_profit,
                        Signal.timeframe == sig.timeframe,
                        Signal.direction == sig.direction,
                        Signal.strategy_group == sig.strategy_group,
                        Signal.strategy_name == sig.strategy_name,
                        SignalDelivery.delivered_at >= cutoff,
                    )
                )
                if int(res_u.scalar() or 0) > 0:
                    # Debug log for dedup hit
                    try:
                        import logging
                        logging.getLogger(__name__).info(f"[dedup] Existing delivery found: user={user.id} asset={sig.asset} tf={sig.timeframe} dir={sig.direction} entry={sig.entry} sl={sig.stop_loss} tp={sig.take_profit} strat={sig.strategy_group}/{sig.strategy_name}")
                    except Exception:
                        pass
                    return False
        except Exception:
            # If dedupe query fails, fall back to unique(user_id, signal_id) constraint.
            pass


    before: int = len(session.new)
    delivery = SignalDelivery(user_id=user.id, signal_id=signal_id, tier_at_send=tier_s, delivered_at=_utcnow())
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
    now: datetime = _utcnow()
    start: datetime = now.replace(hour=0, minute=0, second=0, microsecond=0)

    res: Result[Tuple[User]] = await session.execute(select(User).where(User.telegram_user_id == int(telegram_user_id)))
    user: User | None = res.scalar_one_or_none()
    if user is None:
        return []

    q: Select[Tuple[Signal]] = (
        select(Signal)
        .join(SignalDelivery, SignalDelivery.signal_id == Signal.signal_id)
        .where(SignalDelivery.user_id == user.id, SignalDelivery.delivered_at >= start)
        .order_by(SignalDelivery.delivered_at.desc())
    )
    res2: Result[Tuple[Signal]] = await session.execute(q)
    return list(res2.scalars().all())


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
        .where(SignalDelivery.user_id == user.id)
        .order_by(SignalDelivery.delivered_at.desc())
        .limit(max(1, int(limit)))
    )
    if asset:
        q: Select[Tuple[Signal]] = q.where(Signal.asset == str(asset).upper().strip())
    if timeframe:
        q: Select[Tuple[Signal]] = q.where(Signal.timeframe == str(timeframe).lower().strip())

    res2: Result[Tuple[Signal]] = await session.execute(q)
    return list(res2.scalars().all())


async def get_delivered_signal_by_ref(
    session: AsyncSession,
    telegram_user_id: int,
    ref: str,
) -> Signal | None:
    ref = (ref or "").strip()
    if not ref:
        return None

    res: Result[Tuple[User]] = await session.execute(select(User).where(User.telegram_user_id == int(telegram_user_id)))
    user: User | None = res.scalar_one_or_none()
    if user is None:
        return None

    q: Select[Tuple[Signal]] = (
        select(Signal)
        .join(SignalDelivery, SignalDelivery.signal_id == Signal.signal_id)
        .where(SignalDelivery.user_id == user.id)
    )
    if len(ref) >= 32:
        q: Select[Tuple[Signal]] = q.where(Signal.signal_id == ref)
    else:
        q: Select[Tuple[Signal]] = q.where(Signal.signal_id.like(f"{ref}%"))
    q: Select[Tuple[Signal]] = q.order_by(Signal.created_at.desc()).limit(1)

    res2: Result[Tuple[Signal]] = await session.execute(q)
    return res2.scalars().first()


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
) -> Outcome:
    res: Result[Tuple[Outcome]] = await session.execute(select(Outcome).where(Outcome.signal_id == str(signal_id)))
    oc: Outcome | None = res.scalars().first()
    if oc is None:
        oc = Outcome(signal_id=str(signal_id), status=str(status).lower()[:16])
        session.add(oc)
        await session.flush()
    oc.status = str(status).lower()[:16]
    if opened_at is not None and oc.opened_at is None:
        oc.opened_at = opened_at
    if closed_at is not None:
        oc.closed_at = closed_at
    elif oc.closed_at is None:
        oc.closed_at = _utcnow()
    if r_multiple is not None:
        oc.r_multiple = float(r_multiple)
    if percent is not None:
        oc.percent = float(percent)
    # Best-effort duration
    try:
        if oc.opened_at is not None and oc.closed_at is not None:
            oc.duration_seconds = int((oc.closed_at - oc.opened_at).total_seconds())
    except Exception:
        pass
    if meta:
        try:
            merged: Dict[str, Any] = dict(oc.meta or {})
            merged.update(dict(meta))
            oc.meta = merged
        except Exception:
            oc.meta = dict(meta)
    await session.flush()
    return oc


async def list_signals_missing_outcomes(
    session: AsyncSession,
    *,
    max_age_days: int = 3,
    limit: int = 50,
) -> list[Signal]:
    """Signals that were delivered to at least one user but have no Outcome row yet."""
    now: datetime = _utcnow()
    start: datetime = now - timedelta(days=max(1, int(max_age_days)))

    delivered_ids: Subquery = (
        select(SignalDelivery.signal_id)
        .where(SignalDelivery.delivered_at >= start)
        .distinct()
        .subquery()
    )

    q: Select[Tuple[Signal]] = (
        select(Signal)
        .where(
            Signal.signal_id.in_(select(delivered_ids.c.signal_id)),
            Signal.created_at >= start,
            ~select(Outcome.id).where(Outcome.signal_id == Signal.signal_id).exists(),
        )
        .order_by(Signal.created_at.asc())
        .limit(max(1, int(limit)))
    )
    res: Result[Tuple[Signal]] = await session.execute(q)
    return list(res.scalars().all())


async def list_unnotified_outcomes(session: AsyncSession, limit: int = 50) -> list[tuple[Outcome, Signal]]:
    # Keep query simple; filter meta in Python for robustness.
    res: Result[Tuple[Outcome, Signal]] = await session.execute(
        select(Outcome, Signal)
        .join(Signal, Signal.signal_id == Outcome.signal_id)
        .where(Outcome.closed_at.is_not(None))
        .order_by(Outcome.closed_at.asc())
        .limit(max(1, int(limit)))
    )
    rows: list[Row[Tuple[Outcome, Signal]]] = list(res.all())
    out: list[tuple[Outcome, Signal]] = []
    for oc, sig in rows:
        try:
            if bool((oc.meta or {}).get("notified")):
                continue
        except Exception:
            pass
        out.append((oc, sig))
    return out


async def mark_outcome_notified(session: AsyncSession, outcome_id: int) -> None:
    res: Result[Tuple[Outcome]] = await session.execute(select(Outcome).where(Outcome.id == int(outcome_id)))
    oc: Outcome | None = res.scalars().first()
    if oc is None:
        return
    meta = {}
    try:
        meta: Dict[str, Any] = dict(oc.meta or {})
    except Exception:
        meta = {}
    meta["notified"] = True
    meta["notified_at"] = _utcnow().isoformat()
    oc.meta = meta
    await session.flush()


async def get_outcome_for_signal(session: AsyncSession, signal_id: str) -> Outcome | None:
    res: Result[Tuple[Outcome]] = await session.execute(select(Outcome).where(Outcome.signal_id == str(signal_id)).order_by(Outcome.id.desc()).limit(1))
    return res.scalars().first()


async def list_delivery_recipients_for_signal(session: AsyncSession, signal_id: str) -> list[tuple[int, str]]:
    """Return list of (telegram_user_id, tier_at_send) for users who received this signal."""
    res: Result[Tuple[int, str]] = await session.execute(
        select(User.telegram_user_id, SignalDelivery.tier_at_send)
        .select_from(SignalDelivery)
        .join(User, User.id == SignalDelivery.user_id)
        .where(SignalDelivery.signal_id == str(signal_id))
        .order_by(User.telegram_user_id.asc())
    )
    return [(int(uid), str(tier)) for (uid, tier) in (res.all() or [])]


async def list_all_user_telegram_ids(session: AsyncSession) -> list[int]:
    res: Result[Tuple[int]] = await session.execute(select(User.telegram_user_id).order_by(User.telegram_user_id.asc()))
    return [int(x) for (x,) in (res.all() or [])]


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


async def get_alert_prefs(session: AsyncSession, telegram_user_id: int) -> dict:
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
    if delay_minutes is None:
        delay_minutes = _env_int("FREE_DELAY_MINUTES", 30)
    if daily_limit is None:
        daily_limit = _env_int("FREE_DAILY_LIMIT", 2)

    # Product rule: Free tier gets at most 2 delayed signals per day.
    try:
        daily_limit = min(int(daily_limit), 2)
    except Exception:
        daily_limit = 2

    now: datetime = _utcnow()
    user: User = await get_or_create_user(session, telegram_user_id=int(telegram_user_id))

    # Daily window is anchored to the user's join time (created_at), not midnight.
    # Example: if user joined at 09:24 UTC, their "day" runs 09:24 → next 09:24.
    try:
        anchor: datetime = user.created_at
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


async def get_user_performance_30d(session: AsyncSession, telegram_user_id: int) -> dict:
    """Compute 30-day performance from deliveries + outcomes.

    Returns:
      {total, wins, losses, win_rate, avg_r, net_r, tracked_outcomes, profit_loss_pct}
    """

    now: datetime = _utcnow()
    cutoff: datetime = now - timedelta(days=30)

    res: Result[Tuple[User]] = await session.execute(select(User).where(User.telegram_user_id == int(telegram_user_id)))
    user: User | None = res.scalar_one_or_none()
    if user is None:
        return {
            "total": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "avg_r": None, "net_r": None, "tracked_outcomes": 0, "profit_loss_pct": 0.0
        }

    # Total signals delivered in last 30 days
    res_total: Result[Tuple[int]] = await session.execute(
        select(func.count(SignalDelivery.id)).where(
            SignalDelivery.user_id == user.id,
            SignalDelivery.delivered_at >= cutoff,
        )
    )
    total = int(res_total.scalar() or 0)
    if total <= 0:
        return {
            "total": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "avg_r": None, "net_r": None, "tracked_outcomes": 0, "profit_loss_pct": 0.0
        }

    delivered_signal_ids_subq: Subquery = (
        select(SignalDelivery.signal_id)
        .where(SignalDelivery.user_id == user.id, SignalDelivery.delivered_at >= cutoff)
        .distinct()
        .subquery()
    )

    # Outcomes are global per signal; we only count outcomes for signals this user received.
    res_outcomes: Result[Tuple[str, int]] = await session.execute(
        select(Outcome.status, func.count(Outcome.id)).where(Outcome.signal_id.in_(select(delivered_signal_ids_subq.c.signal_id))).group_by(Outcome.status)
    )
    outcome_counts: Dict[str, int] = {str(status).lower(): int(cnt) for (status, cnt) in (res_outcomes.all() or [])}

    win_statuses: set[str] = {"tp", "tp1", "tp2", "partial_tp"}
    loss_statuses: set[str] = {"sl"}
    wins: int = sum(outcome_counts.get(s, 0) for s in win_statuses)
    losses: int = sum(outcome_counts.get(s, 0) for s in loss_statuses)
    tracked_outcomes: int = wins + losses

    win_rate: float = (wins / max(1, wins + losses)) if (wins + losses) > 0 else 0.0

    res_r: Result[Tuple[Any, float | None]] = await session.execute(
        select(func.avg(Outcome.r_multiple), func.sum(Outcome.r_multiple)).where(
            Outcome.signal_id.in_(select(delivered_signal_ids_subq.c.signal_id)),
            Outcome.r_multiple.is_not(None),
        )
    )
    avg_r, net_r = res_r.first() or (None, None)

    # Calculate profit/loss percentage: assume equal 1% risk per trade
    profit_loss_pct = 0.0
    if net_r is not None and tracked_outcomes > 0:
        risk_per_trade = 1.0  # 1% risk assumed per signal
        profit_loss_pct: float = (float(net_r) / tracked_outcomes) * risk_per_trade

    return {
        "total": int(total),
        "wins": int(wins),
        "losses": int(losses),
        "win_rate": float(win_rate),
        "avg_r": float(avg_r) if avg_r is not None else None,
        "net_r": float(net_r) if net_r is not None else None,
        "tracked_outcomes": int(tracked_outcomes),
        "profit_loss_pct": float(profit_loss_pct),
    }


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
    referrer: User = await get_or_create_user(session, telegram_user_id=int(referrer_telegram_user_id))

    res: Result[Tuple[ReferralCode]] = await session.execute(select(ReferralCode).where(ReferralCode.referrer_user_id == referrer.id))
    existing: ReferralCode | None = res.scalar_one_or_none()
    if existing is not None:
        return existing.code

    # One-time random suffix for uniqueness; referrer id included for readability.
    suffix: int = random.randint(1000, 9999)
    code: str = f"SRK{int(referrer_telegram_user_id)}{suffix}"[:32]

    rc = ReferralCode(code=code, referrer_user_id=referrer.id)
    session.add(rc)
    await session.flush()
    return rc.code


async def _count_referrals(session: AsyncSession, referrer_user_id: int) -> int:
    res: Result[Tuple[int]] = await session.execute(
        select(func.count(ReferralAttribution.id)).where(ReferralAttribution.referrer_user_id == referrer_user_id)
    )
    return int(res.scalar() or 0)


async def get_referral_progress(session: AsyncSession, referrer_telegram_user_id: int) -> dict:
    referrer: User = await get_or_create_user(session, telegram_user_id=int(referrer_telegram_user_id))
    total: int = await _count_referrals(session, referrer_user_id=referrer.id)
    toward_next: int = total % 3
    needed: int = 3 - toward_next if toward_next else 0
    return {
        "total": int(total),
        "toward_next": int(toward_next),
        "needed_for_next": int(needed),
        "reward_days_per_3": 7,
    }


async def _sum_reward_days(session: AsyncSession, referrer_user_id: int) -> int:
    res: Result[Tuple[int]] = await session.execute(
        select(func.coalesce(func.sum(ReferralReward.reward_value), 0)).where(
            ReferralReward.referrer_user_id == referrer_user_id,
            ReferralReward.reward_type == "premium_days",
        )
    )
    return int(res.scalar() or 0)


async def process_referral_start(
    session: AsyncSession,
    referred_telegram_user_id: int,
    referral_code: str,
    is_new_user: bool,
) -> dict:
    """
    Process referral when a new user starts the bot with a referral code.
    
    IMPORTANT RULES:
    1. Referrer ID is extracted from the ReferralCode linked to the referral link
    2. Referral is ONLY counted if is_new_user=True (first-time start only)
    3. Reward is distributed to the referrer_id that owns the referral code
    4. Referred user can only be attributed once (no duplicate credit)
    """
    result = {
        "status": "ignored",
        "referrer_id": None,
        "referrals_total": 0,
        "days_granted": 0,
        "referrer_notified": False,
    }

    code: str = (referral_code or "").strip()
    if not code:
        result["status"] = "invalid_code"
        return result

    # STEP 1: Look up referral code to find who created it (the referrer)
    res: Result[Tuple[ReferralCode]] = await session.execute(select(ReferralCode).where(ReferralCode.code == code))
    rc: ReferralCode | None = res.scalar_one_or_none()
    if rc is None:
        result["status"] = "invalid_code"
        return result

    # STEP 2: Get referrer details from ReferralCode.referrer_user_id
    # This ID is linked to the referral link and is used for reward distribution
    res2: Result[Tuple[User]] = await session.execute(select(User).where(User.id == rc.referrer_user_id))
    referrer_user: User | None = res2.scalar_one_or_none()
    if referrer_user is None:
        result["status"] = "invalid_code"
        return result

    referrer_tid = int(referrer_user.telegram_user_id)
    result["referrer_id"] = referrer_tid

    if int(referred_telegram_user_id) == referrer_tid:
        result["status"] = "self_referral"
        return result

    # STEP 3: CRITICAL CHECK - Only count referral if this is a NEW USER
    # Existing users using a referral code do NOT trigger referral counting
    # This ensures each user can only be counted once (at first /start)
    if not bool(is_new_user):
        result["status"] = "not_new"
        return result

    referred_user: User = await get_or_create_user(session, telegram_user_id=int(referred_telegram_user_id))

    # STEP 4: Check if this referred user was already attributed to someone else
    # Each user can only be attributed once - no duplicate referral credits
    res3: Result[Tuple[ReferralAttribution]] = await session.execute(
        select(ReferralAttribution).where(ReferralAttribution.referred_user_id == referred_user.id)
    )
    if res3.scalar_one_or_none() is not None:
        result["status"] = "already_referred"
        return result

    # STEP 5: Create referral attribution record
    # Links referred_user to referrer_user via the ReferralCode's referrer_user_id
    # This ensures proper reward distribution to the correct referrer
    attribution = ReferralAttribution(
        referred_user_id=referred_user.id,
        referrer_user_id=rc.referrer_user_id  # Referrer ID from the referral link owner
    )
    session.add(attribution)
    
    session.add(
        ReferralReward(
            referrer_user_id=rc.referrer_user_id,
            referred_user_id=referred_user.id,
            reward_type="referral_signup",
            reward_value=1,
        )
    )
    await session.flush()

    # STEP 6: Increment referrer's referral_count by 1
    # This tracks progress toward the next reward (3 referrals = 1 reward)
    # The referrer_user object is fetched from the ReferralCode, ensuring correct attribution
    referrer_user.referral_count = (referrer_user.referral_count or 0) + 1
    await session.flush()
    
    referral_count: int | None = referrer_user.referral_count
    result["referrals_total"] = int(referral_count)  # Return updated count to caller
    
    # STEP 7: Check if referrer has reached reward threshold
    # Requirement: 3 referrals (counting from 1) = 1 reward cycle
    # Referrer gets 7 premium days + count resets to 0
    REFERRAL_REQUIREMENT = 3
    has_earned_reward = (referral_count % REFERRAL_REQUIREMENT) == 0
    
    # Prepare notification message for referrer
    msg_for_referrer = None
    if has_earned_reward:
        remaining_after_reward = referral_count - REFERRAL_REQUIREMENT
        msg_for_referrer: str = (
            f"🎉 Someone joined with your referral link!\n\n"
            f"Referral count: {referral_count}\n"
            f"✅ You've reached {REFERRAL_REQUIREMENT} referrals! You earned 7 premium days.\n\n"
            f"Progress toward next reward: {remaining_after_reward}/{REFERRAL_REQUIREMENT}"
        )
    else:
        needed = REFERRAL_REQUIREMENT - (referral_count % REFERRAL_REQUIREMENT)
        msg_for_referrer: str = (
            f"👤 Someone joined with your referral link!\n\n"
            f"Referral count: {referral_count}\n"
            f"You need {needed} more referrals to earn 7 premium days."
        )
    
    result["referrer_message"] = msg_for_referrer
    
    if not has_earned_reward:
        result["status"] = "attributed"
        return result

    # REWARD LOGIC: Grant 7 premium days and reset referral_count
    from db.access import resolve_user_tier

    current_tier: str = normalize_tier(await resolve_user_tier(referrer_tid))
    tier_to_extend: str = "vip" if current_tier == "vip" else "premium"

    # Make idempotent per reward “batch”.
    reward_ref: str = f"REFERRAL:{referrer_tid}:{total // 3}"
    await activate_subscription(
        session,
        telegram_user_id=referrer_tid,
        tier=tier_to_extend,
        duration_days=int(grant_days),
        paystack_reference=reward_ref,
        meta={"source": "referral", "referred": int(referred_telegram_user_id), "batch": int(batch_number), "grant_days": grant_days},
    )

    session.add(
        ReferralReward(
            referrer_user_id=rc.referrer_user_id,
            referred_user_id=referred_user.id,
            reward_type="premium_days",
            reward_value=int(grant_days),
        )
    )
    
    # RESET referral_count after reward
    referrer_user.referral_count = 0
    await session.flush()

    result["status"] = "reward_granted"
    result["days_granted"] = int(grant_days)
    return result

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
) -> list[Signal]:
    """Return unresolved signals (no outcome yet) delivered to this user, excluding archived."""
    res: Result[Tuple[User]] = await session.execute(select(User).where(User.telegram_user_id == int(telegram_user_id)))
    user: User | None = res.scalar_one_or_none()
    if user is None:
        return []

    q: Select[Tuple[Signal]] = (
        select(Signal)
        .join(SignalDelivery, SignalDelivery.signal_id == Signal.signal_id)
        .where(
            SignalDelivery.user_id == user.id,
            Signal.archived == False,
            ~select(Outcome.id).where(Outcome.signal_id == Signal.signal_id).exists(),
        )
        .order_by(SignalDelivery.delivered_at.desc())
    )
    res2: Result[Tuple[Signal]] = await session.execute(q)
    return list(res2.scalars().all())


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


async def get_random_available_signals_for_free_user(
    session: AsyncSession,
    telegram_user_id: int,
    limit: int = 2,
) -> list[Signal]:
    """Get completely random signals that user hasn't received yet.
    
    Bot picks ANY random signals from available pool - no filtering by score,
    quality, or any other criteria. Truly random selection.
    
    Returns up to 'limit' random signals that:
    - Were created recently (last 24 hours)
    - Haven't been delivered to this user yet
    - Are still ongoing trades (no outcome recorded)
    
    Different users will get different random signals from the same pool.
    """
    user: User = await get_or_create_user(session, telegram_user_id=int(telegram_user_id))
    now: datetime = _utcnow()
    cutoff: datetime = now - timedelta(hours=24)
    
    # Get signals this user already received
    res_delivered: Result[Tuple[str]] = await session.execute(
        select(SignalDelivery.signal_id).where(SignalDelivery.user_id == user.id)
    )
    already_received: set[Any] = set(row[0] for row in res_delivered.all())
    
    # Get signals with outcomes (resolved trades)
    res_resolved: Result[Tuple[str]] = await session.execute(
        select(Outcome.signal_id).where(Outcome.signal_id.isnot(None))
    )
    resolved_signals: set[Any] = set(row[0] for row in res_resolved.all())
    
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
    available: list[Signal] = [
        s for s: Signal in all_recent 
        if s.signal_id not in already_received and s.signal_id not in resolved_signals
    ]
    
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
    already_received: set[Any] = set(row[0] for row: Row[Tuple[str]] in res_delivered.all())
    
    # Get signals with outcomes (resolved trades)
    res_resolved: Result[Tuple[str]] = await session.execute(
        select(Outcome.signal_id).where(Outcome.signal_id.isnot(None))
    )
    resolved_signals: set[Any] = set(row[0] for row: Row[Tuple[str]] in res_resolved.all())
    
    # Get highest scoring recent signal not yet delivered to user and still ongoing
    # Note: archived filtering will be applied once migration 0009 runs
    res_signal: Result[Tuple[Signal]] = await session.execute(
        select(Signal)
        .where(
            Signal.created_at >= cutoff,
            Signal.signal_id.notin_(already_received) if already_received else True,
            Signal.signal_id.notin_(resolved_signals) if resolved_signals else True,
        )
        .order_by(Signal.score.desc())
        .limit(1)
    )
    return res_signal.scalar_one_or_none()


async def queue_random_free_signals_for_all_users(
    session: AsyncSession,
) -> int:
    """Queue random signals for all FREE users who haven't reached daily limit.
    
    Called periodically to distribute signals to FREE users.
    Returns count of users who received new signals.
    """
    now: datetime = _utcnow()
    daily_limit = 2
    count = 0
    
    # Get all FREE tier users
    res_users: Result[Tuple[User]] = await session.execute(
        select(User).where(User.tier == "free")
    )
    free_users: list[User] = list(res_users.scalars().all())
    
    for user: User in free_users:
        # Check user's daily window
        try:
            anchor: datetime = user.created_at
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
        
        # Queue them
        delay_minutes: int = _env_int("FREE_DELAY_MINUTES", 30)
        for sig: Signal in random_signals:
            deliver_after: datetime = now + timedelta(minutes=delay_minutes)
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
    start_of_day: datetime = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    res: Result[Tuple[int]] = await session.execute(
        select(func.count(SignalDelivery.id)).where(
            SignalDelivery.user_id == user.id,
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
    start_of_day: datetime = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
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
        outcomes: os.Sequence[Outcome] = result.scalars().all()
        
        total: int = len(outcomes)
        wins: int = sum(1 for o: Outcome in outcomes if str(getattr(o, 'status', '')).lower() == 'tp')
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
    except Exception as e: Exception:
        # Fallback if query fails
        return {
            'win_rate': 0.0,
            'avg_rr': 1.8,
            'total_outcomes': 0,
            'wins': 0,
            'losses': 0
        }
