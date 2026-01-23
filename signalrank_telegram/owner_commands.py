from config import config
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from core.redis_state import state


    try:
        return int(getattr(config, "OWNER_TELEGRAM_ID", 0))
    except ValueError:
        return 0


async def _is_owner(user_id: int) -> bool:
    oid = _owner_id()
    if oid and user_id == oid:
        return True
    return await state.has_temp_owner(user_id)




async def _is_strict_owner(user_id: int) -> bool:
    return int(user_id) in _strict_owner_ids()


    key = getattr(config, "BYPASS_KEY", None)
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

    # 24h temporary admin access (bypass)
    await state.set_temp_owner(update.effective_user.id, ttl_seconds=24 * 3600)

    # Persist bypass usage + tier in Postgres (best-effort).
    try:
        from db.session import ENGINE, get_session
        if ENGINE is not None:
            from db.repository import get_or_create_user
            from db.models import AdminEvent
            from db.pg_features import record_bot_event

            async with get_session() as session:
                u = await get_or_create_user(session, telegram_user_id=int(update.effective_user.id), username=getattr(update.effective_user, "username", None))
                try:
                    u.tier = "admin"
                except Exception:
                    pass
                try:
                    session.add(
                        AdminEvent(
                            event_type="bypass_unlock",
                            actor_telegram_user_id=int(update.effective_user.id),
                            details={"source": "unlock"},
                        )
                    )
                except Exception:
                    pass
                try:
                    await record_bot_event(
                        session,
                        telegram_user_id=int(update.effective_user.id),
                        username=getattr(update.effective_user, "username", None),
                        event_type="bypass_unlock",
                        meta={"tier": "admin"},
                    )
                except Exception:
                    pass
                await session.commit()
    except Exception:
        pass

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
        from datetime import datetime

        now = datetime.utcnow()
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


async def correct_signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Owner command to mark a signal as incorrect and notify all recipients.
    
    Usage: /correct_signal <signal_ref> <error_description>
    Example: /correct_signal abc123 Invalid entry level due to data error
    """
    if update.effective_user is None or update.message is None:
        return
    
    if not await _is_strict_owner(update.effective_user.id):
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /correct_signal <signal_ref> <error_description>\n"
            "Example: /correct_signal abc123 Invalid entry level"
        )
        return
    
    signal_ref = context.args[0].strip()
    error_description = " ".join(context.args[1:]).strip()
    
    if not signal_ref or not error_description:
        await update.message.reply_text("❌ Both signal reference and error description are required.")
        return
    
    try:
        from db.session import ENGINE, get_session
        if ENGINE is None:
            await update.message.reply_text("Postgres not configured.")
            return
        
        from db.models import Signal, SignalDelivery
        from sqlalchemy import select
        from engine.signal_validator import create_signal_correction, notify_signal_correction
        
        async with get_session() as session:
            # Find the signal
            query = select(Signal)
            if len(signal_ref) >= 32:
                query = query.where(Signal.signal_id == signal_ref)
            else:
                query = query.where(Signal.signal_id.like(f"{signal_ref}%"))
            
            query = query.order_by(Signal.created_at.desc()).limit(1)
            result = await session.execute(query)
            signal = result.scalar_one_or_none()
            
            if signal is None:
                await update.message.reply_text(f"❌ Signal not found: {signal_ref}")
                return
            
            # Count deliveries
            delivery_query = select(SignalDelivery).where(
                SignalDelivery.signal_id == signal.signal_id
            )
            delivery_result = await session.execute(delivery_query)
            deliveries = delivery_result.scalars().all()
            delivery_count = len(deliveries)
            
            if delivery_count == 0:
                await update.message.reply_text(
                    f"⚠️ Signal {signal.signal_id[:8]} was never delivered to any users.\n"
                    f"No corrections needed."
                )
                return
            
            # Create correction record
            await create_signal_correction(
                session=session,
                original_signal_id=signal.signal_id,
                error_type="manual_correction",
                error_description=error_description,
                corrected_signal_id=None  # Manual correction, no replacement signal
            )
            
            await session.commit()
        
        # Notify users
        await update.message.reply_text(
            f"⏳ Notifying {delivery_count} users about signal correction..."
        )
        
        from signalrank_telegram.bot import application
        bot = application.bot
        
        notified_count = await notify_signal_correction(
            bot=bot,
            original_signal_id=signal.signal_id,
            error_description=error_description,
            corrected_signal_id=None
        )
        
        await update.message.reply_text(
            f"✅ Signal correction complete:\n"
            f"• Signal: {signal.signal_id[:8]}\n"
            f"• Error: {error_description}\n"
            f"• Users notified: {notified_count}/{delivery_count}"
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        await update.message.reply_text(f"❌ Error correcting signal: {e}")
