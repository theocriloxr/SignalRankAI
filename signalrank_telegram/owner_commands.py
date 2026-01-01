import os
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from core.redis_state import state


def _owner_id() -> int:
    try:
        return int(os.getenv("OWNER_TELEGRAM_ID", "0"))
    except ValueError:
        return 0


async def _is_owner(user_id: int) -> bool:
    oid = _owner_id()
    if oid and user_id == oid:
        return True
    return await state.has_temp_owner(user_id)


def _strict_owner_ids() -> set[int]:
    try:
        from config import OWNER_IDS
        ids = set(int(x) for x in (OWNER_IDS or set()) if int(x) > 0)
    except Exception:
        ids = set()
    # Fallback to env var
    try:
        oid = _owner_id()
        if oid > 0:
            ids.add(int(oid))
    except Exception:
        pass
    return ids


async def _is_strict_owner(user_id: int) -> bool:
    return int(user_id) in _strict_owner_ids()


def _bypass_key() -> Optional[str]:
    key = os.getenv("BYPASS_KEY")
    return key.strip() if key else None


async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not context.args or len(context.args) != 1:
        return  # silent

    provided = context.args[0]
    expected = _bypass_key()
    if not expected or provided != expected:
        return  # silent

    # 24h temporary owner access
    await state.set_temp_owner(update.effective_user.id, ttl_seconds=24 * 3600)
    await update.message.reply_text("Access granted.")


async def dev_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        return
    await state.set_killswitch(True, reason="paused via /dev_pause")
    await update.message.reply_text("Kill-switch enabled.")


async def dev_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        return
    await state.set_killswitch(False, reason="")
    await update.message.reply_text("Kill-switch disabled.")


async def dev_force_signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        return

    # Safe synthetic test message (explicitly a test)
    await update.message.reply_text(
        "[TEST] Forced signal trigger received.\n"
        "This is a system test message (not a trade recommendation)."
    )


async def dev_invalidate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        return
    if not context.args or len(context.args) != 1:
        return
    signal_id = context.args[0]
    # TODO: persist invalidation to Postgres outcomes/admin_events.
    await update.message.reply_text(f"Invalidated: {signal_id}")


async def owner_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Strict owner-only: show total users and active subscribers."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_strict_owner(update.effective_user.id):
        return

    try:
        from db.session import ENGINE, get_session
        if ENGINE is None:
            await update.message.reply_text("Postgres not configured.")
            return
        from db.models import User, Subscription
        from sqlalchemy import select, func
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        async with get_session() as session:
            res_users = await session.execute(select(func.count(User.id)))
            total_users = int(res_users.scalar() or 0)

            res_active = await session.execute(
                select(Subscription.tier, func.count(Subscription.id))
                .where(Subscription.status == "active", Subscription.expires_at.is_not(None), Subscription.expires_at > now)
                .group_by(Subscription.tier)
            )
            active_rows = res_active.all() or []
            await session.commit()

        active_map = {str(t).lower(): int(c) for (t, c) in active_rows}
        prem = int(active_map.get("premium", 0))
        vip = int(active_map.get("vip", 0))
        msg = (
            "👤 Users (Owner)\n\n"
            f"Total users started bot: {total_users}\n"
            f"Active Premium: {prem}\n"
            f"Active VIP: {vip}"
        )
        await update.message.reply_text(msg)
    except Exception:
        await update.message.reply_text("Unable to load user stats right now.")


async def owner_revenue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Strict owner-only: show revenue totals and breakdowns."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_strict_owner(update.effective_user.id):
        return

    try:
        from db.session import ENGINE, get_session
        if ENGINE is None:
            await update.message.reply_text("Postgres not configured.")
            return
        from db.models import PaymentEvent
        from sqlalchemy import select, func

        def _plan_label(days: int | None, plan_code: str | None) -> str:
            if plan_code:
                return str(plan_code)
            if days == 7:
                return "weekly"
            if days == 30:
                return "monthly"
            if days == 90:
                return "quarterly"
            if days is None:
                return "unknown"
            return f"{int(days)}d"

        async with get_session() as session:
            res_total_sub = await session.execute(
                select(func.coalesce(func.sum(PaymentEvent.amount_ngn), 0)).where(PaymentEvent.kind == "subscription")
            )
            total_sub = int(res_total_sub.scalar() or 0)

            res_total_extra = await session.execute(
                select(func.coalesce(func.sum(PaymentEvent.amount_ngn), 0)).where(PaymentEvent.kind == "extra_signals")
            )
            total_extra = int(res_total_extra.scalar() or 0)

            total_all = int(total_sub) + int(total_extra)

            res_by_tier_sub = await session.execute(
                select(PaymentEvent.tier, func.coalesce(func.sum(PaymentEvent.amount_ngn), 0))
                .where(PaymentEvent.kind == "subscription")
                .group_by(PaymentEvent.tier)
                .order_by(func.coalesce(func.sum(PaymentEvent.amount_ngn), 0).desc())
            )
            by_tier_sub = [(str(t or "unknown"), int(a or 0)) for (t, a) in (res_by_tier_sub.all() or [])]

            res_by_tier_extra = await session.execute(
                select(PaymentEvent.tier, func.coalesce(func.sum(PaymentEvent.amount_ngn), 0))
                .where(PaymentEvent.kind == "extra_signals")
                .group_by(PaymentEvent.tier)
                .order_by(func.coalesce(func.sum(PaymentEvent.amount_ngn), 0).desc())
            )
            by_tier_extra = [(str(t or "unknown"), int(a or 0)) for (t, a) in (res_by_tier_extra.all() or [])]

            res_by_plan = await session.execute(
                select(PaymentEvent.tier, PaymentEvent.duration_days, PaymentEvent.plan_code, func.coalesce(func.sum(PaymentEvent.amount_ngn), 0))
                .where(PaymentEvent.kind == "subscription")
                .group_by(PaymentEvent.tier, PaymentEvent.duration_days, PaymentEvent.plan_code)
                .order_by(func.coalesce(func.sum(PaymentEvent.amount_ngn), 0).desc())
                .limit(10)
            )
            by_plan = res_by_plan.all() or []
            await session.commit()

        lines = [
            "💰 Revenue (Owner)",
            "",
            f"Total (all): ₦{total_all}",
            f"Subscriptions: ₦{total_sub}",
            f"Extra signals: ₦{total_extra}",
            "",
        ]

        if by_tier_sub:
            lines.append("Subscriptions by tier:")
            for t, a in by_tier_sub:
                lines.append(f"• {t.upper()}: ₦{a}")
            lines.append("")

        if by_tier_extra:
            lines.append("Extra signals by tier:")
            for t, a in by_tier_extra:
                lines.append(f"• {t.upper()}: ₦{a}")
            lines.append("")

        if by_plan:
            lines.append("Top plans:")
            for t, days, plan_code, a in by_plan:
                lines.append(f"• {str(t or 'unknown').upper()} / {_plan_label(days, plan_code)}: ₦{int(a or 0)}")
        await update.message.reply_text("\n".join(lines))
    except Exception:
        await update.message.reply_text("Unable to load revenue stats right now.")
