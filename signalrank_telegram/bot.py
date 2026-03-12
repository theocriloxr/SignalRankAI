from utils.async_runner import run_sync


def resend_unsent_signals_job():
    """Scheduled job: resend top-scored unsent signals to eligible users.

    Signals are capped to the top-20 by score from the last 24 h to avoid flooding.
    Uses run_sync() so the global async engine is re-used correctly whether or not
    an event loop is already running in the calling thread.
    """
    # Pre-flight: make sure the global async engine is initialised.  This is a
    # no-op when run_bot() has already set it up, but guards against edge cases
    # where the job fires before the main startup path completes.
    try:
        from db.session import _get_global_engine
        if _get_global_engine() is None:
            logger.warning("[resend] DB engine not initialised — skipping job")
            return
    except Exception as _pre_err:
        logger.warning("[resend] DB engine pre-flight failed: %s", _pre_err)
        return
    try:
        run_sync(_resend_unsent_signals_async())
    except Exception:
        logger.exception("[resend] resend_unsent_signals_job failed")


async def _resend_unsent_signals_async():
    """Async core of the resend job — all deliveries share one event loop / Bot instance."""
    try:
        from db.session import get_session
        from db.pg_features import list_active_signals, get_signal_outcome_status, record_signal_delivery
        from signalrank_telegram.tier_delivery import TierDeliveryManager
        from core.redis_state import was_signal_delivered_sync
        from signalrank_telegram.access import resolve_user_tier
        from .formatter import format_signal
        import asyncio
        from telegram.error import RetryAfter

        delivery_mgr = TierDeliveryManager()

        # Fetch user IDs with a direct async call — avoids calling
        # get_all_user_ids_compat() (which uses run_sync() internally and would
        # spawn a nested thread+event-loop inside the already-running loop).
        from db.pg_features import list_all_user_telegram_ids
        async with get_session() as _uid_session:
            user_ids = await list_all_user_telegram_ids(_uid_session)

        # Fetch signals from the last 24 h, limit 100 rows, then rank by score
        async with get_session() as session:
            try:
                raw_signals = await list_active_signals(session, max_age_days=1, limit=100)
                await session.commit()
            except Exception:
                raw_signals = []

        if not raw_signals:
            return

        # Keep top-20 highest-score signals to avoid flooding users
        signals = sorted(
            raw_signals,
            key=lambda s: float(getattr(s, 'score', 0) or 0),
            reverse=True,
        )[:20]

        # Single Bot instance, properly initialised — avoids shared-httpx-client races
        bot = Bot(token=_require_telegram_token())
        async def _send_with_retry(chat_id: int, text: str) -> None:
            while True:
                try:
                    await bot.send_message(chat_id=int(chat_id), text=text)
                    return
                except RetryAfter as e:
                    await asyncio.sleep(float(getattr(e, "retry_after", 1.0) or 1.0))
                except Exception:
                    raise
        async with bot:
            for sig in signals:
                signal_id = str(getattr(sig, 'signal_id', '') or '')
                if not signal_id:
                    continue

                # ── Fix 1: 50-minute cutoff — skip stale signals ──────────────────
                try:
                    from datetime import datetime, timezone, timedelta as _td
                    _created = getattr(sig, 'created_at', None)
                    if _created is not None:
                        if hasattr(_created, 'tzinfo') and _created.tzinfo is None:
                            _created = _created.replace(tzinfo=timezone.utc)
                        _age_min = (datetime.now(timezone.utc) - _created).total_seconds() / 60
                        if _age_min > 50:
                            # Mark as expired so this signal never re-enters the queue
                            try:
                                async with get_session() as _exp_s:
                                    from db.pg_features import expire_signal as _expire
                                    await _expire(_exp_s, signal_id)
                                    await _exp_s.commit()
                            except Exception:
                                pass
                            logger.info(f"[resend] Signal {signal_id} is {_age_min:.0f}m old — expired, skipped.")
                            continue
                except Exception as _age_err:
                    logger.debug(f"[resend] age-check failed for {signal_id}: {_age_err}")

                # Skip signals whose outcome (TP / SL) has already been reached
                try:
                    outcome_status = get_signal_outcome_status(signal_id)
                    if outcome_status and outcome_status.get('reached'):
                        continue
                except Exception:
                    pass

                # Build a plain dict from the ORM row for the formatter
                try:
                    if hasattr(sig, '__table__'):
                        sig_dict = {c.key: getattr(sig, c.key, None) for c in sig.__table__.columns}
                    else:
                        sig_dict = {k: v for k, v in sig.__dict__.items() if not k.startswith('_')}
                except Exception:
                    sig_dict = {}

                for user_id in user_ids:
                    try:
                        # Fast Redis / in-memory dedup first
                        if was_signal_delivered_sync(user_id, signal_id):
                            continue

                        # Tier, score, and daily-limit gate
                        user_tier = resolve_user_tier(user_id).lower()
                        score = float(getattr(sig, 'score', 0) or 0)
                        if not delivery_mgr.should_send_signal(user_tier, score, user_id=user_id):
                            logger.info(
                                f"[resend] User {user_id} not eligible for signal {signal_id} "
                                f"(tier/score/limit), skipping."
                            )
                            continue

                        # Format and send
                        display_tier = 'vip' if user_tier in ('owner', 'admin') else user_tier
                        text = format_signal(sig_dict, display_tier=display_tier)
                        try:
                            await _send_with_retry(int(user_id), text)
                        except Exception as send_err:
                            raise send_err
                        await asyncio.sleep(0.5)
                        logger.info(f"[resend] Delivered signal {signal_id} to user {user_id} (tier={user_tier})")

                        # Record delivery in DB (sequential — no races)
                        try:
                            async with get_session() as db_session:
                                ok = await record_signal_delivery(
                                    db_session,
                                    telegram_user_id=int(user_id),
                                    signal_id=str(signal_id),
                                    tier_at_send=str(user_tier),
                                )
                                await db_session.commit()
                            if ok:
                                logger.info(f"[resend] DB tracked delivery: signal {signal_id} to user {user_id} (tier={user_tier})")
                            else:
                                logger.info(f"[resend] DB deduped: signal {signal_id} to user {user_id} (tier={user_tier})")
                        except Exception as db_err:
                            logger.error(f"[resend] DB error tracking delivery: signal {signal_id} to user {user_id}: {db_err}")

                    except Exception as send_err:
                        logger.error(f"[resend] Failed to deliver signal {signal_id} to user {user_id}: {send_err}")

    except Exception as e:
        logger.warning(f"[resend] Job inner error: {e}")


import os
from config import config
from telegram.ext import Application, CommandHandler
from signalrank_telegram.httpx_config import httpx_client

def _audit_handler(command_name: str, handler):
    async def _inner(update, context):
        # IMPORTANT: Skip pre-audit for /start.
        # The audit writer creates the user row (via record_bot_event -> get_or_create_user).
        # That would make start_command see the user as "not new" and prevent referral attribution.
        # start_command already handles user creation + start auditing in a single transaction.
        if str(command_name) == "start":
            return await handler(update, context)

        try:
            from db.session import get_session
            if getattr(update, "effective_user", None) is not None:
                user_id = int(update.effective_user.id)
                username = None
                try:
                    username = update.effective_user.username
                except Exception as e:
                    logger.debug(f"[audit] Failed to get username from update: {e}")
                    pass
                # ...existing code for auditing...
        except Exception as e:
            logger.debug(f"[audit] Failed to audit command wrapper: {e}")
            pass
        return await handler(update, context)
    return _inner

from telegram.ext import Defaults
import logging
# Increase Telegram bot request timeout for connection pool exhaustion
TELEGRAM_POOL_TIMEOUT = int(getattr(config, "TELEGRAM_POOL_TIMEOUT", 30))  # seconds, configurable
TELEGRAM_CONNECT_TIMEOUT = int(getattr(config, "TELEGRAM_CONNECT_TIMEOUT", 30))  # seconds, configurable
TELEGRAM_READ_TIMEOUT = int(getattr(config, "TELEGRAM_READ_TIMEOUT", 30))  # seconds, configurable
TELEGRAM_WRITE_TIMEOUT = int(getattr(config, "TELEGRAM_WRITE_TIMEOUT", 30))  # seconds, configurable

# Build the Telegram Application only when a token is provided and not in DRY_RUN
_token = getattr(config, 'TELEGRAM_BOT_TOKEN', None)
_dry_run_env = str(os.getenv('DRY_RUN') or '').strip().lower() in {'1', 'true', 'yes'}
if _token and not _dry_run_env:
    application = Application.builder()
    application = application.token(_token)
    application = application.pool_timeout(TELEGRAM_POOL_TIMEOUT)
    application = application.connect_timeout(TELEGRAM_CONNECT_TIMEOUT)
    application = application.read_timeout(TELEGRAM_READ_TIMEOUT)
    application = application.write_timeout(TELEGRAM_WRITE_TIMEOUT)
    application = application.build()
else:
    # Dummy application for environments without a token or when DRY_RUN is set.
    class _DummyApp:
        def add_handler(self, *a, **k):
            return None

        def run(self, *a, **k):
            return None

    application = _DummyApp()
    # Log a non-blocking warning so operators see why the real bot isn't running
    try:
        _logger = logging.getLogger(__name__)
        if _dry_run_env:
            _logger.warning("TELEGRAM_BOT_TOKEN not used because DRY_RUN is enabled; bot disabled for this process.")
        else:
            _logger.warning("TELEGRAM_BOT_TOKEN not provided; Telegram bot is disabled in this process.")
    except Exception as e:
        _logger.warning(f"[bot] Failed to initialize Telegram bot token: {e}")
        pass
from .commands import reports_command
application.add_handler(CommandHandler("reports", _audit_handler("reports", reports_command)))
from .commands import filter_command
application.add_handler(CommandHandler("filter", _audit_handler("filter", filter_command)))
from .commands import apikey_command
application.add_handler(CommandHandler("apikey", _audit_handler("apikey", apikey_command)))
from .commands import language_command
application.add_handler(CommandHandler("language", _audit_handler("language", language_command)))
from .commands import referral_leaderboard_command, referral_rewards_command
# Register referral leaderboard and rewards commands
application.add_handler(CommandHandler("referral_leaderboard", _audit_handler("referral_leaderboard", referral_leaderboard_command)))
application.add_handler(CommandHandler("referral_rewards", _audit_handler("referral_rewards", referral_rewards_command)))
from .commands import admin_top_assets_command, admin_top_strategies_command, admin_user_engagement_command, assets_command
# Register admin analytics commands
application.add_handler(CommandHandler("admin_top_assets", _audit_handler("admin_top_assets", admin_top_assets_command)))
application.add_handler(CommandHandler("assets", _audit_handler("assets", assets_command)))
application.add_handler(CommandHandler("admin_top_strategies", _audit_handler("admin_top_strategies", admin_top_strategies_command)))
application.add_handler(CommandHandler("admin_user_engagement", _audit_handler("admin_user_engagement", admin_user_engagement_command)))
import os
import asyncio
import socket
import logging
from telegram import Bot
from telegram.ext import Application, CommandHandler
from datetime import datetime

from core.performance import performance_tracker
from db.pg_compat import get_all_user_ids_compat
from signalrank_telegram.access import resolve_user_tier
from .formatter import format_signal

from .commands import (
    start_command,
    help_command,
    about_command,
    faq_command,
    disclaimer_command,
    status_command,
    support_command,
    performance_command,
    pricing_command,
    upgrade_command,
    policy_command,
    recap_command,
    signals_command,
    signal_command,
    outcome_command,
    invite_command,
    stats_command,
    history_command,
    analyze_command,
    risk_command,
    alerts_command,
    elite_command,
    early_command,
    report_command,
    feedback_command,
    notify_command,
    selfcheck_command,
    myid_command,
    dashboard_command,
    liveprice_command,
    portfolio_command,
    market_command,
    admin_command,
    admin_broadcast_command,
    agree_terms_callback,
    decline_terms_callback,
    vip_waitlist_join_callback,
    blast_terms_command,
)

# Register new commands
application.add_handler(CommandHandler("myid", _audit_handler("myid", myid_command)))
application.add_handler(CommandHandler("dashboard", _audit_handler("dashboard", dashboard_command)))
application.add_handler(CommandHandler("selfcheck", _audit_handler("selfcheck", selfcheck_command)))
application.add_handler(CommandHandler("notify", _audit_handler("notify", notify_command)))
application.add_handler(CommandHandler("feedback", _audit_handler("feedback", feedback_command)))
application.add_handler(CommandHandler("analyze", _audit_handler("analyze", analyze_command)))

from core.redis_state import state, mark_signal_delivered_sync
from .owner_commands import (
    unlock,
    dev_pause,
    dev_resume,
    dev_force_signal,
    dev_invalidate,
    owner_users,
    owner_revenue,
    correct_signal,
    provider_status_command,
    broadcast_command,
)

# Import tier-based notification manager
from engine.tier_notifications import TierNotificationManager

# Initialize tier notification manager
_tier_notifier = TierNotificationManager()

# Module-level logger for scheduled jobs and dispatch traces
logger = logging.getLogger(__name__)

TIER_LIMITS = {
    'free': 3,
    'premium': 10,
    'vip': 30,
    'admin': 9999,
    'owner': 9999,
}


_LOG_ONCE_KEYS: set[str] = set()


def _log_once(key: str, message: str) -> None:
    if key in _LOG_ONCE_KEYS:
        return
    _LOG_ONCE_KEYS.add(key)
    try:
        print(message, flush=True)
    except Exception as e:
        logger.debug(f"[log_once] Failed to print log message: {e}")
        pass




async def _send_message_async(bot: Bot, chat_id: int, text: str, parse_mode: str | None = None) -> None:
    await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)


async def _send_signal_with_engagement_async(
    bot: Bot,
    chat_id: int,
    text: str,
    signal_id: str,
    telegram_user_id: int,
    signal: dict | None = None,
) -> None:
    """Send a signal message with engagement buttons (+ ⚡ MT5 button for PREMIUM+)
    and save message_id to ActiveSignalMessage for live-edit support."""
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    # Row 1: engagement reactions (always present)
    _kb_rows = [[
        InlineKeyboardButton("🔥 Taking it", callback_data=f"signal_reaction_{signal_id}|taking_it"),
        InlineKeyboardButton("👀 Watching",  callback_data=f"signal_reaction_{signal_id}|watching"),
    ]]
    # Row 2: ⚡ Take Trade button — shown to ALL tiers.
    # FREE users see an upsell paywall when they tap it; PREMIUM/VIP execute.
    if signal:
        try:
            import json as _j
            _asset = str(signal.get('asset') or '')
            _dir   = str(signal.get('direction') or '').lower()
            _entry = signal.get('entry') or 0
            _sl    = signal.get('stop_loss') or 0
            _tp_r  = signal.get('take_profit') or signal.get('tp_levels') or 0
            # Reduce TP to first scalar value
            if isinstance(_tp_r, list) and _tp_r:
                _tp = _tp_r[0]
            elif isinstance(_tp_r, str):
                try:
                    _pd = _j.loads(_tp_r)
                    _tp = _pd[0] if isinstance(_pd, list) else _pd
                except Exception:
                    try:
                        _tp = float(_tp_r.strip("[]'\" ").split(',')[0])
                    except Exception:
                        _tp = 0
            else:
                _tp = _tp_r or 0
            _sid8 = str(signal_id)[:8]
            # Include button even when sl/tp are 0 — FREE users are gated in the
            # callback before execution logic is reached.
            if _asset and _dir:
                _cb = f"mt5_trade_{_sid8}|{_asset}|{_dir}|{_entry}|{_sl}|{_tp}"
                if len(_cb.encode()) <= 64:
                    _kb_rows.append([
                        InlineKeyboardButton("⚡ Take Trade", callback_data=_cb)
                    ])
        except Exception as _me:
            logger.debug(f"[send_signal] Take Trade button error: {_me}")
    # Row 3: 🔍 Check Outcome — always present so users can query signal status
    if signal_id:
        _co_cb = f"check_outcome_{str(signal_id)[:36]}"
        if len(_co_cb.encode()) <= 64:
            _kb_rows.append([
                InlineKeyboardButton("🔍 Check Outcome", callback_data=_co_cb)
            ])
    keyboard = InlineKeyboardMarkup(_kb_rows)
    try:
        msg = await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
        # Persist message location so tiered_executor can live-edit it later
        try:
            from db.session import get_session
            from db.models import ActiveSignalMessage
            from db.pg_features import get_or_create_user
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            async with get_session() as session:
                user = await get_or_create_user(session, telegram_user_id=int(telegram_user_id))
                stmt = pg_insert(ActiveSignalMessage).values(
                    user_id=user.id,
                    signal_id=str(signal_id),
                    chat_id=int(chat_id),
                    message_id=int(msg.message_id),
                    is_active=True,
                ).on_conflict_do_update(
                    constraint="uq_active_signal_msg_user_signal",
                    set_={"message_id": int(msg.message_id), "is_active": True},
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as _e:
            logger.debug(f"[engage] Failed to save ActiveSignalMessage: {_e}")
    except Exception:
        # Fallback: send without buttons so the signal still reaches the user
        await bot.send_message(chat_id=chat_id, text=text)


def _send_signal_with_engagement_sync(
    bot: Bot,
    chat_id: int,
    text: str,
    signal_id: str,
    telegram_user_id: int,
    signal: dict | None = None,
) -> None:
    """Sync wrapper for _send_signal_with_engagement_async."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        run_sync(_send_signal_with_engagement_async(
            bot, int(chat_id), str(text), str(signal_id), int(telegram_user_id), signal
        ))
        return
    try:
        loop.create_task(_send_signal_with_engagement_async(
            bot, int(chat_id), str(text), str(signal_id), int(telegram_user_id), signal
        ))
    except Exception as _e:
        logger.debug(f"[send_signal] Failed to schedule engagement send: {_e}")


def _send_message_sync(bot: Bot, chat_id: int, text: str, parse_mode: str | None = None) -> None:
    """Send a Telegram message from sync code.

    python-telegram-bot v20+ uses async methods. The engine and APScheduler jobs
    run in sync contexts, so we bridge with asyncio.
    """

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        run_sync(_send_message_async(bot, int(chat_id), str(text), parse_mode=parse_mode))
        return
    # If we're already in an event loop, schedule it.
    try:
        loop.create_task(_send_message_async(bot, int(chat_id), str(text), parse_mode=parse_mode))
    except Exception as e:
        logger.debug(f"[send_message] Failed to create async task for message: {e}")
        pass


def _audit_handler(command_name: str, handler):
    async def _inner(update, context):
        # IMPORTANT: Skip pre-audit for /start.
        # The audit writer creates the user row (via record_bot_event -> get_or_create_user).
        # That would make start_command see the user as "not new" and prevent referral attribution.
        # start_command already handles user creation + start auditing in a single transaction.
        if str(command_name) == "start":
            return await handler(update, context)

        try:
            from db.session import get_engine_for_event_loop, get_session
            engine = get_engine_for_event_loop()
            if engine is not None and getattr(update, "effective_user", None) is not None:
                user_id = int(update.effective_user.id)
                username = None
                try:
                    username = update.effective_user.username
                except Exception:
                    username = None

                meta = {"command": str(command_name)}
                # Avoid logging secrets (e.g., /unlock bypass key)
                if str(command_name) not in {"unlock"}:
                    try:
                        meta["args"] = list(getattr(context, "args", None) or [])
                    except Exception:
                        meta["args"] = None

                async with get_session() as session:
                    try:
                        from db.pg_features import record_bot_event

                        await record_bot_event(
                            session,
                            telegram_user_id=user_id,
                            username=username,
                            event_type="command",
                            meta=meta,
                        )
                        await session.commit()
                    except Exception as e:
                        _log_once(
                            "bot_event_audit_failed",
                            f"[bot] bot_events audit write failed: {type(e).__name__}: {e}",
                        )
        except Exception as e:
            _log_once(
                "bot_event_audit_outer_failed",
                f"[bot] bot_events audit init failed: {type(e).__name__}: {e}",
            )
        try:
            return await handler(update, context)
        except Exception as _cmd_err:
            # Detect DB/connection errors and give the user actionable feedback
            # instead of silent failure.
            _err_lower = str(_cmd_err).lower()
            _is_db_err = any(kw in _err_lower for kw in (
                "connection refused", "could not connect", "no route to host",
                "password authentication failed", "database error",
                "asyncpg", "operational error", "connection pool",
                "ssl", "timeout expired", "could not translate host",
            ))
            if _is_db_err:
                try:
                    if getattr(update, "message", None):
                        await update.message.reply_text(
                            "⚠️ Database connection error. Please try again later."
                        )
                except Exception:
                    pass
            else:
                raise  # Let the on_error handler log unexpected errors

    return _inner


def _require_telegram_token() -> str:
    # Always use centralized config for secrets
    token = getattr(config, 'TELEGRAM_BOT_TOKEN', None)
    if token:
        return token
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN is not set in config. "
        "Set it as an environment variable or in your .env file."
    )

# Outcome tracking notifications with tier-based formatting
def notify_trade_outcome(user_id, strategy, result, ret):
    bot = Bot(token=_require_telegram_token())
    # result: 'tp', 'partial_tp', 'sl', 'invalid', 'summary', 'free_limited'
    
    # Get user tier for appropriate formatting
    tier_raw = resolve_user_tier(user_id)
    tier = (tier_raw or 'FREE').strip().lower()
    
    # Map tier for notifications
    if tier in ('owner', 'admin'):
        user_tier = 'vip'
    elif tier == 'vip':
        user_tier = 'vip'
    elif tier == 'premium':
        user_tier = 'premium'
    else:
        user_tier = 'free'
    
    # Use tier-based notifier for formatted messages
    try:
        # Multi-TP/Partial Exit Support
        tp_levels = strategy.get('tp_levels') or strategy.get('take_profit') or []
        if isinstance(tp_levels, str):
            import ast
            try:
                tp_levels = ast.literal_eval(tp_levels)
            except Exception:
                tp_levels = []
        if isinstance(tp_levels, (float, int)):
            tp_levels = [tp_levels]

        entry = float(strategy.get('entry', 0))
        direction = str(strategy.get('direction', '')).lower()
        # For each TP, check if it was hit and not yet notified
        trade_id = strategy.get('trade_id')
        notified_tps = set(strategy.get('notified_tps', []))

        # --- Outcome notification and feedback prompt ---
        # After sending outcome notification, prompt for feedback (premium/vip only)
        from db.session import get_session, get_engine_for_event_loop
        from db.pg_features import get_user_performance_30d
        import asyncio
        tier_for_feedback = user_tier
        if get_engine_for_event_loop() is not None and user_tier in ("premium", "vip"):
            async def _notify_and_feedback():
                async with get_session() as session:
                    perf = await get_user_performance_30d(session, int(user_id))
                    # Send tailored follow-up/advisory
                    summary = (
                        f"\n\n📈 30D Performance:\n"
                        f"Signals: {perf['total']} | Win Rate: {perf['win_rate']*100:.1f}% | NetR: {perf['net_r'] or 0:.2f}R\n"
                        f"Profit/Loss: {perf['profit_loss_pct']:.2f}%"
                    ) if perf['total'] else ""
                    # Send feedback prompt
                    feedback_msg = (
                        f"\n\nWe value your feedback!\nReply with /feedback {strategy.get('signal_id','')} <rating 1-5|issue> [comment]"
                    )
                    try:
                        await bot.send_message(chat_id=user_id, text=summary + feedback_msg)
                    except Exception as e:
                        logger.warning(f"[notify] Failed to send feedback message to user {user_id}: {e}")
                        pass
            try:
                run_sync(_notify_and_feedback())
            except Exception as e:
                logger.warning(f"[notify] Failed to run notify and feedback: {e}")
                pass

        # Determine which TP(s) to notify
        tp_hit = strategy.get('tp_hit')  # e.g., [1,2] if TP1 and TP2 hit
        if tp_hit is None:
            # Fallback: if result == 'tp', treat as full TP3; if 'partial_tp', as TP1
            if result == 'tp':
                tp_hit = [3]
            elif result == 'partial_tp':
                tp_hit = [1]
            else:
                tp_hit = []
        if isinstance(tp_hit, int):
            tp_hit = [tp_hit]

        for tp_level in tp_hit:
            if tp_level in notified_tps:
                continue  # Already notified
            # Calculate profit percentage for this TP
            tp_price = None
            if tp_levels and len(tp_levels) >= tp_level:
                tp_price = float(tp_levels[tp_level-1])
            else:
                tp_price = float(strategy.get(f'tp{tp_level}', 0))
            if entry > 0 and tp_price > 0:
                if direction == 'long':
                    profit_pct = ((tp_price - entry) / entry) * 100
                else:
                    profit_pct = ((entry - tp_price) / entry) * 100
            else:
                profit_pct = float(strategy.get('percent', 0))
            msg = _tier_notifier.format_tp_hit_notification(strategy, user_tier, tp_level, profit_pct)
            # Send notification
            _send_message_sync(bot, chat_id=user_id, text=msg)
            # Mark as notified (update DB or in-memory as needed)
            notified_tps.add(tp_level)
            # Optionally update Trade.partial_exits in DB here

        # SL notification
        if result == 'sl':
            loss_pct = float(strategy.get('percent', 0))
            if loss_pct > 0:
                loss_pct = -loss_pct  # Make it negative
            msg = _tier_notifier.format_sl_hit_notification(strategy, user_tier, loss_pct)
            _send_message_sync(bot, chat_id=user_id, text=msg)

        # Invalidation notification
        if result == 'invalid':
            msg = _tier_notifier.format_signal_update(
                strategy,
                user_tier,
                'invalidated',
                {'reason': strategy.get('reason', 'Market conditions changed')}
            )
            _send_message_sync(bot, chat_id=user_id, text=msg)

        # Free limited notification
        if result == 'free_limited' and user_tier == 'free':
            msg = (
                "🔒 FREE USER (LIMITED OUTCOME MESSAGE)\n"
                "📊 SIGNAL UPDATE\n\n"
                "A recent trade reached its target.\n\n"
                "Upgrade to Premium to see:\n"
                "• Exact entries & exits\n"
                "• Full performance stats\n"
                "• Real-time alerts"
            )
            _send_message_sync(bot, chat_id=user_id, text=msg)
        elif result == 'free_limited':
            msg = "📊 Trade update."
            _send_message_sync(bot, chat_id=user_id, text=msg)

        if not tp_hit and result not in ('sl', 'invalid', 'free_limited'):
            # Fallback generic notification
            msg = "[Outcome] Trade update."
            _send_message_sync(bot, chat_id=user_id, text=msg)

    except Exception as e:
        # Fallback to old format on error
        def fmt(val, d=2):
            return f"{val:.{d}f}" if isinstance(val, float) else str(val)
        if result == 'tp':
            msg = (
                "✅ TAKE PROFIT HIT — FULL CLOSE\n"
                f"\nAsset: {strategy.get('asset','')}\nTimeframe: {strategy.get('timeframe','')}\nDirection: {strategy.get('direction','').upper()}\n"
                f"\nEntry: {fmt(strategy.get('entry'))}\nExit: {fmt(strategy.get('exit'))}\n"
                f"\nResult: {fmt(strategy.get('r_multiple'))}R ({fmt(strategy.get('percent',0))}%)\nDuration: {strategy.get('duration','')}\nConfidence Score: {fmt(strategy.get('confidence',0))}%\n"
                "\nWell-managed trade ✔️"
            )
            _send_message_sync(bot, chat_id=user_id, text=msg)
        elif result == 'partial_tp':
            msg = (
                "🟢 PARTIAL TAKE PROFIT (TP1)\n"
                f"\nAsset: {strategy.get('asset','')}\nTimeframe: {strategy.get('timeframe','')}\nDirection: {strategy.get('direction','').upper()}\n"
                f"\nEntry: {fmt(strategy.get('entry'))}\nTP1: {fmt(strategy.get('tp1'))}\n"
                f"\nPartial Result: {fmt(strategy.get('r_multiple',0))}R\nRemaining Position: Active"
            )
        elif result == 'sl':
            msg = (
                "❌ STOP LOSS HIT\n"
                f"\nAsset: {strategy.get('asset','')}\nTimeframe: {strategy.get('timeframe','')}\nDirection: {strategy.get('direction','').upper()}\n"
                f"\nEntry: {fmt(strategy.get('entry'))}\nStop Loss: {fmt(strategy.get('stop'))}\n"
                f"\nResult: {fmt(strategy.get('r_multiple',-1))}R ({fmt(strategy.get('percent',0))}%)\nDuration: {strategy.get('duration','')}\n"
                "\nRisk was predefined and controlled."
            )
        elif result == 'invalid':
            msg = (
                "⚠️ SIGNAL INVALIDATED (ADMIN / MARKET EVENT)\n"
                f"\nAsset: {strategy.get('asset','')}\nTimeframe: {strategy.get('timeframe','')}\n"
                f"\nReason: {strategy.get('reason','Unknown')}\nStatus: Closed at market\n\nResult: Flat (0R)"
            )
        elif result == 'free_limited':
            msg = (
                "🔒 FREE USER (LIMITED OUTCOME MESSAGE)\n📊 SIGNAL UPDATE\n\nA recent trade reached its target.\n\nUpgrade to Premium to see:\n• Exact entries & exits\n• Full performance stats\n• Real-time alerts"
            )
        else:
            msg = "[Outcome] Trade update."
    
    _send_message_sync(bot, chat_id=user_id, text=msg)

def notify_all_users_trade_outcome(strategy, result, ret, user_ids=None):
    bot = Bot(token=_require_telegram_token())
    if user_ids is None:
        user_ids = get_all_user_ids_compat()
    # Use the same message format as notify_trade_outcome, but for all users
    for uid in user_ids:
        notify_trade_outcome(uid, strategy, result, ret)

def send_performance_summary(user_id):
    bot = Bot(token=_require_telegram_token())
    # Example daily summary message
    stats = performance_tracker.get_stats()
    total = sum(s['trades'] for s in stats.values())
    wins = sum(int(s['win_rate']*s['trades']) for s in stats.values())
    losses = total - wins
    win_rate = (wins/total*100) if total else 0
    net_r = sum(s['avg_return']*s['trades'] for s in stats.values())
    msg = (
        "📊 DAILY PERFORMANCE SUMMARY (AUTO)\n\n"
        f"Total Signals: {total}\nWins: {wins}\nLosses: {losses}\nWin Rate: {win_rate:.1f}%\nNet Result: {net_r:.2f}R\n\nConsistency over frequency."
    )
    _send_message_sync(bot, chat_id=user_id, text=msg)

def _format_free_preview(signal):
    # Limited info to drive upgrades (no exact levels)
    return (
        "🔒 FREE USER (LIMITED SIGNAL)\n\n"
        f"Reference: {signal.get('signal_id') or signal.get('id')}\n"
        f"Asset: {signal.get('asset')}\n"
        f"Timeframe: {signal.get('timeframe')}\n"
        f"Direction: {signal.get('direction')}\n\n"
        "Upgrade to Premium to see:\n"
        "• Exact entry, stop, target\n"
        "• Real-time alerts\n"
        "• Full performance tracking"
    )

def _format_free_delayed_digest(items: list) -> str:
    """Format a list of free-tier delayed signal queue items into a Telegram message.

    Each item is a dict with keys: id, signal_id, asset, timeframe, direction, score.
    """
    if not items:
        return "📊 No signals available right now."

    lines = [
        f"📊 *SignalRankAI — Daily Signal Digest*",
        f"_{len(items)} signal(s) selected for you today_\n",
    ]
    for i, item in enumerate(items, 1):
        asset     = str(item.get("asset") or "")
        tf        = str(item.get("timeframe") or "")
        direction = str(item.get("direction") or "").upper()
        score     = int(item.get("score") or 0)
        sig_ref   = str(item.get("signal_id") or "")[:8]
        arrow     = "📈" if direction == "LONG" else "📉"
        lines.append(
            f"{i}. {arrow} *{asset}* · `{tf}`\n"
            f"   Direction: {direction}\n"
            f"   Ref: `{sig_ref}` · Score: {score}/100"
        )

    lines.append(
        "\n🔒 _Upgrade to Premium for exact entry, stop-loss & take-profit levels._\n"
        "Use /upgrade to subscribe."
    )
    return "\n\n".join(lines)


def dispatch_signals(strategy_signals, user_id, regime=None):
    """Dispatch signals to user based on their tier.
    
    Tier-based Limits & Score Filtering:
    - OWNER: 9999 signals/day (all signals, real-time, no score filter)
    - ADMIN: 9999 signals/day (all signals, real-time, no score filter)
    - VIP: 30 signals/day (score >= 72 only, real-time)
    - PREMIUM: 10 signals/day (score 55-80, real-time)
    - FREE: 2 random signals/day (delayed queue, bot picks any from global pool)
    - EXTRA: 1 signal per purchase (highest scoring available, real-time)
    
    FREE tier: Bot queues ALL generated signals to global pool, then randomly 
    distributes to FREE users (different users get different signals).
    
    EXTRA signals: When FREE users buy extra signals, they get the highest scoring
    ongoing signal that hasn't been sent to them yet.
    
    Outcomes are sent for ALL signals (crypto and FX) regardless of tier.
    """

    tier_raw = resolve_user_tier(user_id)
    tier = (tier_raw or 'FREE').strip().lower()

    # Free users with paid extra-signal quota receive highest scoring signal
    extra_left = 0
    if tier == 'free':
        try:
            extra_left = int(state.get_extra_signals_left_sync(int(user_id)) or 0)
        except Exception:
            extra_left = 0

    # Global kill-switch (do not dispatch/queue)
    try:
        if state.get_killswitch_sync().enabled:
            return
    except Exception as e:
        logger.debug(f"[dispatch] Failed to check killswitch: {e}")
        pass

    # Support passing ranked buckets (vip/premium/free)
    signals_list = []
    if isinstance(strategy_signals, dict):
        vip_list = list(strategy_signals.get('vip', []) or [])
        prem_list = list(strategy_signals.get('premium', []) or [])
        # Tier-based signal selection with score thresholds
        if tier in ('owner', 'admin'):
            signals_list = vip_list + prem_list
        elif tier in ('vip',):
            signals_list = [s for s in (vip_list + prem_list) if s.get('score', 0) >= 55.0]
        elif tier in ('premium',):
            signals_list = [s for s in (vip_list + prem_list) if s.get('score', 0) >= 55.0]
        else:  # FREE
            signals_list = (vip_list + prem_list)
    else:
        signals_list = list(strategy_signals or [])

    # --- USER PREFERENCES FILTERING ---
    try:
        from .user_prefs import user_prefs_store
        prefs = user_prefs_store.get_prefs(user_id)
        assets = set([a.upper() for a in prefs.get('assets', set())]) if prefs.get('assets') else None
        timeframes = set([tf.lower() for tf in prefs.get('timeframes', set())]) if prefs.get('timeframes') else None
        strategies = set([s.lower() for s in prefs.get('strategies', set())]) if prefs.get('strategies') else None
        if assets or timeframes or strategies:
            filtered = []
            for sig in signals_list:
                asset_ok = True
                tf_ok = True
                strat_ok = True
                if assets:
                    asset = str(sig.get('asset') or sig.get('symbol') or '').upper()
                    asset_ok = asset in assets
                if timeframes:
                    tf = str(sig.get('timeframe') or '').lower()
                    tf_ok = tf in timeframes
                if strategies:
                    strat = str(sig.get('strategy_name') or sig.get('strategy') or '').lower()
                    strat_ok = strat in strategies
                if asset_ok and tf_ok and strat_ok:
                    filtered.append(sig)
            signals_list = filtered
    except Exception as e:
        _log_once('user_prefs_filter_error', f'[dispatch] User prefs filter error: {e}')

    if not signals_list:
        return

    # --- FRESHNESS FILTERING ---
    # Filter out stale signals before delivery
    try:
        from engine.price_validator import is_signal_stale, enrich_signal_with_live_price
        
        fresh_signals = []
        for sig in signals_list:
            # Enrich with current price and age info
            try:
                sig = enrich_signal_with_live_price(sig)
            except Exception as e:
                logger.debug(f"[dispatch] Failed to enrich signal {sig.get('signal_id')}: {e}")
            
            # Check if stale
            if is_signal_stale(sig):
                sig_id = sig.get('signal_id') or sig.get('id', 'unknown')
                asset = sig.get('asset', 'unknown')
                age_seconds = sig.get('signal_age_seconds', 'unknown')
                logger.info(f"[dispatch] Filtered stale signal {sig_id} for user {user_id}: age={age_seconds}s asset={asset}")
            else:
                fresh_signals.append(sig)
        
        signals_list = fresh_signals
        
        if not signals_list:
            logger.info(f"[dispatch] All signals filtered as stale for user {user_id}")
            return
    except Exception as e:
        logger.warning(f"[dispatch] Freshness filtering failed for user {user_id}: {e}")
        # Continue with unfiltered signals on error

    # Entry validation: check that current price is within entry zone (±3%)
    # Add entry_status flag to track if entry has been hit or is pending
    def _check_entry_status(signal: dict) -> tuple[bool, str]:
        """
        Check if entry is valid and return (allow: bool, status: str).
        Status can be: "PENDING_ENTRY" (price >3% away), "AT_ENTRY" (price ±3%), "ENTRY_MISSED" (>3% away, hard reject)
        """
        try:
            asset = str(signal.get("asset") or "").upper()
            entry = float(signal.get("entry") or 0.0)
            if not asset or entry <= 0:
                return True, "UNKNOWN"  # Can't validate, allow through
            
            # Fetch current price
            try:
                import requests
                is_crypto = asset.endswith("USDT") or asset.endswith("USDC")
                if not is_crypto:
                    return True, "UNKNOWN"  # Skip FX validation for now
                
                # Try Binance first, then CryptoCompare fallback
                sym = asset.replace("USDT", "").replace("USDC", "")
                try:
                    resp = requests.get(
                        f"https://api.binance.com/api/v3/ticker/price",
                        params={"symbol": asset},
                        timeout=5,
                    )
                    if resp.ok:
                        price = float(resp.json().get("price", entry))
                    else:
                        raise Exception("Binance failed")
                except Exception:
                    # Fallback to CryptoCompare
                    api_key = (getattr(config, "CRYPTOCOMPARE_API_KEY", "") or "").strip()
                    headers = {"authorization": f"Apikey {api_key}"} if api_key else {}
                    resp = requests.get(
                        "https://min-api.cryptocompare.com/data/price",
                        params={"fsym": sym, "tsyms": "USDT,USD"},
                        headers=headers,
                        timeout=5,
                    )
                    if resp.ok:
                        data = resp.json()
                        price = float(data.get("USDT") or data.get("USD") or entry)
                    else:
                        return True, "UNKNOWN"  # Can't validate, allow through
                
                # Check if price is within ±3% of entry
                price_distance_pct = abs(price - entry) / entry * 100.0
                
                # Determine entry status
                if price_distance_pct <= 3.0:
                    # Price is at entry (within tolerance)
                    return True, "AT_ENTRY"
                elif price < entry:
                    # Price is below entry (pending long entry)
                    return True, "PENDING_ENTRY"
                else:
                    # Price is above entry (potential miss)
                    return True, "PENDING_ENTRY"
            except Exception:
                return True, "UNKNOWN"  # On error, allow signal through
        except Exception:
            return True, "UNKNOWN"

    # Add entry_status flag to all signals
    try:
        for signal in signals_list:
            allow, status = _check_entry_status(signal)
            signal["entry_status"] = status
            signal["current_price_pct"] = None  # Will be populated on display
    except Exception as e:
        _log_once(
            "entry_status_error",
            f"[dispatch] Entry status error: {e}",
        )

    if not signals_list:
        return

    # DEBUG: Removing deduplication - send all signals to all users
    try:
        print(f"[DEBUG][dispatch] User {user_id} tier={tier} signals_list={len(signals_list)}", flush=True)
        for sig in signals_list:
            print(f"[DEBUG][dispatch] Preparing to send signal: {sig.get('asset')} {sig.get('timeframe')} score={sig.get('score')} id={sig.get('signal_id', 'n/a')}", flush=True)
    except Exception as e:
        print(f"[DEBUG][dispatch] Error in debug logging: {e}", flush=True)

    # Postgres-backed delivery dedup + history (preferred)
    try:
        from db.session import get_engine_for_event_loop, get_session
        engine = get_engine_for_event_loop()

        if engine is not None:
            effective_tier = tier
            display_tier = tier
            
            # OWNER and ADMIN always get VIP format for ALL notifications
            if tier in ('owner', 'admin'):
                display_tier = 'vip'
                effective_tier = tier  # Keep actual tier for delivery tracking
            elif tier == 'free' and extra_left > 0:
                effective_tier = 'premium'
                display_tier = 'premium'


            if effective_tier in ('premium', 'vip', 'owner', 'admin'):
                bot = Bot(token=_require_telegram_token())
                limit = TIER_LIMITS.get(tier, 0)
                if tier == 'free' and extra_left > 0:
                    limit = min(int(max(1, extra_left)), len(signals_list))

                async def _reserve() -> list[dict]:
                    from db.pg_features import get_or_create_signal, record_signal_delivery

                    to_send: list[dict] = []
                    async with get_session() as session:
                        for signal in signals_list[: max(0, int(limit))]:
                            s = await get_or_create_signal(session, signal)
                            print(f"[DEBUG][db] Attempting to record delivery: user={user_id} signal_id={s.signal_id} tier={effective_tier}", flush=True)
                            ok = await record_signal_delivery(
                                session,
                                telegram_user_id=int(user_id),
                                signal_id=str(s.signal_id),
                                tier_at_send=str(effective_tier),
                            )
                            print(f"[DEBUG][db] record_signal_delivery result: {ok}", flush=True)
                            payload = dict(signal)
                            payload["signal_id"] = str(s.signal_id)
                            payload.setdefault("asset", s.asset)
                            payload.setdefault("timeframe", s.timeframe)
                            payload.setdefault("direction", s.direction)
                            payload.setdefault("entry", s.entry)
                            payload.setdefault("stop_loss", s.stop_loss)
                            payload.setdefault("take_profit", s.take_profit)
                            payload.setdefault("rr_ratio", s.rr_estimate)
                            payload.setdefault("score", s.score)
                            payload.setdefault("regime", s.regime)
                            to_send.append(payload)
                        await session.commit()
                    return to_send

                try:
                    reserved = run_sync(_reserve())
                    reserve_failed = False
                except Exception as e:
                    reserved = []
                    reserve_failed = True
                    print(f"[DEBUG][db] dispatch reserve failed (falling back to direct send): {type(e).__name__}: {e}", flush=True)

                print(f"[DEBUG][dispatch] user={user_id} tier={tier} effective_tier={effective_tier} signals={len(signals_list)} limit={int(limit)} reserved={len(reserved)} reserve_failed={int(reserve_failed)}", flush=True)

                if reserve_failed:
                    sent = 0
                    for signal in signals_list:
                        if sent >= int(limit):
                            break
                        try:
                            print(f"[DEBUG][dispatch] Fallback direct send: user={user_id} signal={signal.get('asset')} id={signal.get('signal_id', 'n/a')}", flush=True)
                            _send_message_sync(bot, chat_id=user_id, text=format_signal(signal, display_tier=display_tier))
                            sent += 1
                            if tier == 'free' and extra_left > 0:
                                try:
                                    state.consume_extra_signals_sync(int(user_id), 1)
                                except Exception as e:
                                    logger.debug(f"[dispatch] Failed to consume extra signal for user {user_id}: {e}")
                                    pass
                        except Exception as e:
                            print(f"[DEBUG][dispatch] Exception in fallback send: {e}", flush=True)
                            continue
                    return

                for signal in reserved:
                    try:
                        print(f"[DEBUG][dispatch] Sending reserved signal: user={user_id} signal={signal.get('asset')} id={signal.get('signal_id', 'n/a')}", flush=True)
                        _send_signal_with_engagement_sync(
                            bot,
                            chat_id=user_id,
                            text=format_signal(signal, display_tier=display_tier),
                            signal_id=str(signal.get('signal_id', '')),
                            telegram_user_id=int(user_id),
                            signal=signal,
                        )
                        if tier == 'free' and extra_left > 0:
                            try:
                                state.consume_extra_signals_sync(int(user_id), 1)
                            except Exception as e:
                                logger.debug(f"[dispatch] Failed to consume extra signal for user {user_id}: {e}")
                                pass
                    except Exception as e:
                        print(f"[DEBUG][dispatch] Exception in reserved send: {e}", flush=True)
                        continue
                return

            # FREE with extra signals: send highest scoring available signal immediately
            if tier == 'free' and extra_left > 0:
                bot = Bot(token=_require_telegram_token())
                
                async def _get_best_signal():
                    from db.pg_features import get_highest_scoring_available_signal_for_user, record_signal_delivery
                    async with get_session() as session:
                        sent_count = 0
                        for _ in range(min(extra_left, len(signals_list))):
                            best_sig = await get_highest_scoring_available_signal_for_user(
                                session, int(user_id)
                            )
                            if not best_sig:
                                break
                            
                            # Record delivery
                            ok = await record_signal_delivery(
                                session,
                                telegram_user_id=int(user_id),
                                signal_id=str(best_sig.signal_id),
                                tier_at_send='premium',  # Extra signals get premium formatting
                            )
                            if ok:
                                # Build signal dict for formatting with all VIP fields
                                import json
                                tp_parsed = best_sig.take_profit
                                try:
                                    # Parse JSON-encoded TP list
                                    if isinstance(best_sig.take_profit, str):
                                        tp_parsed = json.loads(best_sig.take_profit)
                                except Exception as e:
                                    logger.debug(f"[dispatch] Failed to parse TP levels: {e}")
                                    pass
                                
                                sig_dict = {
                                    "signal_id": best_sig.signal_id,
                                    "asset": best_sig.asset,
                                    "timeframe": best_sig.timeframe,
                                    "direction": best_sig.direction,
                                    "entry": best_sig.entry,
                                    "stop_loss": best_sig.stop_loss,
                                    "take_profit": tp_parsed,
                                    "rr_ratio": best_sig.rr_estimate,
                                    "score": best_sig.score,
                                    "regime": getattr(best_sig, 'regime', 'NEUTRAL'),
                                    # VIP-specific fields
                                    "session": getattr(best_sig, 'session', ''),
                                    "market_regime": getattr(best_sig, 'regime', ''),
                                    "confluence": getattr(best_sig, 'confluence', None),
                                    "htf_bias": getattr(best_sig, 'htf_bias', None),
                                    "risk_reward": best_sig.rr_estimate,
                                    "invalidation": getattr(best_sig, 'invalidation', None),
                                    "trade_logic": getattr(best_sig, 'trade_logic', None),
                                    "strategy": best_sig.strategy_name,
                                }
                                try:
                                    # Determine display tier: VIP for owner/admin, PREMIUM otherwise
                                    from signalrank_telegram.access import resolve_user_tier
                                    user_tier = resolve_user_tier(user_id).lower()
                                    signal_display_tier = 'vip' if user_tier in ('owner', 'admin') else 'premium'
                                    _send_message_sync(bot, chat_id=user_id, text=format_signal(sig_dict, display_tier=signal_display_tier))
                                    sent_count += 1
                                    state.consume_extra_signals_sync(int(user_id), 1)
                                except Exception as e:
                                    logger.warning(f"[dispatch] Failed to send extra signal to user {user_id}: {e}")
                                    pass
                        await session.commit()
                        return sent_count
                
                try:
                    run_sync(_get_best_signal())
                except Exception as e:
                    _log_once(
                        "extra_signal_failed",
                        f"[bot] extra signal delivery failed: {type(e).__name__}: {e}",
                    )

            # FREE users: send completely random signals at random times (bot decides when)
            # Bot picks ANY signals at random - different users get different random signals
            # Bot also decides WHEN to send: randomly picks times during day to check and send signals
            async def _send_random_signals_immediately() -> None:
                from db.pg_features import (
                    get_random_available_signals_for_free_user, 
                    record_signal_delivery,
                    get_user_next_signal_time,
                    set_user_next_signal_time
                )
                from db.models import User
                from sqlalchemy import select
                import random
                from datetime import datetime, timedelta
                from typing import Awaitable, Callable, cast
                from sqlalchemy.ext.asyncio import AsyncSession

                SetUserNextSignalTime = Callable[[AsyncSession, int, int, datetime], Awaitable[None]]
                set_user_next_signal_time_typed: SetUserNextSignalTime = cast(
                    SetUserNextSignalTime, set_user_next_signal_time
                )

                bot = Bot(token=_require_telegram_token())
                
                async with get_session() as session:
                    # Get user
                    res_user = await session.execute(
                        select(User).where(User.telegram_user_id == int(user_id))
                    )
                    user = res_user.scalar_one_or_none()
                    if not user:
                        return
                    
                    # Check how many signals user already received today using Redis
                    from core.redis_state import state
                    from core.tier_constants import TIER_DAILY_LIMITS
                    from signalrank_telegram.access import resolve_user_tier
                    
                    date_str = datetime.utcnow().strftime('%Y-%m-%d')
                    redis_key = f"signals_sent:{user_id}:{date_str}"
                    signals_sent_today = 0
                    try:
                        signals_sent_today = int(state.get_sync(redis_key) or 0)
                    except Exception:
                        signals_sent_today = 0
                    
                    # Get user's actual tier for accurate logging
                    user_tier_actual = 'free'
                    try:
                        user_tier_actual = resolve_user_tier(user_id).lower()
                    except Exception:
                        user_tier_actual = 'free'
                    
                    # Get tier limit from constants
                    daily_limit = TIER_DAILY_LIMITS.get(user_tier_actual, 2)
                    remaining = max(0, daily_limit - signals_sent_today) if daily_limit != float('inf') else 999
                    
                    if remaining <= 0:
                        logger.info(f"[bot] daily limit reached for user={user_id} tier={user_tier_actual} sent={signals_sent_today}")
                        return  # Already hit daily limit
                    
                    # Get completely random available signals (bot's choice - no quality filter)
                    # Different users get different random signals from the same pool
                    available_signals = await get_random_available_signals_for_free_user(
                        session, int(user_id), limit=remaining
                    )
                    
                    if not available_signals:
                        return  # No signals available
                    
                    # Send each signal
                    for sig in available_signals:
                        # Record delivery
                        ok = await record_signal_delivery(
                            session,
                            telegram_user_id=int(user_id),
                            signal_id=str(sig.signal_id),
                            tier_at_send='free',
                        )
                        
                        if ok:
                            # Build signal dict with all VIP fields
                            import json
                            tp_parsed = sig.take_profit
                            try:
                                # Parse JSON-encoded TP list
                                if isinstance(sig.take_profit, str):
                                    tp_parsed = json.loads(sig.take_profit)
                            except Exception as e:
                                logger.debug(f"[dispatch] Failed to parse TP levels: {e}")
                                pass
                            
                            sig_dict = {
                                "signal_id": sig.signal_id,
                                "asset": sig.asset,
                                "timeframe": sig.timeframe,
                                "direction": sig.direction,
                                "entry": sig.entry,
                                "stop_loss": sig.stop_loss,
                                "take_profit": tp_parsed,
                                "rr_ratio": sig.rr_estimate,
                                "score": sig.score,
                                "regime": getattr(sig, 'regime', 'NEUTRAL'),
                                # VIP-specific fields
                                "session": getattr(sig, 'session', ''),
                                "market_regime": getattr(sig, 'regime', ''),
                                "confluence": getattr(sig, 'confluence', None),
                                "htf_bias": getattr(sig, 'htf_bias', None),
                                "risk_reward": sig.rr_estimate,
                                "invalidation": getattr(sig, 'invalidation', None),
                                "trade_logic": getattr(sig, 'trade_logic', None),
                                "strategy": sig.strategy_name,
                            }
                            try:
                                # Determine display tier: VIP for owner/admin, FREE for others
                                from signalrank_telegram.access import resolve_user_tier
                                user_tier = resolve_user_tier(user_id).lower()
                                signal_display_tier = 'vip' if user_tier in ('owner', 'admin') else 'free'
                                _send_message_sync(bot, chat_id=user_id, text=format_signal(sig_dict, display_tier=signal_display_tier))
                                # Mark as delivered in Redis
                                try:
                                    mark_signal_delivered_sync(user_id, str(sig_dict.get('signal_id')))
                                except Exception as e:
                                    logger.debug(f"[dispatch] Failed to mark signal as delivered in Redis: {e}")
                                    pass
                                # Increment daily counter
                                try:
                                    from core.redis_state import state
                                    state.incr_sync(redis_key, ex=86400)
                                except Exception as e:
                                    logger.debug(f"[dispatch] Failed to increment daily counter in Redis: {e}")
                                    pass
                            except Exception as e:
                                logger.debug(f"[dispatch] Failed to track signal delivery in Redis: {e}")
                                pass
                    
                    await session.commit()

            try:
                run_sync(_send_random_signals_immediately())
                return
            except Exception as e:
                _log_once(
                    "free_random_send_failed",
                    f"[bot] free random signal delivery failed: {type(e).__name__}: {e}",
                )
    except Exception as e:
        _log_once(
            "dispatch_pg_path_failed",
            f"[bot] dispatch postgres path failed: {type(e).__name__}: {e}",
        )

    if tier in ('premium', 'vip', 'owner', 'admin'):
        from core.redis_state import state
        from core.tier_constants import TIER_DAILY_LIMITS
        from datetime import datetime
        
        # Check daily limit
        date_str = datetime.utcnow().strftime('%Y-%m-%d')
        redis_key = f"signals_sent:{user_id}:{date_str}"
        signals_sent_today = 0
        try:
            signals_sent_today = int(state.get_sync(redis_key) or 0)
        except Exception:
            signals_sent_today = 0
        
        daily_limit = TIER_DAILY_LIMITS.get(tier, 2)
        
        if signals_sent_today >= daily_limit:
            logger.info(f"[bot] daily limit reached for user={user_id} tier={tier} sent={signals_sent_today}")
            return
        
        bot = Bot(token=_require_telegram_token())
        limit = TIER_LIMITS.get(tier, 0)
        sent = 0
        # OWNER and ADMIN always get VIP format
        display_tier = 'vip' if tier in ('owner', 'admin') else tier
        for signal in signals_list:
            # Check if we've hit the daily limit
            if signals_sent_today + sent >= daily_limit:
                break
            if sent >= limit:
                break
            try:
                _send_message_sync(bot, chat_id=user_id, text=format_signal(signal, display_tier=display_tier))
                # Mark as delivered in Redis
                try:
                    mark_signal_delivered_sync(user_id, str(signal.get('signal_id')))
                except Exception as e:
                    logger.debug(f"[dispatch] Failed to mark signal as delivered in Redis for user {user_id}: {e}")
                    pass
                # Increment daily counter
                try:
                    state.incr_sync(redis_key, ex=86400)
                except Exception as e:
                    logger.debug(f"[dispatch] Failed to increment daily counter in Redis for user {user_id}: {e}")
                    pass
                sent += 1
            except Exception as e:
                logger.warning(f"[dispatch] Failed to dispatch signal to user {user_id}: {e}")
                continue
        return

    # FREE: queue delayed summary (max 3/day)
    try:
        from db.session import get_engine_for_event_loop, get_session
        engine = get_engine_for_event_loop()
        if engine is None:
            raise RuntimeError("DATABASE_URL not configured. Postgres is required.")
        daily_limit = 3

        async def _queue() -> None:
            from db.pg_features import queue_free_signal_summary as queue_free_signal_summary_pg

            async with get_session() as session:
                # Queue any signals the bot generates (no score sorting - bot decides)
                for signal in signals_list:
                    ok = await queue_free_signal_summary_pg(
                        session,
                        telegram_user_id=int(user_id),
                        signal=signal,
                        daily_limit=int(daily_limit),
                    )
                    if not ok:
                        break
                await session.commit()

        try:
            run_sync(_queue())
        except Exception as e:
            _log_once(
                "queue_free_legacy_failed",
                f"[bot] queue free (legacy path) failed: {type(e).__name__}: {e}",
            )
    except Exception:
        # As a last resort, send the limited preview
        try:
            bot = Bot(token=_require_telegram_token())
            _send_message_sync(bot, chat_id=user_id, text=_format_free_preview(signals_list[0]))
        except Exception as e:
            logger.warning(f"[dispatch] Failed to send free preview to user {user_id}: {e}")
            pass


def downgrade_expired_subscriptions_job():
    """Daily job: downgrade expired subscriptions to FREE tier."""
    logger.info("🔄 Checking for expired subscriptions...")
    try:
        from db.session import get_session
        from db.pg_features import downgrade_expired_subscriptions

        async def _do_downgrade():
            async with get_session() as session:
                count = await downgrade_expired_subscriptions(session)
                if count > 0:
                    logger.info(f"📉 Downgraded {count} user(s) to FREE tier")
                    await session.commit()
                else:
                    logger.info("✅ No expired subscriptions to downgrade")

        run_sync(_do_downgrade())
    except Exception as e:
        logger.error(f"❌ Error downgrading subscriptions: {e}")


def auto_delete_old_signals_job():
    """Weekly job: hard delete signals older than 7 days."""
    logger.info("🗑️ Deleting old signals (>7 days)...")
    try:
        from db.session import get_session
        from db.pg_features import delete_old_signals

        async def _do_delete():
            async with get_session() as session:
                count = await delete_old_signals(session, older_than_days=7)
                if count > 0:
                    logger.info(f"🗑️ Deleted {count} old signal(s)")
                    await session.commit()
                else:
                    logger.info("✅ No old signals to delete")

        run_sync(_do_delete())
    except Exception as e:
        logger.error(f"❌ Error deleting old signals: {e}")


def distribute_random_signals_to_free_users_job():
    """Periodic job: distribute random signals to FREE users from global pool."""
    logger.info("🎲 Distributing random signals to FREE users...")
    try:
        from db.session import get_session
        from db.pg_features import queue_random_free_signals_for_all_users

        async def _do_distribute():
            async with get_session() as session:
                count = await queue_random_free_signals_for_all_users(session)
                if count > 0:
                    logger.info(f"📬 Queued signals for {count} FREE user(s)")
                    await session.commit()
                else:
                    logger.info("✅ All FREE users have reached daily limit or no new signals")

        run_sync(_do_distribute())
    except Exception as e:
        logger.error(f"❌ Error distributing signals to FREE users: {e}")


_bot_lock_conn = None

# ── Webhook mode module-level state ──────────────────────────────────────────
# When TELEGRAM_USE_WEBHOOK=1, run_bot() stores the fully-configured Application
# here instead of blocking in run_polling().  railway_main.py reads this variable
# after run_bot() returns to obtain the application for process_update() calls.
_webhook_application = None
_bot_scheduler = None  # keeps the BackgroundScheduler alive after run_bot() returns

def run_bot() -> None:
    """Run the Telegram polling bot.

    This must be explicitly invoked (e.g. RUN_MODE=bot or RUN_MODE=all). It must
    not run on import.
    """

    from apscheduler.schedulers.background import BackgroundScheduler

    # ── Bulletproof DATABASE_URL validation ─────────────────────────────────
    # Validate DATABASE_URL BEFORE any scheduler job or async session is
    # created.  If it is missing, raise immediately so Railway shows a clear
    # crash message rather than hundreds of "password authentication failed
    # for user 'postgres'" errors from asyncpg falling back to local auth.
    _db_raw = (os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL") or "").strip()
    if not _db_raw:
        raise ValueError(
            "[FATAL] DATABASE_URL is not set. "
            "Add it as an environment variable on Railway before deploying."
        )
    # Safe log: print only the host portion, never the password.
    try:
        _db_host_part = _db_raw.split("@")[-1]  # e.g. 'monorail.proxy.rlwy.net:54321/railway'
        print(f"[boot] Connecting to DB at: {_db_host_part}", flush=True)
    except Exception:
        print("[boot] DATABASE_URL is set (host masked)", flush=True)
    # Force the global async engine to re-initialise using the fresh env value.
    # This is needed if session.py was imported before the env var was set
    # (e.g. in a hot-reload scenario) and the cached engine is None.
    try:
        from db.session import _get_global_engine, _global_engine
        if _global_engine is None:
            _get_global_engine()  # triggers engine creation with correct URL
    except Exception as _eng_err:
        print(f"[boot] DB engine init: {_eng_err}", flush=True)
    # ───────────────────────────────────────────────────────────────────────

    # Avoid leaking bot token in logs: httpx logs full request URLs at INFO.
    # We keep errors, but silence INFO/DEBUG.
    try:
        logging.getLogger("httpx").setLevel(logging.WARNING)
    except Exception as e:
        logger.debug(f"[bot] Failed to set httpx logging level: {e}")
        pass
    try:
        logging.getLogger("telegram").setLevel(logging.WARNING)
    except Exception as e:
        logger.debug(f"[bot] Failed to set telegram logging level: {e}")
        pass

    application = (
        Application.builder()
        .token(_require_telegram_token())
        .pool_timeout(TELEGRAM_POOL_TIMEOUT)
        .connect_timeout(TELEGRAM_CONNECT_TIMEOUT)
        .read_timeout(TELEGRAM_READ_TIMEOUT)
        .write_timeout(TELEGRAM_WRITE_TIMEOUT)
        .build()
    )

    # Ensure required schema exists — belt-and-suspenders patch for any live DB
    # that was bootstrapped before Alembic migration 0010_consolidate_full_schema ran.
    # Every statement uses IF NOT EXISTS / ADD COLUMN IF NOT EXISTS so it is safe
    # to run against any DB state on every bot restart.
    try:
        from db.session import is_db_configured, get_session
        from sqlalchemy import text

        if is_db_configured():
            async def _ensure_schema() -> None:
                _stmts = [
                    # users — columns added after 0001_init / 0008_user_tier_column
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS premium_until TIMESTAMP",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS fixed_lot_size FLOAT NOT NULL DEFAULT 0.01",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_executions_today INTEGER NOT NULL DEFAULT 0",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_executions_reset_at TIMESTAMP",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS max_risk_percentage FLOAT NOT NULL DEFAULT 1.0",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS paystack_subscription_code VARCHAR(128)",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS paystack_customer_code VARCHAR(128)",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_renew BOOLEAN NOT NULL DEFAULT TRUE",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_count INTEGER DEFAULT 0",
                    # subscriptions
                    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS bonus_days INTEGER NOT NULL DEFAULT 0",
                    # signals
                    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS ml_probability FLOAT",
                    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP",
                    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS expired BOOLEAN NOT NULL DEFAULT FALSE",
                    "ALTER TABLE signals ADD COLUMN IF NOT EXISTS is_near_order_block BOOLEAN NOT NULL DEFAULT FALSE",
                    # referrals
                    "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS is_successful BOOLEAN NOT NULL DEFAULT FALSE",
                    "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS reward_applied BOOLEAN NOT NULL DEFAULT FALSE",
                    "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS successful_at TIMESTAMP",
                    "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS referrer_notified_at TIMESTAMP",
                    # managed_assets
                    "ALTER TABLE managed_assets ADD COLUMN IF NOT EXISTS last_analyzed_at TIMESTAMP",
                ]
                async with get_session() as session:
                    for stmt in _stmts:
                        try:
                            await session.execute(text(stmt))
                        except Exception:
                            pass  # Column/table may already exist
                    await session.commit()

            run_sync(_ensure_schema())
    except Exception as e:
        _log_once("ensure_schema_failed", f"[bot] schema ensure failed: {type(e).__name__}: {e}")

    # Advisory lock: only needed in polling mode to prevent duplicate pollers
    # across Railway replicas.  In webhook mode Telegram delivers each update
    # exactly once to the registered URL, so the lock is unnecessary.
    if not os.getenv("TELEGRAM_USE_WEBHOOK"):
        try:
            import psycopg2

            lock_id = int(os.getenv("TELEGRAM_BOT_LOCK_ID", "739105"))
            dsn = (os.getenv("DATABASE_URL") or "").strip()
            if dsn.startswith("postgresql+asyncpg://"):
                dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)

            if dsn:
                conn = psycopg2.connect(dsn, connect_timeout=5)
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,))
                    locked = bool(cur.fetchone()[0])
                if not locked:
                    try:
                        conn.close()
                    except Exception as e:
                        logger.debug(f"[boot] Failed to close database connection: {e}")
                        pass
                    print("[boot] telegram bot polling skipped: another instance holds the lock", flush=True)
                    return
                global _bot_lock_conn
                _bot_lock_conn = conn
        except Exception:
            # If DB is unavailable or lock fails, fall back to running (single-instance environments).
            pass

    async def _on_error(update, context) -> None:
        err = getattr(context, "error", None)
        print(f"[bot] error: {err}", flush=True)
        # Alert all owners about every unhandled exception so nothing is silent
        try:
            import traceback
            tb = "".join(traceback.format_exception(type(err), err, err.__traceback__)) if err else "(no traceback)"
            alert = f"🚨 *Bot Error*\n`{type(err).__name__}: {err}`\n\n```\n{tb[:800]}\n```"
            from config import OWNER_IDS
            for _oid in (OWNER_IDS or []):
                try:
                    await application.bot.send_message(
                        chat_id=int(_oid), text=alert, parse_mode="Markdown"
                    )
                except Exception:
                    pass
        except Exception:
            pass  # Never let the error handler itself crash the bot

    application.add_error_handler(_on_error)

    async def _post_init(app):
        # BotFather-visible commands must remain concise.
        _global_cmds = [            ("start", "Start"),
            ("pricing", "Pricing"),
            ("upgrade", "Upgrade / subscribe"),
            ("help", "Commands"),
            ("status", "Subscription status"),
            ("signals", "Latest signals"),
            ("signal", "Signal by reference"),
            ("performance", "Performance"),
            ("invite", "Invite"),
            ("support", "Support"),
        ]
        _premium_cmds = _global_cmds + [
            ("dashboard", "Dashboard"),
            ("history", "Trade history"),
            ("risk", "Risk settings"),
            ("alerts", "Alerts"),
            ("tiers", "Tier comparison"),
            ("mystats", "My P&L stats"),
            ("referral", "Referral link"),
            ("setlot", "Set lot size"),
            ("connect_broker", "Connect MT5 broker"),
            ("mt5_link", "Link MT5 account"),
            ("mt5_status", "MT5 account status"),
        ]
        _vip_cmds = _premium_cmds + [
            ("setrisk", "Set risk %"),
            ("elite", "Elite signals"),
            ("early", "Early access"),
            ("report", "Full report"),
        ]
        _owner_cmds = _vip_cmds + [
            ("unlock", "Owner: unlock tier"),
            ("dev_pause", "Owner: pause engine"),
            ("dev_resume", "Owner: resume engine"),
            ("owner_users", "Owner: user list"),
            ("owner_revenue", "Owner: revenue"),
            ("provider_status", "Owner: provider health"),
        ]
        try:
            from telegram import BotCommandScopeChat
            from signalrank_telegram.access import resolve_user_tier
            from db.pg_compat import get_all_user_ids_compat
            user_ids = get_all_user_ids_compat()
            for _uid in (user_ids or []):
                try:
                    _t = (resolve_user_tier(int(_uid)) or "free").lower()
                    if _t in ("owner", "admin"):
                        _cmds = _owner_cmds
                    elif _t == "vip":
                        _cmds = _vip_cmds
                    elif _t == "premium":
                        _cmds = _premium_cmds
                    else:
                        _cmds = _global_cmds
                    await app.bot.set_my_commands(
                        _cmds, scope=BotCommandScopeChat(chat_id=int(_uid))
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"[bot] BotCommandScopeChat update skipped: {e}")
        try:
            await app.bot.set_my_commands(_global_cmds)
        except Exception as e:
            logger.warning(f"[bot] Failed to set bot commands: {e}")
            pass

        # Start the real-time outcome tracker (polls open signals every 15s for TP/SL hits)
        try:
            from engine.realtime_outcome_tracker import outcome_tracker
            await outcome_tracker.start()
            logger.info("[bot] RealtimeOutcomeTracker started")
        except Exception as _e:
            logger.warning(f"[bot] RealtimeOutcomeTracker failed to start: {_e}")

        # ── Post-deploy terms blast ───────────────────────────────────────────
        # Set env var TERMS_BLAST_ON_DEPLOY=1 on Railway to automatically send
        # the financial disclaimer to every existing user on this deployment.
        # After the blast runs once, remove the env var to prevent re-blasting.
        if str(os.getenv("TERMS_BLAST_ON_DEPLOY", "0")).strip() in {"1", "true", "yes"}:
            import asyncio as _aio
            async def _auto_blast():
                await _aio.sleep(30)  # Wait 30s for DB connections to settle
                try:
                    from db.session import get_session as _gs_ab
                    from db.models import User as _User_ab
                    from sqlalchemy import select as _sel_ab
                    from telegram import InlineKeyboardMarkup as _IKM_ab, InlineKeyboardButton as _IKB_ab

                    async with _gs_ab() as _session_ab:
                        _result_ab = await _session_ab.execute(
                            _sel_ab(_User_ab.telegram_user_id).where(_User_ab.accepted_terms == False)  # noqa: E712
                        )
                        _pending_ab = [row[0] for row in _result_ab.fetchall()]

                    logger.info(f"[blast_terms] Auto-blast: {len(_pending_ab)} users to notify")
                    _disclaimer_ab = (
                        "⚠️ *SignalRankAI — Financial Disclaimer*\n\n"
                        "We've updated our terms. Please confirm to continue using the bot:\n\n"
                        "• All signals are for *educational purposes only*\n"
                        "• Nothing here constitutes financial advice\n"
                        "• Trading involves significant risk — losses can exceed your deposit\n"
                        "• Past performance does not guarantee future results\n"
                        "• You are solely responsible for your trading decisions\n\n"
                        "Tap *✅ I Agree* to continue."
                    )
                    _kbd_ab = _IKM_ab([[
                        _IKB_ab("✅ I Agree", callback_data="agree_terms"),
                        _IKB_ab("❌ Decline", callback_data="decline_terms"),
                    ]])
                    _sent_ab = 0
                    for _uid_ab in _pending_ab:
                        try:
                            await app.bot.send_message(
                                chat_id=int(_uid_ab),
                                text=_disclaimer_ab,
                                parse_mode="Markdown",
                                reply_markup=_kbd_ab,
                            )
                            _sent_ab += 1
                        except Exception:
                            pass
                    logger.info(f"[blast_terms] Auto-blast complete: sent={_sent_ab}/{len(_pending_ab)}")
                except Exception as _be:
                    logger.warning(f"[blast_terms] Auto-blast failed: {_be}")

            _aio.ensure_future(_auto_blast())
            logger.info("[blast_terms] Auto-blast scheduled (30s delay)")

    async def _post_stop(app):
        """Gracefully stop background tasks when the bot shuts down."""
        try:
            from engine.realtime_outcome_tracker import outcome_tracker
            await outcome_tracker.stop()
            logger.info("[bot] RealtimeOutcomeTracker stopped")
        except Exception as _e:
            logger.debug(f"[bot] RealtimeOutcomeTracker stop error: {_e}")

    application.post_init = _post_init
    application.post_stop = _post_stop

    application.add_handler(CommandHandler("start", _audit_handler("start", start_command)))
    application.add_handler(CommandHandler("status", _audit_handler("status", status_command)))
    application.add_handler(CommandHandler("help", _audit_handler("help", help_command)))
    application.add_handler(CommandHandler("about", _audit_handler("about", about_command)))
    application.add_handler(CommandHandler("faq", _audit_handler("faq", faq_command)))
    application.add_handler(CommandHandler("disclaimer", _audit_handler("disclaimer", disclaimer_command)))
    application.add_handler(CommandHandler("support", _audit_handler("support", support_command)))
    application.add_handler(CommandHandler("performance", _audit_handler("performance", performance_command)))
    application.add_handler(CommandHandler("pricing", _audit_handler("pricing", pricing_command)))
    application.add_handler(CommandHandler("upgrade", _audit_handler("upgrade", upgrade_command)))
    application.add_handler(CommandHandler("signals", _audit_handler("signals", signals_command)))
    application.add_handler(CommandHandler("signal", _audit_handler("signal", signal_command)))
    application.add_handler(CommandHandler("outcome", _audit_handler("outcome", outcome_command)))
    application.add_handler(CommandHandler("invite", _audit_handler("invite", invite_command)))

    # Premium (not advertised)
    application.add_handler(CommandHandler("stats", _audit_handler("stats", stats_command)))
    application.add_handler(CommandHandler("history", _audit_handler("history", history_command)))
    application.add_handler(CommandHandler("risk", _audit_handler("risk", risk_command)))
    application.add_handler(CommandHandler("alerts", _audit_handler("alerts", alerts_command)))
    
    # New commands for live prices and portfolio
    application.add_handler(CommandHandler("liveprice", _audit_handler("liveprice", liveprice_command)))
    application.add_handler(CommandHandler("portfolio", _audit_handler("portfolio", portfolio_command)))
    application.add_handler(CommandHandler("market", _audit_handler("market", market_command)))

    # VIP (not advertised)
    application.add_handler(CommandHandler("elite", _audit_handler("elite", elite_command)))
    application.add_handler(CommandHandler("early", _audit_handler("early", early_command)))
    application.add_handler(CommandHandler("report", _audit_handler("report", report_command)))

    application.add_handler(CommandHandler("policy", _audit_handler("policy", policy_command)))
    application.add_handler(CommandHandler("refunds", _audit_handler("refunds", policy_command)))
    application.add_handler(CommandHandler("recap", _audit_handler("recap", recap_command)))
    # Backward compatible alias

    # Hidden owner-only commands (silent for non-owners)
    application.add_handler(CommandHandler("unlock", _audit_handler("unlock", unlock)))
    application.add_handler(CommandHandler("dev_pause", _audit_handler("dev_pause", dev_pause)))
    application.add_handler(CommandHandler("dev_resume", _audit_handler("dev_resume", dev_resume)))
    application.add_handler(CommandHandler("dev_force_signal", _audit_handler("dev_force_signal", dev_force_signal)))
    application.add_handler(CommandHandler("dev_invalidate", _audit_handler("dev_invalidate", dev_invalidate)))
    application.add_handler(CommandHandler("owner_users", _audit_handler("owner_users", owner_users)))
    application.add_handler(CommandHandler("owner_revenue", _audit_handler("owner_revenue", owner_revenue)))
    application.add_handler(CommandHandler("correct_signal", _audit_handler("correct_signal", correct_signal)))
    application.add_handler(CommandHandler("provider_status", _audit_handler("provider_status", provider_status_command)))
    application.add_handler(CommandHandler("broadcast", _audit_handler("broadcast", broadcast_command)))
    from .commands import version_command
    application.add_handler(CommandHandler("version", _audit_handler("version", version_command)))

    # MT5 commands (Premium+)
    from .commands import (
        mt5_link_command, mt5_status_command,
        setlot_command, setrisk_command, tiers_command,
        mystats_command, referral_command, build_connect_broker_conversation,
        cancel_command,
    )
    application.add_handler(CommandHandler("mt5_link", _audit_handler("mt5_link", mt5_link_command)))
    application.add_handler(CommandHandler("mt5_status", _audit_handler("mt5_status", mt5_status_command)))
    application.add_handler(CommandHandler("setlot", _audit_handler("setlot", setlot_command)))
    application.add_handler(CommandHandler("setrisk", _audit_handler("setrisk", setrisk_command)))
    application.add_handler(CommandHandler("tiers", _audit_handler("tiers", tiers_command)))
    application.add_handler(CommandHandler("mystats", _audit_handler("mystats", mystats_command)))
    application.add_handler(CommandHandler("referral", _audit_handler("referral", referral_command)))
    application.add_handler(CommandHandler("cancel", _audit_handler("cancel", cancel_command)))
    application.add_handler(build_connect_broker_conversation())

    # Subscription cancellation confirmation callbacks
    from .commands import cancel_confirm_callback, cancel_nevermind_callback
    from telegram.ext import CallbackQueryHandler as _CQH_cancel
    application.add_handler(_CQH_cancel(cancel_confirm_callback, pattern="^cancel_confirm$"))
    application.add_handler(_CQH_cancel(cancel_nevermind_callback, pattern="^cancel_nevermind$"))

    # ── Terms gate callbacks (/start disclaimer) ─────────────────────────────
    from .commands import agree_terms_callback, decline_terms_callback
    from telegram.ext import CallbackQueryHandler as _CQH_terms
    application.add_handler(_CQH_terms(agree_terms_callback, pattern="^agree_terms$"))
    application.add_handler(_CQH_terms(decline_terms_callback, pattern="^decline_terms$"))

    # ── VIP waitlist join callback (/upgrade when full) ──────────────────────
    from .commands import vip_waitlist_join_callback
    from telegram.ext import CallbackQueryHandler as _CQH_vip
    application.add_handler(_CQH_vip(vip_waitlist_join_callback, pattern="^vip_waitlist_join$"))

    # ── Help/Navigation buttons ─────────────────────────────────────────────
    from .commands import button_click_handler
    from telegram.ext import CallbackQueryHandler as _CQH_nav
    application.add_handler(_CQH_nav(button_click_handler, pattern=r"^(nav_|trade_now)"))

    # ── Admin commands (OWNER/ADMIN only, silent for others) ─────────────────
    from .commands import admin_command, admin_broadcast_command, blast_terms_command, admin_dashboard
    application.add_handler(CommandHandler("admin", _audit_handler("admin", admin_command)))
    application.add_handler(CommandHandler("admin_dashboard", _audit_handler("admin_dashboard", admin_dashboard)))
    application.add_handler(CommandHandler("admin_broadcast", _audit_handler("admin_broadcast", admin_broadcast_command)))
    application.add_handler(CommandHandler("blast_terms", _audit_handler("blast_terms", blast_terms_command)))

    # ── Commands previously only on the module-level application — now added here ──
    # These were mistakenly registered on the boot-time application object, which is
    # NOT the one that serves polling/webhook requests. run_bot() creates its own
    # Application instance and ALL handlers must be added to it.
    from .commands import (
        myid_command, dashboard_command, selfcheck_command,
        notify_command, feedback_command, analyze_command,
        referral_leaderboard_command, referral_rewards_command,
        admin_top_assets_command, admin_top_strategies_command,
        admin_user_engagement_command, assets_command,
        reports_command, filter_command, apikey_command, language_command,
        account_command,
    )
    application.add_handler(CommandHandler("myid", _audit_handler("myid", myid_command)))
    application.add_handler(CommandHandler("dashboard", _audit_handler("dashboard", dashboard_command)))
    application.add_handler(CommandHandler("selfcheck", _audit_handler("selfcheck", selfcheck_command)))
    application.add_handler(CommandHandler("notify", _audit_handler("notify", notify_command)))
    application.add_handler(CommandHandler("feedback", _audit_handler("feedback", feedback_command)))
    application.add_handler(CommandHandler("analyze", _audit_handler("analyze", analyze_command)))
    application.add_handler(CommandHandler("referral_leaderboard", _audit_handler("referral_leaderboard", referral_leaderboard_command)))
    application.add_handler(CommandHandler("referral_rewards", _audit_handler("referral_rewards", referral_rewards_command)))
    application.add_handler(CommandHandler("admin_top_assets", _audit_handler("admin_top_assets", admin_top_assets_command)))
    application.add_handler(CommandHandler("admin_top_strategies", _audit_handler("admin_top_strategies", admin_top_strategies_command)))
    application.add_handler(CommandHandler("admin_user_engagement", _audit_handler("admin_user_engagement", admin_user_engagement_command)))
    application.add_handler(CommandHandler("assets", _audit_handler("assets", assets_command)))
    application.add_handler(CommandHandler("reports", _audit_handler("reports", reports_command)))
    application.add_handler(CommandHandler("filter", _audit_handler("filter", filter_command)))
    application.add_handler(CommandHandler("apikey", _audit_handler("apikey", apikey_command)))
    application.add_handler(CommandHandler("language", _audit_handler("language", language_command)))
    application.add_handler(CommandHandler("account", _audit_handler("account", account_command)))

    # 📊 Signal engagement reactions (🔥 Taking It / 👀 Watching)
    from telegram.ext import CallbackQueryHandler as _CQH
    async def _signal_reaction_callback(update, context):
        query = update.callback_query
        await query.answer()
        user_id = update.effective_user.id if update.effective_user else None
        if user_id is None:
            return
        try:
            # Callback data: signal_reaction_<signal_id>|<reaction>
            data = (query.data or "").replace("signal_reaction_", "", 1)
            signal_id_str, reaction = data.split("|", 1)
            signal_id = int(signal_id_str)
        except Exception:
            return
        try:
            from db.session import get_session as _gs
            from db.models import SignalEngagement
            from sqlalchemy import select
            async with _gs() as session:
                existing = (await session.execute(
                    select(SignalEngagement).where(
                        SignalEngagement.user_id == user_id,
                        SignalEngagement.signal_id == signal_id,
                    )
                )).scalar_one_or_none()
                if existing:
                    existing.reaction = reaction
                else:
                    session.add(SignalEngagement(
                        user_id=user_id,
                        signal_id=signal_id,
                        reaction=reaction,
                    ))
                await session.commit()
            emoji = "🔥" if reaction == "taking_it" else "👀"
            await query.answer(f"{emoji} Noted!", show_alert=False)
        except Exception as exc:
            logger.debug(f"[engagement] reaction save failed: {exc}")

    application.add_handler(_CQH(_signal_reaction_callback, pattern=r"^signal_reaction_"))

    # ⚡ Take Trade — one-click MT5 execution (PREMIUM/VIP) or upsell (FREE)
    # Callback data: mt5_trade_<signal_id>|<asset>|<direction>|<entry>|<sl>|<tp>
    from telegram.ext import CallbackQueryHandler
    async def _mt5_trade_callback(update, context):
        query = update.callback_query
        user_id = update.effective_user.id if update.effective_user else None
        if user_id is None:
            await query.answer()
            return

        # ── Tier gate: FREE users see an upsell paywall ───────────────────────
        try:
            from signalrank_telegram.access import resolve_user_tier
            from signalrank_telegram.commands import tier_rank
            _ut = (resolve_user_tier(int(user_id)) or "FREE").upper()
            if tier_rank(_ut) < tier_rank("PREMIUM"):
                await query.answer("🔒 Premium feature", show_alert=False)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=(
                        "🔒 *Premium Feature Locked!*\n\n"
                        "Auto-trading directly from Telegram is reserved for our paid members.\n\n"
                        "⭐️ *Premium Benefits:* 1-click execution, faster signals, and full asset coverage.\n\n"
                        "👑 *VIP Benefits:* Everything in Premium, plus custom risk management, "
                        "dedicated support, and exclusive market insights.\n\n"
                        "🚀 Type /upgrade right now to unlock these features and catch this trade!"
                    ),
                    parse_mode="Markdown",
                )
                return
        except Exception as _te:
            logger.debug("[mt5] tier check error: %s", _te)

        await query.answer()
        try:
            parts = (query.data or "").replace("mt5_trade_", "", 1).split("|")
            signal_id, asset, direction, entry, sl, tp = parts[0], parts[1], parts[2], float(parts[3]), float(parts[4]), float(parts[5])
        except Exception:
            await query.edit_message_text("❌ Invalid trade button data.")
            return

        # Validate that we actually have sl/tp (FREE signals have 0)
        if not sl or not tp:
            await query.edit_message_text(
                "⚠️ Trade data incomplete — stop-loss or take-profit is missing on this signal."
            )
            return

        try:
            from services.mt5_client import get_user_mt5_account_id, validate_slippage, execute_trade
            account_id = await get_user_mt5_account_id(user_id)
            if not account_id:
                await query.edit_message_text(
                    "⚠️ No MT5 account linked.\nUse /mt5_link <login> <password> <server> first."
                )
                return
            within_tol, slip, live_px = await validate_slippage(account_id, asset, entry)
            if not within_tol:
                await query.edit_message_text(
                    f"⚠️ *Slippage Warning*\n\nSignal entry: `{entry}`\nLive price: `{live_px:.5f}`\nSlippage: `{slip:.1f}` pts\n\nToo far from entry — trade not executed.",
                    parse_mode="Markdown"
                )
                return
            # Use user's configured lot size (/setlot) or default 0.01
            _exec_vol = 0.01
            try:
                from db.session import get_session as _gs_mt5
                from db.models import User as _UserMT5
                from sqlalchemy import select as _sel_mt5
                async with _gs_mt5() as _sm5:
                    _ur = (await _sm5.execute(
                        _sel_mt5(_UserMT5).where(_UserMT5.telegram_user_id == user_id)
                    )).scalar_one_or_none()
                    if _ur and getattr(_ur, 'fixed_lot_size', None):
                        _exec_vol = float(_ur.fixed_lot_size)
            except Exception:
                pass
            result = await execute_trade(
                account_id=account_id, symbol=asset, direction=direction,
                volume=_exec_vol, stop_loss=sl, take_profit=tp, signal_entry=entry
            )
            if result.get("success"):
                oid = result.get("order_id", "")
                lp = result.get("live_price") or entry
                await query.edit_message_text(
                    f"✅ *Trade Executed*\n\n🏦 {asset} {direction.upper()}\n📍 Entry: `{lp:.5f}`\nSL: `{sl}` | TP: `{tp}`\n🆔 Order: `{oid}`",
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text(f"❌ Trade failed: `{result.get('error', 'unknown')}`", parse_mode="Markdown")
        except Exception as exc:
            await query.edit_message_text(f"❌ MT5 error: `{exc}`", parse_mode="Markdown")

    application.add_handler(CallbackQueryHandler(_mt5_trade_callback, pattern=r"^mt5_trade_"))

    # 🔍 Check Outcome — query DB for signal status / outcome and show as popup
    async def _check_outcome_callback(update, context):
        query = update.callback_query
        await query.answer()  # acknowledge immediately; detailed answer sent below
        raw = (query.data or "").replace("check_outcome_", "", 1).strip()
        if not raw:
            await query.answer("No signal ID found.", show_alert=True)
            return
        try:
            from db.session import get_session as _gs_oc
            from db.models import Signal as _Sig, Outcome as _Out
            from sqlalchemy import select as _sel_oc
            async with _gs_oc() as _s:
                sig_row = (await _s.execute(
                    _sel_oc(_Sig).where(_Sig.signal_id == raw).limit(1)
                )).scalar_one_or_none()
                out_row = (await _s.execute(
                    _sel_oc(_Out).where(_Out.signal_id == raw).limit(1)
                )).scalar_one_or_none() if sig_row else None
            if sig_row is None:
                await query.answer("❌ Signal not found in database.", show_alert=True)
                return
            asset     = getattr(sig_row, 'asset', '?')
            direction = str(getattr(sig_row, 'direction', '?')).upper()
            score     = getattr(sig_row, 'score', 0)
            expired   = getattr(sig_row, 'expired', False)
            created   = getattr(sig_row, 'created_at', None)
            age_str   = ""
            if created:
                try:
                    from datetime import datetime, timezone
                    _c = created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created
                    _mins = int((datetime.now(timezone.utc) - _c).total_seconds() / 60)
                    age_str = f" | Age: {_mins}m"
                except Exception:
                    pass
            if out_row:
                outcome = str(getattr(out_row, 'status', 'unknown')).upper()
                emoji = "✅" if outcome.startswith("TP") else ("🛑" if outcome == "SL" else "ℹ️")
                msg = f"{emoji} {asset} {direction}\nOutcome: {outcome}\nScore: {score:.0f}{age_str}"
            elif expired:
                msg = f"⏰ {asset} {direction}\nStatus: Expired{age_str}"
            else:
                msg = f"🟢 {asset} {direction}\nStatus: Active (no outcome yet)\nScore: {score:.0f}{age_str}"
            await query.answer(msg, show_alert=True)
        except Exception as _oc_err:
            logger.debug("[check_outcome] error: %s", _oc_err)
            await query.answer("⚠️ Could not retrieve signal status right now.", show_alert=True)

    application.add_handler(CallbackQueryHandler(_check_outcome_callback, pattern=r"^check_outcome_"))

    def send_weekly_recap():
        user_ids = get_all_user_ids_compat()
        # Prefer Postgres-backed recap when configured
        from db.session import is_db_configured, get_session
        if is_db_configured():
            from db.pg_features import get_weekly_recap_stats

            async def _fetch(uid: int) -> dict:
                async with get_session() as session:
                    data = await get_weekly_recap_stats(session, int(uid))
                    await session.commit()
                    return data

            for user_id in user_ids:
                try:
                    stats = run_sync(_fetch(int(user_id)))
                except Exception:
                    stats = {"total": 0, "top_assets": [], "top_strategies": []}
                total = int(stats.get("total") or 0)
                if total <= 0:
                    recap_msg = (
                        "\U0001F4CA SignalRankAI Weekly Recap\n\n"
                        "No signals were sent to you this week.\n\n"
                        "Remember: No signals is sometimes better than bad signals.\n\n"
                        "Thank you for trading responsibly."
                    )
                else:
                    most_active = ", ".join(list(stats.get("top_assets") or [])[:2]) or "N/A"
                    best_strategy = ", ".join(list(stats.get("top_strategies") or [])[:1]) or "N/A"
                    recap_msg = (
                        "\U0001F4CA SignalRankAI Weekly Recap\n\n"
                        "Here’s a quick overview of your past week:\n\n"
                        f"• Total signals delivered: {total}\n"
                        f"• Markets most active: {most_active}\n"
                        f"• Best-performing strategy: {best_strategy}\n\n"
                        "Market conditions can be mixed, so signal frequency is intentionally limited.\n\n"
                        "Thank you for trading responsibly."
                    )
                try:
                    _send_message_sync(application.bot, chat_id=int(user_id), text=recap_msg)
                except Exception as e:
                    logger.warning(f"[recap] Failed to send weekly recap to user {user_id}: {e}")
                    pass
            return

    # Initialize and schedule jobs
    def send_outcome_notifications():
        # Send outcome notifications only once per outcome (notified_at tracks this).
        # Fetches unnotified outcomes and sends them to all users who received the signal.
        # Once sent and marked as notified, the outcome will never be resent.
        try:
            from db.session import is_db_configured, get_session
            if not is_db_configured():
                return
            from db.pg_features import (
                list_unnotified_outcomes,
                list_delivery_recipients_for_signal,
                mark_outcome_notified,
                get_alert_prefs,
            )
            from datetime import datetime

            async def _fetch() -> list[tuple[object, object, list[tuple[int, str, dict]]]]:
                async with get_session() as session:
                    rows = await list_unnotified_outcomes(session, limit=50)
                    out = []
                    for oc, sig in rows:
                        recipients = await list_delivery_recipients_for_signal(session, str(sig.signal_id))
                        enriched: list[tuple[int, str, dict]] = []
                        for telegram_user_id, tier_at_send in recipients:
                            try:
                                prefs = await get_alert_prefs(session, int(telegram_user_id))
                            except Exception:
                                prefs = {"tp_sl_enabled": True, "quiet_start_hour": None, "quiet_end_hour": None}
                            enriched.append((int(telegram_user_id), str(tier_at_send), dict(prefs or {})))
                        out.append((oc, sig, enriched))
                    await session.commit()
                    return out

            try:
                pending = run_sync(_fetch())
            except Exception:
                pending = []
            if not pending:
                return

            for oc, sig, recipients in pending:
                status = str(getattr(oc, 'status', '') or '').lower()
                ref = str(getattr(sig, 'signal_id', '') or '')
                # Shorten ref to 8 chars for display
                ref_short = ref[:8] if ref else 'unknown'
                r_multiple = getattr(oc, 'r_multiple', None)
                asset = str(getattr(sig, 'asset', '') or '')
                timeframe = str(getattr(sig, 'timeframe', '') or '')
                direction = str(getattr(sig, 'direction', '') or '')

                now_hour = int(datetime.now().hour)

                for telegram_user_id, tier_at_send, prefs in recipients:
                    try:
                        if isinstance(prefs, dict) and not prefs.get('tp_sl_enabled', True):
                            continue
                        qs = prefs.get('quiet_start_hour')
                        qe = prefs.get('quiet_end_hour')
                        if qs is not None and qe is not None:
                            qs = int(qs)
                            qe = int(qe)
                            if qs == qe:
                                # Quiet all day
                                continue
                            if qs < qe:
                                if qs <= now_hour < qe:
                                    continue
                            else:
                                # Wrap-around (e.g. 22 -> 6)
                                if now_hour >= qs or now_hour < qe:
                                    continue
                    except Exception as e:
                        logger.debug(f"[dispatch] Failed to check quiet hours for user: {e}")
                        pass

                    # Check if user is owner/admin for VIP formatting
                    from signalrank_telegram.access import resolve_user_tier
                    user_tier = resolve_user_tier(telegram_user_id).lower()
                    
                    # Parse which TP was hit (TP1, TP2, TP3)
                    tp_level_num = 0
                    if status in ("tp1", "partial_tp"):
                        tp_level_num = 1
                    elif status == "tp2":
                        tp_level_num = 2
                    elif status == "tp3":
                        tp_level_num = 3

                    # Fetch the delivered signal for this user and signal_id
                    delivered_signal = None
                    try:
                        from db.session import get_session
                        from db.pg_features import get_delivered_signal_by_ref
                        async def _fetch_delivered():
                            async with get_session() as session:
                                return await get_delivered_signal_by_ref(session, int(telegram_user_id), str(ref))
                        delivered_signal = run_sync(_fetch_delivered())
                    except Exception:
                        delivered_signal = None

                    signal_data = delivered_signal.__dict__ if delivered_signal else sig.__dict__

                    # Outcome notification logic by tier
                    notify = False
                    msg = None
                    # Try to get current market price for the asset
                    current_market_price = None
                    try:
                        from data.market_data import fetch_market_data_cached
                        mkt = fetch_market_data_cached(asset, timeframe)
                        if mkt and 'candles' in mkt and mkt['candles']:
                            current_market_price = mkt['candles'][-1].get('close')
                    except Exception as e:
                        logger.debug(f"[outcome] Failed to fetch current market price for {asset}: {e}")
                        pass

                    if user_tier in ("owner", "admin", "vip"):
                        if tp_level_num in (1, 2, 3):
                            notify = True
                            msg = _tier_notifier.format_tp_hit_notification(signal_data, user_tier, tp_level_num, float(getattr(oc, "percent", 0) or 0), current_market_price)
                        elif status == "sl":
                            notify = True
                            msg = _tier_notifier.format_sl_hit_notification(signal_data, user_tier, float(getattr(oc, "percent", 0) or 0))
                    elif user_tier == "premium":
                        if tp_level_num in (1, 2):
                            notify = True
                            msg = _tier_notifier.format_tp_hit_notification(signal_data, user_tier, tp_level_num, float(getattr(oc, "percent", 0) or 0), current_market_price)
                        elif status == "sl":
                            notify = True
                            msg = _tier_notifier.format_sl_hit_notification(signal_data, user_tier, float(getattr(oc, "percent", 0) or 0))
                    elif str(tier_at_send).lower() == "free":
                        if tp_level_num > 0 or status == "tp":
                            notify = True
                            msg = _tier_notifier.format_tp_hit_notification(signal_data, "free", tp_level_num or 1, float(getattr(oc, "percent", 0) or 0), current_market_price)
                        elif status == "sl":
                            notify = True
                            msg = _tier_notifier.format_sl_hit_notification(signal_data, "free", float(getattr(oc, "percent", 0) or 0))

                    if notify and msg:
                        try:
                            _send_message_sync(application.bot, chat_id=int(telegram_user_id), text=msg)
                        except Exception as e:
                            logger.warning(f"[outcome] Failed to send outcome notification to user {telegram_user_id}: {e}")
                            pass

                # Mark as notified so this outcome is never sent again.
                # Once marked, list_unnotified_outcomes() won't return it.
                try:
                    async def _mark(oid: int) -> None:
                        async with get_session() as session:
                            await mark_outcome_notified(session, int(oid))
                            await session.commit()

                    run_sync(_mark(int(getattr(oc, 'id'))))
                except Exception as e:
                    logger.debug(f"[outcome] Failed to mark outcome as handled: {e}")
                    pass
        except Exception as e:
            logger.warning(f"[outcome] Failed to process outcomes: {e}")
            return


    def compute_outcomes_best_effort():
        """Best-effort outcome writer.

        Scans recently delivered signals that have no outcome yet, fetches candles,
        and records TP/SL if hit. This enables follow-up messages end-to-end.
        """
        try:
            from db.session import _get_global_engine, get_engine_for_event_loop, get_session
            engine = _get_global_engine()  # ensure engine is initialised in this thread
            if engine is None:
                logger.warning("[outcome] DB engine not initialised — skipping job")
                return
            from db.pg_features import list_signals_missing_outcomes, upsert_outcome
            from datetime import datetime
            import json
            from data.fetcher import get_candles

            async def _fetch_candidates():
                async with get_session() as session:
                    sigs = await list_signals_missing_outcomes(session, max_age_days=3, limit=30)
                    await session.commit()
                    return sigs

            try:
                candidates = run_sync(_fetch_candidates())
            except Exception:
                candidates = []
            if not candidates:
                return

            now = datetime.utcnow()

            def _parse_tp(tp_raw):
                if tp_raw is None:
                    return None
                if isinstance(tp_raw, (int, float)):
                    return float(tp_raw)
                s = str(tp_raw).strip()
                if not s:
                    return None
                try:
                    data = json.loads(s)
                    if isinstance(data, list) and data:
                        return float(data[0])
                    if isinstance(data, (int, float)):
                        return float(data)
                except Exception as e:
                    logger.debug(f"[outcome] Failed to parse price from data: {e}")
                    pass
                try:
                    return float(s)
                except Exception:
                    return None

            def _ms(dt):
                try:
                    return int(dt.timestamp() * 1000)
                except Exception:
                    return 0


            for sig in candidates:
                try:
                    asset = str(getattr(sig, "asset", "") or "").upper().strip()
                    tf = str(getattr(sig, "timeframe", "") or "").lower().strip()
                    direction = str(getattr(sig, "direction", "") or "").lower().strip()
                    entry = float(getattr(sig, "entry"))
                    sl = float(getattr(sig, "stop_loss"))
                    tp = _parse_tp(getattr(sig, "take_profit", None))
                    created_at = getattr(sig, "created_at", None)
                    if not asset or not tf or direction not in {"long", "short"}:
                        continue
                    if tp is None or created_at is None:
                        continue

                    print(f"[DEBUG][outcome] Evaluating signal {sig.signal_id} {asset} {tf} {direction}", flush=True)

                    candles = get_candles(asset, tf)
                    if not candles:
                        tf_order = ["1m", "5m", "15m", "1h", "4h", "1d"]
                        alt_tfs = [t for t in tf_order if t != tf]
                        for alt in alt_tfs:
                            try:
                                candles = get_candles(asset, alt)
                                if candles:
                                    break
                            except Exception:
                                candles = []
                                continue
                        if not candles:
                            print(f"[DEBUG][outcome] No candles found for {asset} {tf}", flush=True)
                            continue

                    created_ms = _ms(created_at)
                    filtered = []
                    for c in candles:
                        try:
                            ts = c.get("timestamp")
                            if isinstance(ts, (int, float)):
                                if int(ts) >= created_ms:
                                    filtered.append(c)
                            else:
                                filtered.append(c)
                        except Exception:
                            continue
                    if not filtered:
                        print(f"[DEBUG][outcome] No filtered candles for {asset} {tf}", flush=True)
                        continue

                    # Only progress outcome status (TP1->TP2->TP3->SL), never backwards or duplicate
                    from db.session import get_session
                    from db.pg_features import get_outcome_for_signal
                    prev_status = None
                    try:
                        async def _get_prev():
                            async with get_session() as session:
                                return await get_outcome_for_signal(session, str(sig.signal_id))
                        prev = run_sync(_get_prev())
                        if prev:
                            prev_status = str(getattr(prev, 'status', '') or '').lower()
                    except Exception:
                        prev_status = None


                    status = None
                    entry_filled = False
                    entry_filled_at = None
                    tp_hits = 0
                    missed = False
                    invalidated = False
                    for c in filtered:
                        try:
                            hi = float(c.get("high"))
                            lo = float(c.get("low"))
                        except Exception:
                            continue
                        ts_val = c.get("timestamp")
                        # Entry must be filled before tracking SL/TP
                        if not entry_filled:
                            # If SL is hit before entry, mark as invalidated
                            if (direction == "long" and lo <= sl) or (direction == "short" and hi >= sl):
                                invalidated = True
                                break
                            # If price never touches entry, keep waiting
                            if lo <= entry <= hi:
                                entry_filled = True
                                entry_filled_at = ts_val
                                # Notify entry filled
                                print(f"[DEBUG][outcome] Entry filled for {sig.signal_id} at {entry_filled_at}", flush=True)
                            continue
                        # After entry is filled, track SL/TP
                        if direction == "long":
                            hit_sl = lo <= sl
                            hit_tp = hi >= tp
                        else:
                            hit_sl = hi >= sl
                            hit_tp = lo <= tp
                        if hit_sl and hit_tp:
                            status = "sl"
                            break
                        if hit_sl:
                            status = "sl"
                            break
                        if hit_tp:
                            tp_hits += 1
                            status = f"tp{tp_hits}" if tp_hits <= 3 else "tp"
                            if tp_hits >= 3:
                                break

                    # If entry never filled and candles are exhausted, mark as missed
                    if not entry_filled and not invalidated:
                        missed = True

                    if invalidated:
                        status = "invalidated"
                        print(f"[DEBUG][outcome] Signal {sig.signal_id} invalidated: SL hit before entry", flush=True)
                    elif missed:
                        status = "missed"
                        print(f"[DEBUG][outcome] Signal {sig.signal_id} missed: entry never touched", flush=True)
                    elif status is None:
                        continue

                    # Only progress outcome status, never duplicate or regress
                    status_order = ["tp1", "tp2", "tp3", "tp", "sl"]
                    if prev_status:
                        try:
                            prev_idx = status_order.index(prev_status) if prev_status in status_order else -1
                            curr_idx = status_order.index(status) if status in status_order else -1
                            if curr_idx <= prev_idx:
                                print(f"[DEBUG][outcome] Skipping duplicate/regressive outcome for {sig.signal_id}: {status} (prev: {prev_status})", flush=True)
                                continue
                        except Exception as e:
                            logger.debug(f"[outcome] Failed to check outcome progression: {e}")
                            pass

                    risk = abs(entry - sl)
                    reward = abs(tp - entry)
                    r_mult = None
                    pct = None
                    try:
                        if risk > 0:
                            if status.startswith("tp"):
                                r_mult = reward / risk
                            else:
                                r_mult = -1.0
                        if status.startswith("tp"):
                            if direction == "long":
                                pct = ((tp - entry) / entry) * 100.0
                            else:
                                pct = ((entry - tp) / entry) * 100.0
                        else:
                            if direction == "long":
                                pct = -((entry - sl) / entry) * 100.0
                            else:
                                pct = -((sl - entry) / entry) * 100.0
                    except Exception:
                        r_mult = None
                        pct = None

                    meta = {
                        "source": "candle_scan",
                        "evaluated_at": now.isoformat(),
                        "tp": tp,
                        "sl": sl,
                    }
                    entry_filled_dt = None
                    try:
                        if isinstance(entry_filled_at, (int, float)):
                            entry_filled_dt = datetime.utcfromtimestamp(float(entry_filled_at) / 1000.0)
                        elif entry_filled_at:
                            entry_filled_dt = datetime.fromisoformat(str(entry_filled_at).replace("Z", ""))
                    except Exception:
                        entry_filled_dt = None
                    if entry_filled_at is not None:
                        meta["entry_filled_at"] = entry_filled_at

                    print(f"[DEBUG][outcome] Writing outcome for {sig.signal_id}: {status}", flush=True)
                    async def _write():
                        async with get_session() as session:
                            await upsert_outcome(
                                session,
                                str(sig.signal_id),
                                status,
                                meta=meta,
                                r_multiple=r_mult,
                                percent=pct,
                                opened_at=entry_filled_dt or created_at,
                                closed_at=now,
                            )
                            await session.commit()
                    try:
                        run_sync(_write())
                    except Exception as e:
                        print(f"[DEBUG][outcome] Exception writing outcome: {e}", flush=True)

                    # Fire outcome notifications immediately
                    try:
                        print(f"[DEBUG][outcome] Sending outcome notifications for {sig.signal_id}", flush=True)
                        send_outcome_notifications()
                    except Exception as e:
                        print(f"[DEBUG][outcome] Exception sending notifications: {e}", flush=True)
                except Exception as e:
                    print(f"[DEBUG][outcome] Exception in outcome computation: {e}", flush=True)
                    continue

        except Exception:
            logger.exception("[outcome] compute_outcomes_best_effort failed")

    def _in_quiet_hours(current_hour, start_hour, end_hour):
        """Check if current_hour is within quiet hours (respecting wrap-around)."""
        if start_hour == end_hour:
            return True  # Quiet all day
        if start_hour < end_hour:
            return start_hour <= current_hour < end_hour
        else:
            # Wrap-around (e.g., 22 to 6 means quiet 22-23 and 0-5)
            return current_hour >= start_hour or current_hour < end_hour

    def send_free_delayed_summaries():
        # Respect kill-switch
        try:
            if state.get_killswitch_sync().enabled:
                return
        except Exception as e:
            logger.debug(f"[free_summary] Failed to check killswitch: {e}")
            pass

        logger.info("🔄 send_free_delayed_summaries job triggered")

        # Prefer Postgres-backed delayed queue
        try:
            from db.session import get_engine_for_event_loop, get_session
            engine = get_engine_for_event_loop()
            if engine is not None:
                from db.pg_features import (
                    expire_old_free_signal_summaries as expire_old_free_signal_summaries_pg,
                    get_alert_prefs as get_alert_prefs_pg,
                    get_due_free_signal_summaries as get_due_free_signal_summaries_pg,
                    mark_free_signal_summaries_sent as mark_free_signal_summaries_sent_pg,
                    record_signal_delivery,
                )
                from datetime import datetime

                async def _fetch_due() -> dict[int, dict]:
                    async with get_session() as session:
                        try:
                            await expire_old_free_signal_summaries_pg(session, max_age_hours=24)
                        except Exception as e:
                            logger.debug(f"[free_summary] Failed to expire old free signal summaries: {e}")
                            pass
                        due = await get_due_free_signal_summaries_pg(session)
                        out: dict[int, dict] = {}
                        for uid, items in due.items():
                            prefs = await get_alert_prefs_pg(session, int(uid))
                            out[int(uid)] = {"items": items, "prefs": prefs}
                        await session.commit()
                        return out

                try:
                    due = run_sync(_fetch_due())
                    logger.info(f"📬 Free queue check: {len(due)} user(s) with due signals")
                except Exception as e:
                    logger.error(f"Error fetching due signals: {e}", exc_info=True)
                    due = {}

                if not due:
                    logger.info("✅ No free signals due for delivery")
                    return

                now_hour = datetime.now().hour
                per_user_limit = int(getattr(config, 'FREE_DAILY_LIMIT', 3))

                actions: list[tuple[int, list[int], list[str], str]] = []

                for uid, data in due.items():
                    items = list(data.get("items") or [])
                    prefs = dict(data.get("prefs") or {})

                    logger.info(f"📨 User {uid}: {len(items)} queued signal(s)")

                    if not prefs.get("tp_sl_enabled", True):
                        logger.info(f"⏸️ User {uid} has alerts disabled, marking as suppressed")
                        actions.append(
                            (int(uid), [it["id"] for it in items], [it["signal_id"] for it in items], 'suppressed')
                        )
                        continue

                    qs = prefs.get("quiet_start_hour")
                    qe = prefs.get("quiet_end_hour")
                    if qs is not None and qe is not None:
                        try:
                            if _in_quiet_hours(now_hour, int(qs), int(qe)):
                                logger.info(f"🔇 User {uid} in quiet hours ({qs}-{qe}), skipping")
                                continue
                        except Exception as e:
                            logger.debug(f"[free_summary] Failed to check quiet hours for user {uid}: {e}")
                            pass

                    items_to_send = items[:per_user_limit]
                    items_to_skip = items[per_user_limit:]

                    status = 'sent'
                    if items_to_send:
                        msg = _format_free_delayed_digest(items_to_send)
                        try:
                            _send_message_sync(application.bot, chat_id=int(uid), text=msg)
                            logger.info(f"✅ Delivered {len(items_to_send)} signal(s) to user {uid}")
                        except Exception as e:
                            logger.error(f"❌ Failed to send to user {uid}: {e}")
                            status = 'failed'

                        actions.append(
                            (
                                int(uid),
                                [it["id"] for it in items_to_send],
                                [it["signal_id"] for it in items_to_send],
                                status,
                            )
                        )

                    # Clear out any extra due items so they don't remain queued forever.
                    if items_to_skip:
                        logger.info(f"⏱️ User {uid}: {len(items_to_skip)} signal(s) overflow, marking as expired")
                        actions.append(
                            (
                                int(uid),
                                [it["id"] for it in items_to_skip],
                                [it["signal_id"] for it in items_to_skip],
                                'expired',
                            )
                        )

                if not actions:
                    logger.info("✅ No actions to apply")
                    return

                async def _apply_actions() -> None:
                    async with get_session() as session:
                        for uid, ids, signal_ids, status in actions:
                            await mark_free_signal_summaries_sent_pg(session, ids, status=status)
                            if status == 'sent':
                                for sid in signal_ids:
                                    await record_signal_delivery(
                                        session,
                                        telegram_user_id=int(uid),
                                        signal_id=str(sid),
                                        tier_at_send='free',
                                    )
                        await session.commit()

                try:
                    run_sync(_apply_actions())
                    logger.info(f"💾 Applied {len(actions)} queue action(s)")
                except Exception as e:
                    logger.error(f"Error applying actions: {e}", exc_info=True)
                return
        except Exception as e:
            logger.debug(f"[free_summary] Failed to send free summaries: {e}")
            pass

        # Postgres-only: no SQLite fallback
        return

    def auto_retrain_ml_model_job():
        """Automatically retrain ML model when enough outcome data exists."""
        try:
            if state.get_killswitch_sync().enabled:
                return
        except Exception as e:
            logger.debug(f"[ml_retrain] Failed to check killswitch: {e}")
            pass

        logger.info("🤖 ML auto-retrain job triggered")

        try:
            from ml.train_model import main as train_main

            async def _retrain():
                try:
                    success = await train_main()
                    if success:
                        logger.info("✅ ML model retrained successfully")
                    else:
                        logger.warning("⚠️ ML retrain skipped (insufficient data)")
                except Exception as e:
                    logger.error(f"❌ ML retrain failed: {e}", exc_info=True)

            run_sync(_retrain())
        except Exception as e:
            logger.error(f"Error in ML retrain job: {e}", exc_info=True)

    def vip_scarcity_broadcast_job():
        """Broadcast a VIP scarcity nudge to PREMIUM users when seats are available."""
        try:
            if state.get_killswitch_sync().enabled:
                return
        except Exception:
            pass
        try:
            from db.session import get_session
            from db.repository import count_active_vip_users
            from config import OWNER_IDS

            async def _check():
                async with get_session() as session:
                    exclude = set(OWNER_IDS or [])
                    used = await count_active_vip_users(session, exclude_telegram_user_ids=exclude)
                    return used

            used = run_sync(_check())
            vip_limit = int(os.getenv("VIP_SEAT_LIMIT", "15"))
            available = max(0, vip_limit - used)
            if available <= 0:
                return

            from db.pg_compat import get_all_user_ids_compat
            from signalrank_telegram.access import resolve_user_tier
            msg = (
                f"🔥 *VIP Seats Available — {available} of {vip_limit} open!*\n\n"
                "VIP members get:\n"
                "• Real-time signals (30/day)\n"
                "• TP1/TP2/TP3 notifications\n"
                "• One-click MT5 execution\n"
                "• Trailing SL to break-even on TP1\n\n"
                "Seats fill fast. Use /upgrade to claim yours."
            )
            for _uid in (get_all_user_ids_compat() or []):
                try:
                    _t = (resolve_user_tier(int(_uid)) or "free").lower()
                    if _t == "premium":
                        _send_message_sync(application.bot, chat_id=int(_uid), text=msg)
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"[vip_scarcity] job failed: {e}")

    # ── FOMO engine ─────────────────────────────────────────────────────────
    def fomo_engine_job():
        """Broadcast today's VIP highlights to FREE users at 5PM UTC."""
        try:
            if state.get_killswitch_sync().enabled:
                return
        except Exception:
            pass
        try:
            from db.session import get_session as _gs
            from db.models import MT5Execution
            from sqlalchemy import select, func
            from datetime import datetime, timedelta

            async def _fetch_vip_pnl():
                today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                async with _gs() as session:
                    rows = await session.execute(
                        select(
                            func.count().label("trades"),
                            func.sum(MT5Execution.realized_pnl).label("total_pnl"),
                        ).where(
                            MT5Execution.executed_at >= today_start,
                            MT5Execution.tier_at_execution == "VIP",
                            MT5Execution.realized_pnl.isnot(None),
                        )
                    )
                    row = rows.one_or_none()
                    return row

            stats = run_sync(_fetch_vip_pnl())
            trades = int(getattr(stats, "trades", 0) or 0)
            total_pnl = float(getattr(stats, "total_pnl", 0.0) or 0.0)
            if trades == 0:
                return  # Nothing to FOMO about today

            sign = "+" if total_pnl >= 0 else ""
            msg = (
                f"⚡ <b>Today's VIP Execution Recap</b>\n\n"
                f"📊 VIP members executed <b>{trades}</b> trade(s) today\n"
                f"💰 Combined P&amp;L: <b>{sign}${total_pnl:.2f}</b>\n\n"
                f"🎯 Upgrade to VIP for unlimited automated executions.\n"
                f"👉 /tiers to compare plans • /upgrade to subscribe"
            )
            from db.pg_compat import get_all_user_ids_compat
            from signalrank_telegram.access import resolve_user_tier
            for _uid in (get_all_user_ids_compat() or []):
                try:
                    _t = (resolve_user_tier(int(_uid)) or "free").lower()
                    if _t == "free":
                        _send_message_sync(application.bot, chat_id=int(_uid), text=msg)
                except Exception:
                    pass
        except Exception as exc:
            logger.debug(f"[fomo] job failed: {exc}")

    # ── Friday leaderboard ──────────────────────────────────────────────────
    def friday_leaderboard_job():
        """Every Friday at 5PM UTC — broadcast the week's top signals and traders."""
        try:
            if state.get_killswitch_sync().enabled:
                return
        except Exception:
            pass
        try:
            from db.session import get_session as _gs
            from db.models import MT5Execution
            from sqlalchemy import select, func
            from datetime import datetime, timedelta

            week_start = datetime.utcnow() - timedelta(days=7)

            async def _fetch_leaderboard():
                async with _gs() as session:
                    rows = await session.execute(
                        select(
                            MT5Execution.user_id,
                            func.sum(MT5Execution.realized_pnl).label("pnl"),
                            func.count().label("trades"),
                        ).where(
                            MT5Execution.executed_at >= week_start,
                            MT5Execution.realized_pnl.isnot(None),
                            MT5Execution.tier_at_execution == "VIP",
                        ).group_by(
                            MT5Execution.user_id
                        ).order_by(
                            func.sum(MT5Execution.realized_pnl).desc()
                        ).limit(3)
                    )
                    return rows.all()

            top_traders = run_sync(_fetch_leaderboard())
            if not top_traders:
                return

            lines = ["🏆 <b>This Week's VIP Leaderboard</b>\n"]
            medals = ["🥇", "🥈", "🥉"]
            for i, row in enumerate(top_traders):
                uid = row.user_id
                pnl = float(row.pnl or 0)
                trades = int(row.trades or 0)
                sign = "+" if pnl >= 0 else ""
                lines.append(
                    f"{medals[i]} <b>Trader #{uid}</b>  "
                    f"{sign}${pnl:.2f}  ({trades} trades)"
                )

            lines.append(
                "\n💡 Join VIP for automated execution and leaderboard inclusion.\n"
                "👉 /upgrade"
            )
            msg = "\n".join(lines)
            from db.pg_compat import get_all_user_ids_compat
            for _uid in (get_all_user_ids_compat() or []):
                try:
                    _send_message_sync(application.bot, chat_id=int(_uid), text=msg)
                except Exception:
                    pass
        except Exception as exc:
            logger.debug(f"[leaderboard] job failed: {exc}")

    # ── Signal auto-expiry ──────────────────────────────────────────────────
    def expire_old_signals_job():
        """Mark signals where expires_at < now as expired=True."""
        try:
            from db.session import get_session as _gs
            from db.models import Signal
            from sqlalchemy import select, update
            from datetime import datetime

            async def _expire():
                now = datetime.utcnow()
                async with _gs() as session:
                    await session.execute(
                        update(Signal)
                        .where(
                            Signal.expires_at <= now,
                            Signal.expired.is_(False),
                        )
                        .values(expired=True)
                    )
                    await session.commit()

            run_sync(_expire())
        except Exception as exc:
            logger.debug(f"[expiry] expire_old_signals_job failed: {exc}")

    # ── ML market analysis scan ────────────────────────────────────────────
    def ml_market_analysis_job():
        """Every 15 min: run the ML filter over recent unscored signals.

        This makes ML activity visible in APScheduler logs.  Live market
        features are taken from the signal rows already stored by the engine
        loop (which populates indicators, ATR, regime, etc. before persisting).
        """
        try:
            if state.get_killswitch_sync().enabled:
                return
        except Exception:
            pass

        logger.info("🤖 [ML] Market analysis scan starting …")

        try:
            from ml.inference import MLFilter
            from ml.features import extract_features
        except ImportError:
            logger.warning("[ML] ml.inference not available — analysis scan skipped")
            return

        try:
            ml_filter = MLFilter()
            if not getattr(ml_filter, "active", False):
                logger.info("[ML] Model not loaded — scan skipped (train first)")
                return

            threshold = float(os.getenv("ML_PROB_THRESHOLD", "0.65"))

            async def _scan():
                from db.session import get_session
                from db.models import Signal
                from sqlalchemy import select
                from datetime import datetime, timedelta

                cutoff = datetime.utcnow() - timedelta(hours=4)
                async with get_session() as session:
                    rows = await session.execute(
                        select(Signal).where(
                            Signal.created_at >= cutoff,
                            Signal.ml_probability.is_(None),
                            Signal.expired.is_(False),
                        ).limit(50)
                    )
                    signals = rows.scalars().all()

                approved = rejected = errors = 0
                for sig_row in signals:
                    try:
                        sig_dict = {
                            col.name: getattr(sig_row, col.name)
                            for col in sig_row.__table__.columns
                        }
                        features = extract_features(sig_dict, {})
                        ok, prob = ml_filter.ml_filter(features, threshold=threshold)
                        if ok:
                            approved += 1
                        else:
                            rejected += 1
                    except Exception as fe:
                        errors += 1
                        logger.debug("[ML] feature error: %s", fe)
                return len(signals), approved, rejected, errors

            total, approved, rejected, errors = run_sync(_scan())
            logger.info(
                "🤖 [ML] Scan done — signals=%d  approved=%d  rejected=%d  "
                "errors=%d  threshold=%.2f",
                total, approved, rejected, errors, threshold,
            )
        except Exception as exc:
            logger.error("[ML] ml_market_analysis_job failed: %s", exc, exc_info=True)

    # ── APScheduler setup ───────────────────────────────────────────────────
    # APScheduler 3.x's SQLAlchemyJobStore uses *synchronous* SQLAlchemy.
    # Passing an asyncpg:// URL causes the driver to be rejected and the store
    # to silently fall back to  postgresql://postgres@localhost  — which Railway
    # always rejects with "password authentication failed for user postgres".
    # Strip the async driver prefix before creating the job store.
    _sched_raw = (
        os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL") or ""
    ).strip()
    _sched_sync_url: str | None = None
    if _sched_raw:
        _sched_sync_url = _sched_raw
        for _pfx, _rep in (
            ("postgresql+asyncpg://", "postgresql://"),
            ("postgres://", "postgresql://"),
        ):
            if _sched_sync_url.startswith(_pfx):
                _sched_sync_url = _sched_sync_url.replace(_pfx, _rep, 1)
                break

    # Register a 'persistent' jobstore for module-level (picklable) callables.
    # Closure functions defined inside run_bot() cannot be pickled for
    # SQLAlchemy — they are added to the implicit default MemoryJobStore.
    _jobstores: dict = {}
    if _sched_sync_url:
        try:
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore as _SAJobStore
            _jobstores["persistent"] = _SAJobStore(url=_sched_sync_url)
            logger.info(
                "[sched] SQLAlchemyJobStore ready → %s",
                _sched_sync_url.split("@")[-1],
            )
        except Exception as _sa_err:
            logger.warning(
                "[sched] SQLAlchemyJobStore unavailable (%s) — using MemoryJobStore",
                _sa_err,
            )

    # _sa: alias for the store to use for picklable module-level jobs.
    _sa = "persistent" if "persistent" in _jobstores else "default"

    scheduler = BackgroundScheduler(jobstores=_jobstores or {}, timezone="UTC")

    # ── Closure jobs (defined inside run_bot — cannot be pickled for SQLAlchemy)
    # These always land in the default MemoryJobStore.
    scheduler.add_job(
        ml_market_analysis_job,
        'interval',
        minutes=15,
        id='ml_market_analysis',
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        send_free_delayed_summaries,
        'interval',
        minutes=10,
        id='send_free_delayed_summaries',
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        compute_outcomes_best_effort,
        'interval',
        minutes=3,
        id='compute_outcomes_best_effort',
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        send_outcome_notifications,
        'interval',
        minutes=2,
        id='send_outcome_notifications',
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        vip_scarcity_broadcast_job,
        'interval',
        hours=6,
        id='vip_scarcity_broadcast_job',
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        fomo_engine_job,
        'cron',
        hour=17,
        minute=0,
        id='fomo_engine_job',
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        friday_leaderboard_job,
        'cron',
        day_of_week='fri',
        hour=17,
        minute=0,
        id='friday_leaderboard_job',
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        expire_old_signals_job,
        'interval',
        minutes=30,
        id='expire_old_signals_job',
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        send_weekly_recap,
        'cron',
        day_of_week='sun',
        hour=18,
        minute=0,
        id='send_weekly_recap',
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        auto_retrain_ml_model_job,
        'cron',
        day_of_week='sun',
        hour=2,
        minute=0,
        id='auto_retrain_ml_model_job',
        replace_existing=True,
        max_instances=1,
    )

    # ── Module-level jobs (picklable) → SQLAlchemy persistent store when available
    scheduler.add_job(
        resend_unsent_signals_job,
        'interval',
        minutes=1,
        id='resend_unsent_signals_job',
        replace_existing=True,
        max_instances=1,
        jobstore=_sa,
    )
    scheduler.add_job(
        distribute_random_signals_to_free_users_job,
        'interval',
        minutes=15,
        id='distribute_random_signals_to_free_users_job',
        replace_existing=True,
        max_instances=1,
        jobstore=_sa,
    )
    scheduler.add_job(
        downgrade_expired_subscriptions_job,
        'cron',
        hour=0,
        minute=0,
        id='downgrade_expired_subscriptions_job',
        replace_existing=True,
        max_instances=1,
        jobstore=_sa,
    )
    scheduler.add_job(
        auto_delete_old_signals_job,
        'cron',
        day_of_week='sun',
        hour=1,
        minute=0,
        id='auto_delete_old_signals_job',
        replace_existing=True,
        max_instances=1,
        jobstore=_sa,
    )

    scheduler.start()

    # ── Webhook mode ──────────────────────────────────────────────────────────
    # When TELEGRAM_USE_WEBHOOK is set, railway_main.py owns the event loop and
    # calls application.process_update() via the POST /telegram/webhook FastAPI
    # route.  Store the configured application and scheduler so they survive
    # this function's scope, then return without starting long-polling.
    if os.getenv("TELEGRAM_USE_WEBHOOK"):
        global _webhook_application, _bot_scheduler
        _webhook_application = application
        _bot_scheduler = scheduler  # prevent GC; daemon threads keep running
        print("[bot] webhook mode: application ready, scheduler running, not polling", flush=True)
        return

    # ── Polling mode ──────────────────────────────────────────────────────────
    # Run polling with an explicit event loop (Python 3.12 safe)
    try:
        import asyncio as _asyncio
        loop = _asyncio.new_event_loop()
        _asyncio.set_event_loop(loop)
        print("[boot] telegram bot polling starting", flush=True)
        application.run_polling()
    except Exception:
        # Last resort: retry without custom loop
        print("[boot] telegram bot polling starting", flush=True)
        application.run_polling()


if __name__ == "__main__":
    run_bot()
