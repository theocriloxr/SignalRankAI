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
    risk_command,
    alerts_command,
    elite_command,
    early_command,
    report_command,
    buy_extra_signals,
)

from core.redis_state import state
from .owner_commands import (
    unlock,
    dev_pause,
    dev_resume,
    dev_force_signal,
    dev_invalidate,
    owner_users,
    owner_revenue,
)

TIER_LIMITS = {
    'free': 2,
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
    except Exception:
        pass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


async def _send_message_async(bot: Bot, chat_id: int, text: str) -> None:
    await bot.send_message(chat_id=chat_id, text=text)


def _send_message_sync(bot: Bot, chat_id: int, text: str) -> None:
    """Send a Telegram message from sync code.

    python-telegram-bot v20+ uses async methods. The engine and APScheduler jobs
    run in sync contexts, so we bridge with asyncio.
    """

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_send_message_async(bot, int(chat_id), str(text)))
        return
    # If we're already in an event loop, schedule it.
    try:
        loop.create_task(_send_message_async(bot, int(chat_id), str(text)))
    except Exception:
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
            from db.session import ENGINE, get_session
            if ENGINE is not None and getattr(update, "effective_user", None) is not None:
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
        return await handler(update, context)

    return _inner


def _require_telegram_token() -> str:
    token = os.getenv('TELEGRAM_TOKEN')
    if token:
        return token

    # Local dev convenience: optionally load from a `.env` file.
    # Railway/production should rely on injected environment variables.
    allow_dotenv = (os.getenv("ALLOW_DOTENV") or "").strip().lower() in {"1", "true", "yes", "y", "on"}
    if allow_dotenv:
        env_path = os.path.join(os.getcwd(), '.env')
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for raw_line in f:
                        line = raw_line.strip()
                        if not line or line.startswith('#') or '=' not in line:
                            continue
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and key not in os.environ:
                            os.environ[key] = value
            except Exception:
                pass

    token = os.getenv('TELEGRAM_TOKEN')
    if token:
        return token
    raise RuntimeError(
        "TELEGRAM_TOKEN is not set. "
        "Set it in your shell (PowerShell: $env:TELEGRAM_TOKEN='...') or as a Railway Variable."
    )

# Outcome tracking notifications
def notify_trade_outcome(user_id, strategy, result, ret):
    bot = Bot(token=_require_telegram_token())
    # result: 'tp', 'partial_tp', 'sl', 'invalid', 'summary', 'free_limited'
    # signal dict should include asset, timeframe, direction, entry, exit, stop, tp1, duration, confidence, etc.
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
    bot.send_message(chat_id=user_id, text=msg)

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
    bot.send_message(chat_id=user_id, text=msg)

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

def dispatch_signals(strategy_signals, user_id, regime=None):
    """Dispatch signals to user based on their tier.
    
    Tier-based Limits:
    - OWNER: 9999 signals/day (all signals, real-time)
    - ADMIN: 9999 signals/day (all signals, real-time)  
    - VIP: 30 signals/day (real-time)
    - PREMIUM: 10 signals/day (real-time)
    - FREE: 2 signals/day (delayed queue)
    
    All signals must:
    - Pass quality gates (confidence, RR, volatility)
    - Score >= MIN_SCORE_THRESHOLD (55)
    - Pass consensus check (CONSENSUS_MIN_SCORE)
    - Pass risk validation (RR >= 1.5, vol <= 0.20)
    - Pass ML filter if enabled
    """
    tier_raw = resolve_user_tier(user_id)
    tier = (tier_raw or 'FREE').strip().lower()

    # Free users with paid extra-signal quota receive VIP-style real-time delivery
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
    except Exception:
        pass

    # Support passing ranked buckets (vip/premium/free)
    signals_list = []
    if isinstance(strategy_signals, dict):
        vip_list = list(strategy_signals.get('vip', []) or [])
        prem_list = list(strategy_signals.get('premium', []) or [])
        
        # Tier-based signal selection
        if tier in ('owner', 'admin'):
            # Owner/Admin see all signals (vip + premium)
            signals_list = vip_list + prem_list
        elif tier in ('vip',):
            # VIP sees premium and above
            signals_list = vip_list + prem_list
        elif tier in ('premium',):
            # Premium sees full signals (premium + vip)
            signals_list = vip_list + prem_list
        else:  # FREE
            # Free: delayed summaries from top approved signals
            signals_list = (vip_list + prem_list)

        # Paid extra signals: Premium-style real-time delivery (vip+premium), capped by purchased count
        if tier == 'free' and extra_left > 0:
            signals_list = (vip_list + prem_list)
    else:
        signals_list = list(strategy_signals or [])

    if not signals_list:
        return

    # Postgres-backed delivery dedup + history (preferred)
    try:
        from db.session import ENGINE, get_session

        if ENGINE is not None:
            effective_tier = tier
            display_tier = tier
            if tier == 'free' and extra_left > 0:
                effective_tier = 'premium'
                display_tier = 'premium'
            if tier == 'owner':
                # Owner receives VIP formatting while keeping owner volume limits.
                display_tier = 'vip'
                effective_tier = 'vip'
            if tier == 'admin':
                # Admin receives the same set as owner, but store tier distinctly.
                display_tier = 'vip'
                effective_tier = 'admin'

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
                            ok = await record_signal_delivery(
                                session,
                                telegram_user_id=int(user_id),
                                signal_id=str(s.signal_id),
                                tier_at_send=str(effective_tier),
                            )
                            if not ok:
                                continue
                            payload = dict(signal)
                            payload.setdefault("signal_id", str(s.signal_id))
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
                    reserved = asyncio.run(_reserve())
                    reserve_failed = False
                except Exception as e:
                    reserved = []
                    reserve_failed = True
                    _log_once(
                        "dispatch_reserve_failed",
                        f"[bot] dispatch reserve failed (falling back to direct send): {type(e).__name__}: {e}",
                    )

                if _env_bool("BOT_DELIVERY_DEBUG", False):
                    try:
                        print(
                            "[bot] dispatch "
                            f"user={user_id} tier={tier} effective_tier={effective_tier} "
                            f"signals={len(signals_list)} limit={int(limit)} reserved={len(reserved)} reserve_failed={int(reserve_failed)}",
                            flush=True,
                        )
                    except Exception:
                        pass

                if reserve_failed:
                    # DB dedupe/history failed; still deliver to avoid "silent nothing".
                    sent = 0
                    for signal in signals_list:
                        if sent >= int(limit):
                            break
                        try:
                            _send_message_sync(bot, chat_id=user_id, text=format_signal(signal, display_tier=display_tier))
                            sent += 1
                            if tier == 'free' and extra_left > 0:
                                try:
                                    state.consume_extra_signals_sync(int(user_id), 1)
                                except Exception:
                                    pass
                        except Exception:
                            continue
                    return

                for signal in reserved:
                    try:
                        _send_message_sync(bot, chat_id=user_id, text=format_signal(signal, display_tier=display_tier))
                        if tier == 'free' and extra_left > 0:
                            try:
                                state.consume_extra_signals_sync(int(user_id), 1)
                            except Exception:
                                pass
                    except Exception:
                        continue
                return

            # FREE: queue delayed summaries (max 2/day)
            async def _queue_free() -> None:
                from db.pg_features import queue_free_signal_summary

                daily_limit = 2
                async with get_session() as session:
                    for signal in sorted(signals_list, key=lambda s: s.get('score', 0), reverse=True):
                        ok = await queue_free_signal_summary(session, int(user_id), signal, daily_limit=daily_limit)
                        if not ok:
                            break
                    await session.commit()

            try:
                asyncio.run(_queue_free())
                return
            except Exception as e:
                _log_once(
                    "queue_free_failed",
                    f"[bot] queue free signal summary failed: {type(e).__name__}: {e}",
                )
    except Exception as e:
        _log_once(
            "dispatch_pg_path_failed",
            f"[bot] dispatch postgres path failed: {type(e).__name__}: {e}",
        )

    if tier in ('premium', 'vip', 'owner'):
        bot = Bot(token=_require_telegram_token())
        limit = TIER_LIMITS.get(tier, 0)
        sent = 0
        for signal in signals_list:
            if sent >= limit:
                break
            try:
                _send_message_sync(bot, chat_id=user_id, text=format_signal(signal, display_tier=tier))
                sent += 1
            except Exception:
                continue
        return

    # FREE: queue delayed summary (max 2/day)
    try:
        from db.session import ENGINE, get_session
        if ENGINE is None:
            raise RuntimeError("DATABASE_URL not configured. Postgres is required.")
        daily_limit = 2

        async def _queue() -> None:
            from db.pg_features import queue_free_signal_summary as queue_free_signal_summary_pg

            async with get_session() as session:
                # Only queue up to daily limit; prefer higher score first
                for signal in sorted(signals_list, key=lambda s: s.get('score', 0), reverse=True):
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
            asyncio.run(_queue())
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
        except Exception:
            pass
        # Postgres-only: no SQLite fallback
        return
        

def run_bot() -> None:
    """Run the Telegram polling bot.

    This must be explicitly invoked (e.g. RUN_MODE=bot or RUN_MODE=all). It must
    not run on import.
    """

    from apscheduler.schedulers.background import BackgroundScheduler

    # Avoid leaking bot token in logs: httpx logs full request URLs at INFO.
    # We keep errors, but silence INFO/DEBUG.
    try:
        logging.getLogger("httpx").setLevel(logging.WARNING)
    except Exception:
        pass
    try:
        logging.getLogger("telegram").setLevel(logging.WARNING)
    except Exception:
        pass

    application = Application.builder().token(_require_telegram_token()).build()

    async def _on_error(update, context) -> None:
        err = getattr(context, "error", None)
        print(f"[bot] error: {err}", flush=True)
        # Avoid crashing the bot on handler errors; PTB will continue polling.

    application.add_error_handler(_on_error)

    async def _post_init(app):
        # BotFather-visible commands must remain concise.
        try:
            await app.bot.set_my_commands(
                [
                    ("start", "Start"),
                    ("pricing", "Pricing"),
                    ("upgrade", "Upgrade / subscribe"),
                    ("help", "Commands"),
                    ("signals", "Latest signals"),
                    ("signal", "Signal by reference"),
                    ("performance", "Performance"),
                    ("invite", "Invite"),
                ]
            )
        except Exception:
            pass

    application.post_init = _post_init

    application.add_handler(CommandHandler("start", _audit_handler("start", start_command)))
    application.add_handler(CommandHandler("help", _audit_handler("help", help_command)))
    application.add_handler(CommandHandler("about", _audit_handler("about", about_command)))
    application.add_handler(CommandHandler("faq", _audit_handler("faq", faq_command)))
    application.add_handler(CommandHandler("disclaimer", _audit_handler("disclaimer", disclaimer_command)))
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

    # VIP (not advertised)
    application.add_handler(CommandHandler("elite", _audit_handler("elite", elite_command)))
    application.add_handler(CommandHandler("early", _audit_handler("early", early_command)))
    application.add_handler(CommandHandler("report", _audit_handler("report", report_command)))

    application.add_handler(CommandHandler("policy", _audit_handler("policy", policy_command)))
    application.add_handler(CommandHandler("refunds", _audit_handler("refunds", policy_command)))
    application.add_handler(CommandHandler("recap", _audit_handler("recap", recap_command)))
    application.add_handler(CommandHandler("buy_extra_signals", _audit_handler("buy_extra_signals", buy_extra_signals)))
    # Backward compatible alias

    # Hidden owner-only commands (silent for non-owners)
    application.add_handler(CommandHandler("unlock", _audit_handler("unlock", unlock)))
    application.add_handler(CommandHandler("dev_pause", _audit_handler("dev_pause", dev_pause)))
    application.add_handler(CommandHandler("dev_resume", _audit_handler("dev_resume", dev_resume)))
    application.add_handler(CommandHandler("dev_force_signal", _audit_handler("dev_force_signal", dev_force_signal)))
    application.add_handler(CommandHandler("dev_invalidate", _audit_handler("dev_invalidate", dev_invalidate)))
    application.add_handler(CommandHandler("owner_users", _audit_handler("owner_users", owner_users)))
    application.add_handler(CommandHandler("owner_revenue", _audit_handler("owner_revenue", owner_revenue)))

    def send_weekly_recap():
        user_ids = get_all_user_ids_compat()
        # Prefer Postgres-backed recap when configured
        try:
            from db.session import ENGINE, get_session
            if ENGINE is not None:
                from db.pg_features import get_weekly_recap_stats

                async def _fetch(uid: int) -> dict:
                    async with get_session() as session:
                        data = await get_weekly_recap_stats(session, int(uid))
                        await session.commit()
                        return data

                for user_id in user_ids:
                    try:
                        stats = asyncio.run(_fetch(int(user_id)))
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
                    except Exception:
                        pass
                return
        except Exception:
            pass

        # Postgres-only: no SQLite fallback
        return

    def send_outcome_notifications():
        # Best-effort Postgres follow-up messages for TP/SL/invalid outcomes.
        try:
            from db.session import ENGINE, get_session
            if ENGINE is None:
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
                pending = asyncio.run(_fetch())
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
                    except Exception:
                        pass

                    # Limited free follow-up
                    if str(tier_at_send).lower() == 'free':
                        msg = (
                            "📣 Signal Update\n\n"
                            f"Reference: {ref_short}\n"
                            f"{asset} {timeframe} {direction}\n\n"
                            "An outcome was recorded for a recent signal.\n"
                            "Upgrade to Premium to see full stats and exact levels."
                        )
                    else:
                        label = status.upper() if status else 'UPDATE'
                        status_emoji = "✅" if status in ("tp", "tp1", "tp2", "partial_tp") else ("❌" if status == "sl" else "📌")
                        msg = (
                            f"📣 Outcome Update — {status_emoji} {label}\n\n"
                            f"Reference: {ref_short}\n"
                            f"{asset} {timeframe} {direction}\n"
                        )
                        if r_multiple is not None:
                            try:
                                r_val = float(r_multiple)
                                msg += f"R-Multiple: {r_val:.2f}R\n"
                            except Exception:
                                pass
                        msg += "\nThis signal has been marked with an outcome in the tracker."
                    try:
                        _send_message_sync(application.bot, chat_id=int(telegram_user_id), text=msg)
                    except Exception:
                        pass

                # Mark notified so we don't repeat.
                try:
                    async def _mark(oid: int) -> None:
                        async with get_session() as session:
                            await mark_outcome_notified(session, int(oid))
                            await session.commit()

                    asyncio.run(_mark(int(getattr(oc, 'id'))))
                except Exception:
                    pass
        except Exception:
            return


    def compute_outcomes_best_effort():
        """Best-effort outcome writer.

        Scans recently delivered signals that have no outcome yet, fetches candles,
        and records TP/SL if hit. This enables follow-up messages end-to-end.
        """
        try:
            from db.session import ENGINE, get_session
            if ENGINE is None:
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
                candidates = asyncio.run(_fetch_candidates())
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
                except Exception:
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

                    candles = get_candles(asset, tf)
                    if not candles:
                        continue

                    created_ms = _ms(created_at)
                    # Filter candles to those after signal creation when possible.
                    filtered = []
                    for c in candles:
                        try:
                            ts = c.get("timestamp")
                            if isinstance(ts, (int, float)):
                                if int(ts) >= created_ms:
                                    filtered.append(c)
                            else:
                                # FX timestamps are ISO-ish strings; keep best-effort.
                                filtered.append(c)
                        except Exception:
                            continue
                    if not filtered:
                        continue

                    status = None
                    # Walk candles in chronological order and detect first hit.
                    for c in filtered:
                        try:
                            hi = float(c.get("high"))
                            lo = float(c.get("low"))
                        except Exception:
                            continue
                        if direction == "long":
                            hit_sl = lo <= sl
                            hit_tp = hi >= tp
                        else:
                            hit_sl = hi >= sl
                            hit_tp = lo <= tp

                        if hit_sl and hit_tp:
                            # Ambiguous within-candle; be conservative.
                            status = "sl"
                            break
                        if hit_sl:
                            status = "sl"
                            break
                        if hit_tp:
                            status = "tp"
                            break

                    if status is None:
                        continue

                    # Compute R and % (best-effort)
                    risk = abs(entry - sl)
                    reward = abs(tp - entry)
                    r_mult = None
                    pct = None
                    try:
                        if risk > 0:
                            if status == "tp":
                                r_mult = reward / risk
                            else:
                                r_mult = -1.0
                        if status == "tp":
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

                    async def _write():
                        async with get_session() as session:
                            await upsert_outcome(
                                session,
                                str(sig.signal_id),
                                status,
                                meta=meta,
                                r_multiple=r_mult,
                                percent=pct,
                                opened_at=created_at,
                                closed_at=now,
                            )
                            await session.commit()

                    try:
                        asyncio.run(_write())
                    except Exception:
                        pass
                except Exception:
                    continue

        except Exception:
            return

    def send_free_delayed_summaries():
        # Respect kill-switch
        try:
            if state.get_killswitch_sync().enabled:
                return
        except Exception:
            pass

        logger.info("🔄 send_free_delayed_summaries job triggered")

        # Prefer Postgres-backed delayed queue
        try:
            from db.session import ENGINE, get_session
            if ENGINE is not None:
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
                        except Exception:
                            pass
                        due = await get_due_free_signal_summaries_pg(session)
                        out: dict[int, dict] = {}
                        for uid, items in due.items():
                            prefs = await get_alert_prefs_pg(session, int(uid))
                            out[int(uid)] = {"items": items, "prefs": prefs}
                        await session.commit()
                        return out

                try:
                    due = asyncio.run(_fetch_due())
                    logger.info(f"📬 Free queue check: {len(due)} user(s) with due signals")
                except Exception as e:
                    logger.error(f"Error fetching due signals: {e}", exc_info=True)
                    due = {}

                if not due:
                    logger.info("✅ No free signals due for delivery")
                    return

                now_hour = datetime.now().hour
                per_user_limit = int(os.getenv('FREE_DAILY_LIMIT', '2'))

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
                        except Exception:
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
                    asyncio.run(_apply_actions())
                    logger.info(f"💾 Applied {len(actions)} queue action(s)")
                except Exception as e:
                    logger.error(f"Error applying actions: {e}", exc_info=True)
                return
        except Exception:
            pass

        # Postgres-only: no SQLite fallback
        return

    scheduler = BackgroundScheduler()
    scheduler.add_job(send_free_delayed_summaries, 'interval', minutes=10)
    scheduler.add_job(compute_outcomes_best_effort, 'interval', minutes=3)
    scheduler.add_job(send_outcome_notifications, 'interval', minutes=2)
    scheduler.add_job(
        send_weekly_recap,
        'cron',
        day_of_week='sun',
        hour=18,
        minute=0
    )
    scheduler.start()

    print("[boot] telegram bot polling starting", flush=True)
    application.run_polling()


if __name__ == "__main__":
    run_bot()
