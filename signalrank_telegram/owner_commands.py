from telegram import Update
from telegram.ext import ContextTypes
from db.session import get_session, get_engine_for_event_loop
from db.repository import get_or_create_user
# --- ADMIN COMMAND: /broadcast ---
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    msg = " ".join(context.args)
    # TODO: Replace with actual user list query
    from db.pg_compat import get_all_user_ids_compat
    user_ids = await get_all_user_ids_compat()
    from signalrank_telegram.bot import application
    bot = application.bot
    sent = 0
    for uid in user_ids:
        try:
            await bot.send_message(chat_id=uid, text=msg)
            sent += 1
        except Exception:
            continue
    await update.message.reply_text(f"Broadcast sent to {sent} users.")

# --- ADMIN COMMAND: /add_vip ---
async def add_vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /add_vip <telegram_user_id>")
        return
    try:
        user_id = int(context.args[0])
        async with get_session() as session:
            user = await get_or_create_user(session, telegram_user_id=user_id)
            user.tier = "vip"
            await session.commit()
        await update.message.reply_text(f"User {user_id} upgraded to VIP.")
    except Exception as e:
        await update.message.reply_text(f"Failed to add VIP: {e}")

# --- ADMIN COMMAND: /remove_user ---
async def remove_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /remove_user <telegram_user_id>")
        return
    try:
        user_id = int(context.args[0])
        async with get_session() as session:
            user = await get_or_create_user(session, telegram_user_id=user_id)
            user.tier = "free"
            await session.commit()
        await update.message.reply_text(f"User {user_id} downgraded to FREE.")
    except Exception as e:
        await update.message.reply_text(f"Failed to remove user: {e}")

# --- ADMIN COMMAND: /pause_signals ---
async def pause_signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        return
    await state.set_killswitch(True, reason="Paused by admin via /pause_signals")
    await update.message.reply_text("All signals paused (kill-switch enabled).")
from config import config
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from core.redis_state import state


def _owner_id() -> int:
    try:
        return int(getattr(config, "OWNER_TELEGRAM_ID", 0))
    except Exception:
        return 0


def _strict_owner_ids() -> set[int]:
    # Collect configured owner IDs from multiple possible config locations
    ids = set()
    try:
        ids |= set(getattr(config, "OWNER_TELEGRAM_IDS", set()) or set())
    except Exception:
        pass
    try:
        ids |= set(getattr(config, "OWNER_IDS", set()) or set())
    except Exception:
        pass
    try:
        ids |= set(getattr(config, "owner_ids", set()) or set())
    except Exception:
        pass
    # Normalize to ints
    out: set[int] = set()
    for v in ids:
        try:
            out.add(int(v))
        except Exception:
            continue
    return out


def _bypass_key() -> Optional[str]:
    key = getattr(config, "BYPASS_KEY", None)
    return key.strip() if key else None


import logging
_owner_logger = logging.getLogger("owner_debug")

async def _is_owner(user_id: int) -> bool:
    oid = _owner_id()
    bypass = await state.has_temp_owner(user_id)
    tier = None
    try:
        from signalrank_telegram.access import resolve_user_tier
        tier = resolve_user_tier(user_id)
    except Exception:
        tier = None
    _owner_logger.info(f"[OWNER DEBUG] user_id={user_id} oid={oid} tier={tier} bypass={bypass}")
    if oid and user_id == oid:
        return True
    return bypass




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
        from db.session import get_engine_for_event_loop, get_session
        if get_engine_for_event_loop() is not None:
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

    arg = context.args[0].strip() if context.args else ""
    from db.session import get_engine_for_event_loop, get_session
    from db.models import Signal, AdminEvent
    from sqlalchemy import select, desc, or_
    from signalrank_telegram.formatter import format_signal

    engine = get_engine_for_event_loop()
    if engine is None:
        await update.message.reply_text("Database unavailable.")
        return

    async with get_session() as session:
        stmt = select(Signal).where(Signal.archived.is_(False))
        if arg:
            asset = arg.upper()
            stmt = stmt.where(or_(Signal.signal_id.ilike(f"{arg}%"), Signal.asset == asset))
        stmt = stmt.order_by(desc(Signal.created_at)).limit(1)
        res = await session.execute(stmt)
        sig: Signal | None = res.scalar_one_or_none()

        if sig is None:
            await update.message.reply_text("No signal found to send.")
            return

        signal_payload = {
            "signal_id": sig.signal_id,
            "asset": sig.asset,
            "timeframe": sig.timeframe,
            "direction": sig.direction,
            "entry": sig.entry,
            "stop_loss": sig.stop_loss,
            "take_profit": sig.take_profit,
            "rr_ratio": sig.rr_estimate,
            "score": sig.score,
            "regime": sig.regime or "NEUTRAL",
            "ml_probability": sig.ml_probability or 0.5,
            "strategy_name": sig.strategy_name,
            "strategy_group": sig.strategy_group,
            "strength": sig.strength,
            "created_at": sig.created_at,
        }

        msg = format_signal(signal_payload, user_tier="OWNER")
        if not msg:
            msg = (
                "Forced Signal (raw)\n"
                f"Asset: {sig.asset}\n"
                f"TF: {sig.timeframe}\n"
                f"Dir: {sig.direction}\n"
                f"Entry: {sig.entry}\n"
                f"SL: {sig.stop_loss}\n"
                f"TP: {sig.take_profit}\n"
                f"Score: {sig.score}\n"
                f"Ref: {sig.signal_id[:8]}"
            )

        try:
            session.add(
                AdminEvent(
                    event_type="dev_force_signal",
                    actor_telegram_user_id=int(update.effective_user.id),
                    details={"signal_id": sig.signal_id, "arg": arg},
                )
            )
            await session.commit()
        except Exception:
            pass

    await update.message.reply_text(msg)


async def dev_invalidate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        return
    if not context.args or len(context.args) != 1:
        return
    signal_id = context.args[0].strip()

    from db.session import get_engine_for_event_loop, get_session
    from db.models import Signal, AdminEvent
    from sqlalchemy import select, or_

    engine = get_engine_for_event_loop()
    if engine is None:
        await update.message.reply_text("Database unavailable.")
        return

    async with get_session() as session:
        stmt = select(Signal).where(or_(Signal.signal_id == signal_id, Signal.signal_id.ilike(f"{signal_id}%")))
        res = await session.execute(stmt)
        sig: Signal | None = res.scalar_one_or_none()
        if sig is None:
            await update.message.reply_text("Signal not found.")
            return

        sig.archived = True
        try:
            session.add(
                AdminEvent(
                    event_type="dev_invalidate",
                    actor_telegram_user_id=int(update.effective_user.id),
                    details={"signal_id": sig.signal_id},
                )
            )
        except Exception:
            pass

        await session.commit()

    await update.message.reply_text(f"Invalidated: {sig.signal_id[:8]}")


async def owner_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Strict owner-only: show total users and active subscribers."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_strict_owner(update.effective_user.id):
        return

    try:
        from db.session import get_engine_for_event_loop, get_session
        if get_engine_for_event_loop() is None:
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
        from db.session import get_engine_for_event_loop, get_session
        if get_engine_for_event_loop() is None:
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
        from db.session import get_engine_for_event_loop, get_session
        if get_engine_for_event_loop() is None:
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
