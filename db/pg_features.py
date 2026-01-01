from __future__ import annotations

import hashlib
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    AlertPreference,
    FreeSignalQueue,
    ReferralAttribution,
    ReferralCode,
    ReferralReward,
    Signal,
    SignalDelivery,
    Outcome,
    User,
)
from db.repository import activate_subscription, get_or_create_user, normalize_tier


def _env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or str(default)).strip())
    except Exception:
        return default


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def compute_signal_fingerprint(signal: Dict[str, Any]) -> str:
    asset = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()
    timeframe = str(signal.get("timeframe") or "").lower().strip()
    direction = str(signal.get("direction") or "").lower().strip()

    def _round(v: Any) -> str:
        try:
            return f"{float(v):.6f}"
        except Exception:
            return str(v)

    entry = _round(signal.get("entry"))
    sl = _round(signal.get("stop_loss") or signal.get("stop"))
    tp = signal.get("take_profit") or signal.get("targets")
    tp_norm = tp
    if isinstance(tp, (list, tuple)):
        tp_norm = ",".join(_round(x) for x in tp)
    else:
        tp_norm = _round(tp)

    strategy_group = str(signal.get("strategy_group") or "").lower().strip()
    strategy_name = str(signal.get("strategy_name") or signal.get("strategy") or "").lower().strip()

    raw = f"{asset}|{timeframe}|{direction}|{entry}|{sl}|{tp_norm}|{strategy_group}|{strategy_name}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


async def get_or_create_signal(
    session: AsyncSession,
    signal: Dict[str, Any],
    dedup_hours: int = 24,
) -> Signal:
    now = _utcnow()
    cutoff = now - timedelta(hours=max(1, int(dedup_hours)))

    asset = str(signal.get("asset") or signal.get("symbol") or "").upper().strip()[:32]
    timeframe = str(signal.get("timeframe") or "").lower().strip()[:8]
    direction = str(signal.get("direction") or "").lower().strip()[:8]

    entry = float(signal.get("entry") or 0)
    stop_loss = float(signal.get("stop_loss") or signal.get("stop") or 0)

    take_profit = signal.get("take_profit") or signal.get("targets") or []
    # Persist TP as JSON-ish string (keeps current schema stable)
    if isinstance(take_profit, str):
        tp_str = take_profit
    elif isinstance(take_profit, (list, tuple)):
        tp_str = str(list(take_profit))
    else:
        tp_str = str([take_profit])

    rr_estimate = None
    try:
        rr_estimate = float(signal.get("rr_ratio"))
    except Exception:
        rr_estimate = None

    score = float(signal.get("score") or 0)
    regime = signal.get("regime")
    strength = float(signal.get("strength") or 0)
    strategy_name = str(signal.get("strategy_name") or signal.get("strategy") or "unknown")[:64]
    strategy_group = str(signal.get("strategy_group") or "unknown")[:32]

    fingerprint = compute_signal_fingerprint(
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

    res = await session.execute(
        select(Signal).where(and_(Signal.fingerprint == fingerprint, Signal.created_at >= cutoff))
    )
    existing = res.scalars().first()
    if existing is not None:
        # Best-effort update score/strength (keep newest info)
        try:
            existing.score = max(float(existing.score or 0), float(score or 0))
            existing.strength = max(float(existing.strength or 0), float(strength or 0))
        except Exception:
            pass
        await session.flush()
        return existing

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
    return s


async def record_signal_delivery(
    session: AsyncSession,
    telegram_user_id: int,
    signal_id: str,
    tier_at_send: str,
) -> bool:
    user = await get_or_create_user(session, telegram_user_id=telegram_user_id)

    before = len(session.new)
    delivery = SignalDelivery(user_id=user.id, signal_id=signal_id, tier_at_send=normalize_tier(tier_at_send))
    session.add(delivery)
    try:
        await session.flush()
        return True
    except Exception:
        # Unique constraint hit or other issue: treat as already delivered
        await session.rollback()
        return False
    finally:
        _ = before


async def list_signals_sent_today(
    session: AsyncSession,
    telegram_user_id: int,
) -> list[Signal]:
    now = _utcnow()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    res = await session.execute(select(User).where(User.telegram_user_id == int(telegram_user_id)))
    user = res.scalar_one_or_none()
    if user is None:
        return []

    q = (
        select(Signal)
        .join(SignalDelivery, SignalDelivery.signal_id == Signal.signal_id)
        .where(SignalDelivery.user_id == user.id, SignalDelivery.delivered_at >= start)
        .order_by(SignalDelivery.delivered_at.desc())
    )
    res2 = await session.execute(q)
    return list(res2.scalars().all())


async def list_all_user_telegram_ids(session: AsyncSession) -> list[int]:
    res = await session.execute(select(User.telegram_user_id).order_by(User.telegram_user_id.asc()))
    return [int(x) for (x,) in (res.all() or [])]


async def get_alert_prefs(session: AsyncSession, telegram_user_id: int) -> dict:
    user = await get_or_create_user(session, telegram_user_id=int(telegram_user_id))
    res = await session.execute(select(AlertPreference).where(AlertPreference.user_id == user.id))
    pref = res.scalar_one_or_none()
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
    user = await get_or_create_user(session, telegram_user_id=int(telegram_user_id))
    res = await session.execute(select(AlertPreference).where(AlertPreference.user_id == user.id))
    pref = res.scalar_one_or_none()
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

    now = _utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    user = await get_or_create_user(session, telegram_user_id=int(telegram_user_id))

    # Enforce per-day cap (queued + sent)
    res = await session.execute(
        select(func.count(FreeSignalQueue.id)).where(
            FreeSignalQueue.user_id == user.id,
            FreeSignalQueue.date >= today_start,
            FreeSignalQueue.date < today_end,
            FreeSignalQueue.status.in_(["queued", "sent"]),
        )
    )
    already = int(res.scalar() or 0)
    if already >= int(daily_limit):
        return False

    s = await get_or_create_signal(session, signal)

    # Dedupe: do not queue the exact same signal more than once per user/day.
    res_dupe = await session.execute(
        select(func.count(FreeSignalQueue.id)).where(
            FreeSignalQueue.user_id == user.id,
            FreeSignalQueue.date >= today_start,
            FreeSignalQueue.date < today_end,
            FreeSignalQueue.signal_id == s.signal_id,
            FreeSignalQueue.status.in_("queued", "sent"),
        )
    )
    if int(res_dupe.scalar() or 0) > 0:
        return True

    deliver_after = now + timedelta(minutes=max(0, int(delay_minutes)))
    q = FreeSignalQueue(
        user_id=user.id,
        date=today_start,
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
    """Compute simple 30-day performance from deliveries + outcomes.

    Returns:
      {total, wins, losses, win_rate, avg_r, net_r}
    """

    now = _utcnow()
    cutoff = now - timedelta(days=30)

    res = await session.execute(select(User).where(User.telegram_user_id == int(telegram_user_id)))
    user = res.scalar_one_or_none()
    if user is None:
        return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "avg_r": None, "net_r": None}

    # Total signals delivered in last 30 days
    res_total = await session.execute(
        select(func.count(SignalDelivery.id)).where(
            SignalDelivery.user_id == user.id,
            SignalDelivery.delivered_at >= cutoff,
        )
    )
    total = int(res_total.scalar() or 0)
    if total <= 0:
        return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "avg_r": None, "net_r": None}

    delivered_signal_ids_subq = (
        select(SignalDelivery.signal_id)
        .where(SignalDelivery.user_id == user.id, SignalDelivery.delivered_at >= cutoff)
        .distinct()
        .subquery()
    )

    # Outcomes are global per signal; we only count outcomes for signals this user received.
    res_outcomes = await session.execute(
        select(Outcome.status, func.count(Outcome.id)).where(Outcome.signal_id.in_(select(delivered_signal_ids_subq.c.signal_id))).group_by(Outcome.status)
    )
    outcome_counts = {str(status).lower(): int(cnt) for (status, cnt) in (res_outcomes.all() or [])}

    win_statuses = {"tp", "tp1", "tp2", "partial_tp"}
    loss_statuses = {"sl"}
    wins = sum(outcome_counts.get(s, 0) for s in win_statuses)
    losses = sum(outcome_counts.get(s, 0) for s in loss_statuses)

    win_rate = (wins / max(1, wins + losses)) if (wins + losses) > 0 else 0.0

    res_r = await session.execute(
        select(func.avg(Outcome.r_multiple), func.sum(Outcome.r_multiple)).where(
            Outcome.signal_id.in_(select(delivered_signal_ids_subq.c.signal_id)),
            Outcome.r_multiple.is_not(None),
        )
    )
    avg_r, net_r = res_r.first() or (None, None)
    return {
        "total": int(total),
        "wins": int(wins),
        "losses": int(losses),
        "win_rate": float(win_rate),
        "avg_r": float(avg_r) if avg_r is not None else None,
        "net_r": float(net_r) if net_r is not None else None,
    }


async def get_due_free_signal_summaries(session: AsyncSession) -> dict[int, list[dict]]:
    now = _utcnow()
    res = await session.execute(
        select(FreeSignalQueue, User.telegram_user_id)
        .join(User, User.id == FreeSignalQueue.user_id)
        .where(FreeSignalQueue.status == "queued", FreeSignalQueue.deliver_after <= now)
        .order_by(User.telegram_user_id.asc(), FreeSignalQueue.score.desc())
    )
    rows = list(res.all())
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
    now = _utcnow()
    stmt = (
        update(FreeSignalQueue)
        .where(FreeSignalQueue.id.in_([int(x) for x in ids]))
        .values(sent_at=now, status=str(status)[:16])
    )
    await session.execute(stmt)
    await session.flush()


async def expire_old_free_signal_summaries(session: AsyncSession, max_age_hours: int = 24) -> int:
    cutoff = _utcnow() - timedelta(hours=int(max_age_hours))
    stmt = (
        update(FreeSignalQueue)
        .where(FreeSignalQueue.status == "queued", FreeSignalQueue.queued_at < cutoff)
        .values(status="expired")
    )
    res = await session.execute(stmt)
    await session.flush()
    return int(getattr(res, "rowcount", 0) or 0)


async def get_or_create_referral_code(session: AsyncSession, referrer_telegram_user_id: int) -> str:
    referrer = await get_or_create_user(session, telegram_user_id=int(referrer_telegram_user_id))

    res = await session.execute(select(ReferralCode).where(ReferralCode.referrer_user_id == referrer.id))
    existing = res.scalar_one_or_none()
    if existing is not None:
        return existing.code

    # One-time random suffix for uniqueness; referrer id included for readability.
    suffix = random.randint(1000, 9999)
    code = f"SRK{int(referrer_telegram_user_id)}{suffix}"[:32]

    rc = ReferralCode(code=code, referrer_user_id=referrer.id)
    session.add(rc)
    await session.flush()
    return rc.code


async def _count_referrals(session: AsyncSession, referrer_user_id: int) -> int:
    res = await session.execute(
        select(func.count(ReferralAttribution.id)).where(ReferralAttribution.referrer_user_id == referrer_user_id)
    )
    return int(res.scalar() or 0)


async def get_referral_progress(session: AsyncSession, referrer_telegram_user_id: int) -> dict:
    referrer = await get_or_create_user(session, telegram_user_id=int(referrer_telegram_user_id))
    total = await _count_referrals(session, referrer_user_id=referrer.id)
    toward_next = total % 3
    needed = 3 - toward_next if toward_next else 0
    return {
        "total": int(total),
        "toward_next": int(toward_next),
        "needed_for_next": int(needed),
        "reward_days_per_3": 7,
    }


async def _sum_reward_days(session: AsyncSession, referrer_user_id: int) -> int:
    res = await session.execute(
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
    result = {
        "status": "ignored",
        "referrer_id": None,
        "referrals_total": 0,
        "days_granted": 0,
    }

    code = (referral_code or "").strip()
    if not code:
        result["status"] = "invalid_code"
        return result

    res = await session.execute(select(ReferralCode).where(ReferralCode.code == code))
    rc = res.scalar_one_or_none()
    if rc is None:
        result["status"] = "invalid_code"
        return result

    # Look up referrer telegram id
    res2 = await session.execute(select(User).where(User.id == rc.referrer_user_id))
    referrer_user = res2.scalar_one_or_none()
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

    referred_user = await get_or_create_user(session, telegram_user_id=int(referred_telegram_user_id))

    # Each referred can only be attributed once.
    res3 = await session.execute(
        select(ReferralAttribution).where(ReferralAttribution.referred_user_id == referred_user.id)
    )
    if res3.scalar_one_or_none() is not None:
        result["status"] = "already_referred"
        return result

    session.add(
        ReferralAttribution(referred_user_id=referred_user.id, referrer_user_id=rc.referrer_user_id)
    )
    session.add(
        ReferralReward(
            referrer_user_id=rc.referrer_user_id,
            referred_user_id=referred_user.id,
            reward_type="referral_signup",
            reward_value=1,
        )
    )
    await session.flush()

    total = await _count_referrals(session, referrer_user_id=rc.referrer_user_id)
    result["referrals_total"] = int(total)

    expected_days = (total // 3) * 7
    already_days = await _sum_reward_days(session, referrer_user_id=rc.referrer_user_id)
    grant_days = max(0, int(expected_days) - int(already_days))

    if grant_days <= 0:
        result["status"] = "attributed"
        return result

    # Extend referrer subscription (VIP stays VIP; otherwise Premium)
    # We avoid relying on SQLite tier logic in production.
    from db.access import resolve_user_tier

    current_tier = normalize_tier(await resolve_user_tier(referrer_tid))
    tier_to_extend = "vip" if current_tier == "vip" else "premium"

    # Make idempotent per reward “batch”.
    reward_ref = f"REFERRAL:{referrer_tid}:{total // 3}"
    await activate_subscription(
        session,
        telegram_user_id=referrer_tid,
        tier=tier_to_extend,
        duration_days=int(grant_days),
        paystack_reference=reward_ref,
        meta={"source": "referral", "referred": int(referred_telegram_user_id), "batch": int(total // 3)},
    )

    session.add(
        ReferralReward(
            referrer_user_id=rc.referrer_user_id,
            referred_user_id=referred_user.id,
            reward_type="premium_days",
            reward_value=int(grant_days),
        )
    )
    await session.flush()

    result["status"] = "reward_granted"
    result["days_granted"] = int(grant_days)
    return result
