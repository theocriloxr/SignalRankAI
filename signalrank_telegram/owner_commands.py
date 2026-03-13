from telegram import Update
from telegram.ext import ContextTypes
from db.session import get_session, get_engine_for_event_loop
from db.repository import get_or_create_user
# --- ADMIN COMMAND: /broadcast ---
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Access Denied.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    msg = " ".join(context.args)
    import asyncio
    from telegram.error import RetryAfter
    from db.pg_compat import get_all_user_ids_compat
    user_ids = get_all_user_ids_compat()
    from signalrank_telegram.bot import application
    bot = application.bot
    sent = 0
    for uid in user_ids:
        try:
            while True:
                try:
                    await bot.send_message(chat_id=uid, text=msg)
                    break
                except RetryAfter as e:
                    await asyncio.sleep(float(getattr(e, "retry_after", 1.0) or 1.0))
            await asyncio.sleep(0.5)
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
from config import config, ADMIN_IDS
import json
from uuid import uuid4
from datetime import datetime, timedelta
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
    uid = int(user_id)
    # Check all configured owner IDs (OWNER_TELEGRAM_ID + OWNER_IDS + OWNER_TELEGRAM_IDS)
    if uid in _strict_owner_ids():
        return True
    oid = _owner_id()
    if oid and uid == oid:
        return True
    # Temporary bypass (granted by /unlock key)
    bypass = await state.has_temp_owner(uid)
    if bypass:
        return True
    return False


async def _is_admin_or_owner(user_id: int) -> bool:
    try:
        uid = int(user_id)
    except Exception:
        return False
    if await _is_owner(uid):
        return True
    try:
        if uid in ADMIN_IDS:
            return True
    except Exception:
        pass
    return False




async def _is_strict_owner(user_id: int) -> bool:
    return int(user_id) in _strict_owner_ids()


    key = getattr(config, "BYPASS_KEY", None)
    return key.strip() if key else None


async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """One-time unlock: grants 7 days of Premium to anyone with the right key.

    Rules:
    - Silent if wrong key or no args
    - Each user can only redeem the key ONCE. After that they must pay.
    - Grants premium tier + 7-day expiry in DB
    - Records the use in Redis (long TTL) + BotEvent (permanent)
    """
    if update.effective_user is None or update.message is None:
        return
    if not context.args or len(context.args) != 1:
        return  # silent

    provided = context.args[0].strip()
    expected = _bypass_key()
    if not expected or provided != expected:
        return  # silent — wrong key

    user_id = int(update.effective_user.id)
    redis_key = f"unlock_key_used:{user_id}"

    # ── Check one-use gate (Redis fast path) ────────────────────────────────
    already_used_redis = False
    try:
        already_used_redis = bool(state.get_sync(redis_key))
    except Exception:
        pass

    if already_used_redis:
        await update.message.reply_text(
            "🔒 You've already used this unlock key.\n"
            "Use /upgrade to subscribe and keep your Premium access."
        )
        return

    # ── Check DB for belt-and-suspenders (in case Redis was flushed) ────────
    already_used_db = False
    try:
        from db.session import get_engine_for_event_loop, get_session
        from db.models import BotEvent
        from db.repository import get_or_create_user
        from sqlalchemy import select
        if get_engine_for_event_loop() is not None:
            async with get_session() as session:
                db_user = await get_or_create_user(
                    session,
                    telegram_user_id=user_id,
                    username=getattr(update.effective_user, "username", None),
                )
                res = await session.execute(
                    select(BotEvent)
                    .where(
                        BotEvent.user_id == db_user.id,
                        BotEvent.event_type == "unlock_key_used",
                    )
                    .limit(1)
                )
                already_used_db = res.scalar_one_or_none() is not None
    except Exception:
        pass

    if already_used_db:
        # Re-stamp Redis so future checks are fast
        try:
            state.set_sync(redis_key, "1", ex=60 * 60 * 24 * 365 * 10)  # 10 years
        except Exception:
            pass
        await update.message.reply_text(
            "🔒 You've already used this unlock key.\n"
            "Use /upgrade to subscribe and keep your Premium access."
        )
        return

    # ── Grant 7-day Premium ─────────────────────────────────────────────────
    from datetime import datetime, timedelta
    premium_until = datetime.utcnow() + timedelta(days=7)

    try:
        from db.session import get_engine_for_event_loop, get_session
        from db.repository import get_or_create_user
        from db.models import BotEvent, Subscription, AdminEvent
        from db.pg_features import record_bot_event

        if get_engine_for_event_loop() is not None:
            async with get_session() as session:
                db_user = await get_or_create_user(
                    session,
                    telegram_user_id=user_id,
                    username=getattr(update.effective_user, "username", None),
                )
                # Upgrade tier + set expiry on User row
                db_user.tier = "premium"
                db_user.premium_until = premium_until

                # Create a real Subscription record so tier-resolution sees it
                import uuid as _uuid
                sub = Subscription(
                    user_id=db_user.id,
                    tier="premium",
                    status="active",
                    started_at=datetime.utcnow(),
                    expires_at=premium_until,
                    meta={"source": "unlock_key"},
                    paystack_reference=f"unlock_{user_id}_{_uuid.uuid4().hex[:8]}",
                )
                session.add(sub)

                # Audit events
                try:
                    session.add(AdminEvent(
                        event_type="unlock_key_used",
                        actor_telegram_user_id=user_id,
                        details={"tier": "premium", "days": 7},
                    ))
                except Exception:
                    pass
                try:
                    await record_bot_event(
                        session,
                        telegram_user_id=user_id,
                        username=getattr(update.effective_user, "username", None),
                        event_type="unlock_key_used",
                        meta={"tier": "premium", "days": 7},
                    )
                except Exception:
                    pass

                await session.commit()
    except Exception as _e:
        _owner_logger.warning(f"[unlock] DB grant failed for user {user_id}: {_e}")
        await update.message.reply_text(
            "⚠️ Could not activate premium right now. Please contact support."
        )
        return

    # ── Stamp Redis so next call is instant ─────────────────────────────────
    try:
        state.set_sync(redis_key, "1", ex=60 * 60 * 24 * 365 * 10)  # 10 years
    except Exception:
        pass

    await update.message.reply_text(
        "🎉 *Premium Unlocked for 7 Days!*\n\n"
        "You now have access to:\n"
        "⭐ Real-time signals with full Entry / SL / TP\n"
        "📊 Confidence scores & risk/reward\n"
        "📈 Performance stats & signal history\n"
        "⚡ Trade directly on MT5\n\n"
        f"📅 Your premium expires on: {premium_until.strftime('%Y-%m-%d')}\n\n"
        "🔒 This key can only be used once. After expiry, use /upgrade to continue.",
        parse_mode="Markdown",
    )


async def dev_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_admin_or_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Access Denied.")
        return
    await state.set_killswitch(True, reason="paused via /dev_pause")
    await update.message.reply_text("Kill-switch enabled.")


async def dev_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_admin_or_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Access Denied.")
        return
    await state.set_killswitch(False, reason="")
    await update.message.reply_text("Kill-switch disabled.")


async def dev_force_signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_admin_or_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Access Denied.")
        return

    args = list(context.args or [])
    requested_asset = str(args[0]).upper().replace("/", "").strip() if len(args) >= 1 else ""
    requested_tf = str(args[1]).strip().lower() if len(args) >= 2 else ""

    candidate_assets = [requested_asset] if requested_asset else [
        x.strip().upper().replace("/", "")
        for x in (config.__dict__.get("FORCE_SIGNAL_ASSETS") or "BTCUSDT,ETHUSDT,XAUUSD,EURUSD").split(",")
        if x.strip()
    ]
    candidate_timeframes = [requested_tf] if requested_tf else ["15m", "1h", "4h"]

    from db.session import get_engine_for_event_loop, get_session
    from db.models import Signal, AdminEvent
    from engine.market_state import get_market_state_async
    from engine.strategies.signal_generator import SignalGenerator

    engine = get_engine_for_event_loop()
    if engine is None:
        await update.message.reply_text("Database unavailable.")
        return

    generator = SignalGenerator()
    best_signal = None
    best_asset = None
    best_tf = None
    best_ml_prob = None
    best_regime = "NEUTRAL"

    for asset in candidate_assets:
        for timeframe in candidate_timeframes:
            try:
                market_state = await get_market_state_async(asset, [timeframe], include_ml=True)
                tf_data = (market_state.get("timeframes") or {}).get(timeframe) or {}
                candles = tf_data.get("candles") or []
                indicators = tf_data.get("indicators") or {}
                ml_prob = tf_data.get("ml_score")
                if len(candles) < 50:
                    continue
                generated = generator.generate_signals(
                    asset,
                    timeframe,
                    {
                        "candles": candles,
                        "indicators": indicators,
                        "ml_probability": ml_prob,
                    },
                )
                if not generated:
                    continue
                current_best = max(generated, key=lambda item: float(getattr(item, "score", 0) or 0))
                if best_signal is None or float(current_best.score or 0) > float(best_signal.score or 0):
                    best_signal = current_best
                    best_asset = asset
                    best_tf = timeframe
                    best_ml_prob = ml_prob
                    best_regime = str(indicators.get("regime") or "NEUTRAL")
            except Exception:
                continue

    if best_signal is None or best_asset is None or best_tf is None:
        attempted_assets = ", ".join(candidate_assets)
        attempted_tfs = ", ".join(candidate_timeframes)
        await update.message.reply_text(
            "No fresh signal could be generated right now.\n\n"
            f"Assets checked: {attempted_assets}\n"
            f"Timeframes checked: {attempted_tfs}\n\n"
            "Try again with /force_signal <ASSET> <TIMEFRAME>, for example: /force_signal BTCUSDT 1h"
        )
        return

    tp_levels = []
    try:
        tp_levels = [float(tp.get("price")) for tp in (best_signal.take_profit or []) if isinstance(tp, dict) and tp.get("price") is not None]
    except Exception:
        tp_levels = []

    rr_ratio = None
    try:
        if tp_levels:
            risk = abs(float(best_signal.entry) - float(best_signal.stop_loss))
            reward = abs(float(tp_levels[0]) - float(best_signal.entry))
            if risk > 0:
                rr_ratio = reward / risk
    except Exception:
        rr_ratio = None

    signal_id = str(uuid4())
    expires_at = datetime.utcnow() + timedelta(hours=12)
    
    # Ensure score is high enough to bypass quality gates in resend job
    score_for_storage = max(float(best_signal.score or 0), 80.0)
    
    signal_payload = {
        "signal_id": signal_id,
        "asset": best_asset,
        "timeframe": best_tf,
        "direction": best_signal.direction,
        "entry": best_signal.entry,
        "stop_loss": best_signal.stop_loss,
        "take_profit": best_signal.take_profit,
        "tp_levels": tp_levels,
        "rr_ratio": rr_ratio,
        "score": score_for_storage,
        "regime": best_regime,
        "ml_probability": best_ml_prob,
        "strategy_name": best_signal.strategy_name,
        "strategy_group": best_signal.strategy_group,
        "strength": best_signal.confidence,
        "confidence": best_signal.confidence,
        "created_at": datetime.utcnow(),
        "expires_at": expires_at,
    }

    async with get_session() as session:
        try:
            session.add(
                Signal(
                    signal_id=signal_id,
                    asset=best_asset,
                    timeframe=best_tf,
                    direction=best_signal.direction,
                    entry=float(best_signal.entry),
                    stop_loss=float(best_signal.stop_loss),
                    take_profit=json.dumps(best_signal.take_profit or []),
                    rr_estimate=rr_ratio,
                    score=score_for_storage,
                    regime=best_regime,
                    ml_probability=float(best_ml_prob) if best_ml_prob is not None else None,
                    strategy_name=str(best_signal.strategy_name),
                    strategy_group=str(best_signal.strategy_group),
                    strength=float(best_signal.confidence or 0.0),
                    fingerprint=f"{best_asset}_{best_tf}_{best_signal.direction}_{int(float(best_signal.entry) or 0)}",
                    archived=True,
                    expired=True,
                    expires_at=expires_at,
                )
            )
            session.add(
                AdminEvent(
                    event_type="dev_force_signal",
                    actor_telegram_user_id=int(update.effective_user.id),
                    details={
                        "signal_id": signal_id,
                        "asset": best_asset,
                        "timeframe": best_tf,
                        "generated": True,
                        "score": float(best_signal.score or 0),
                    },
                )
            )
            await session.commit()
        except Exception:
            await session.rollback()

    from signalrank_telegram.formatter import format_signal_vip_new
    
    # For forced signals, always use VIP template (bypasses quality gates for admin/owner)
    msg = format_signal_vip_new(signal_payload)
    
    if not msg:
        msg = (
            "Forced Signal (generated)\n"
            f"Asset: {best_asset}\n"
            f"TF: {best_tf}\n"
            f"Dir: {best_signal.direction}\n"
            f"Entry: {best_signal.entry}\n"
            f"SL: {best_signal.stop_loss}\n"
            f"TP1: {tp_levels[0] if tp_levels else 'N/A'}\n"
            f"Score: {best_signal.score}\n"
            f"Ref: {signal_id[:8]}"
        )

    await update.message.reply_text(msg)


async def dev_invalidate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Access Denied.")
        return
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /dev_invalidate <signal_id>")
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
        await update.message.reply_text("⛔ Access Denied.")
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
        await update.message.reply_text("⛔ Access Denied.")
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


async def provider_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner command to check health status of data providers."""
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        await update.message.reply_text("⚠️ Owner access required.")
        return
    
    try:
        from data.fetcher import get_unhealthy_providers, _PROVIDER_HEALTH
        from datetime import datetime
        
        # Get unhealthy providers
        unhealthy = get_unhealthy_providers(min_minutes=5)
        
        message = "📊 **Data Provider Status**\n\n"
        
        # Show all tracked providers
        if _PROVIDER_HEALTH:
            message += "**All Providers:**\n"
            for provider, health_info in _PROVIDER_HEALTH.items():
                failures = len(health_info.get('failures', []))
                last_success = health_info.get('last_success', 0)
                
                if last_success > 0:
                    import time
                    minutes_since_success = int((time.time() - last_success) / 60)
                    success_str = f"{minutes_since_success}m ago"
                else:
                    success_str = "Never"
                
                # Determine status
                if failures == 0:
                    status_emoji = "🟢"
                    status_text = "Healthy"
                elif failures < 3:
                    status_emoji = "🟡"
                    status_text = f"Warning ({failures} fails)"
                else:
                    status_emoji = "🔴"
                    status_text = f"Unhealthy ({failures} fails)"
                
                message += f"{status_emoji} **{provider}**: {status_text}\n"
                message += f"   Last Success: {success_str}\n\n"
        else:
            message += "No provider health data available yet.\n\n"
        
        # Show unhealthy providers summary
        if unhealthy:
            message += f"\n⚠️ **Unhealthy Providers ({len(unhealthy)}):**\n"
            for provider, minutes_down in unhealthy:
                message += f"🔴 {provider}: Down for {minutes_down:.0f} minutes\n"
        else:
            message += "\n✅ All providers healthy (or not yet tracked)\n"
        
        # Add timestamp
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        message += f"\n📅 Checked: {timestamp}"
        
        await update.message.reply_text(message)
    
    except Exception as e:
        await update.message.reply_text(f"Error checking provider status: {str(e)}")

