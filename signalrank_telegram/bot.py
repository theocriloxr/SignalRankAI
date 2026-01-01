import os
import asyncio
import socket
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
    version_command,
    about_command,
    faq_command,
    disclaimer_command,
    performance_command,
    pricing_command,
    upgrade_command,
    policy_command,
    recap_command,
    signals_command,
    invite_command,
    stats_command,
    history_command,
    risk_command,
    alerts_command,
    elite_command,
    early_command,
    report_command,
    buy_extra_premium,
    buy_extra_vip,
)

from core.redis_state import state
from .owner_commands import unlock, dev_pause, dev_resume, dev_force_signal, dev_invalidate

TIER_LIMITS = {
    'free': 2,
    'premium': 10,
    'vip': 30,
    'owner': 9999,
}


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
        f"Asset: {signal.get('asset')}\n"
        f"Timeframe: {signal.get('timeframe')}\n"
        f"Direction: {signal.get('direction')}\n\n"
        "Upgrade to Premium to see:\n"
        "• Exact entry, stop, target\n"
        "• Real-time alerts\n"
        "• Full performance tracking"
    )

def dispatch_signals(strategy_signals, user_id, regime=None):
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
        if tier in ('vip',):
            signals_list = vip_list
        elif tier in ('premium',):
            # Premium sees full signals (premium + vip)
            signals_list = vip_list + prem_list
        elif tier in ('owner',):
            signals_list = vip_list + prem_list
        else:
            # Free: delayed summaries from top approved signals
            signals_list = (vip_list + prem_list)

        # Paid extra signals: VIP-style only, real-time
        if tier == 'free' and extra_left > 0:
            signals_list = vip_list
    else:
        signals_list = list(strategy_signals or [])

    if not signals_list:
        return

    # Postgres-backed delivery dedup + history (preferred)
    try:
        from db.session import ENGINE, get_session

        if ENGINE is not None:
            effective_tier = tier
            if tier == 'free' and extra_left > 0:
                effective_tier = 'vip'

            if effective_tier in ('premium', 'vip', 'owner'):
                bot = Bot(token=_require_telegram_token())
                limit = TIER_LIMITS.get(effective_tier, 0)
                if tier == 'free' and extra_left > 0:
                    limit = min(int(limit), int(extra_left))

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
                except Exception:
                    reserved = []

                for signal in reserved:
                    try:
                        bot.send_message(chat_id=user_id, text=format_signal(signal))
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

                daily_limit = int(os.getenv('FREE_DAILY_LIMIT', '2'))
                async with get_session() as session:
                    for signal in sorted(signals_list, key=lambda s: s.get('score', 0), reverse=True):
                        ok = await queue_free_signal_summary(session, int(user_id), signal, daily_limit=daily_limit)
                        if not ok:
                            break
                    await session.commit()

            try:
                asyncio.run(_queue_free())
                return
            except Exception:
                pass
    except Exception:
        pass

    if tier in ('premium', 'vip', 'owner'):
        bot = Bot(token=_require_telegram_token())
        limit = TIER_LIMITS.get(tier, 0)
        sent = 0
        for signal in signals_list:
            if sent >= limit:
                break
            try:
                bot.send_message(chat_id=user_id, text=format_signal(signal))
                sent += 1
            except Exception:
                continue
        return

    # FREE: queue delayed summary (max 2/day)
    try:
        from db.database import queue_free_signal_summary
        daily_limit = int(os.getenv('FREE_DAILY_LIMIT', '2'))
        # Only queue up to daily limit; prefer higher score first
        for signal in sorted(signals_list, key=lambda s: s.get('score', 0), reverse=True):
            ok = queue_free_signal_summary(user_id, signal, daily_limit=daily_limit)
            if not ok:
                break
    except Exception:
        # As a fallback, send the old limited preview (should be rare)
        try:
            bot = Bot(token=_require_telegram_token())
            bot.send_message(chat_id=user_id, text=_format_free_preview(signals_list[0]))
        except Exception:
            pass


def _in_quiet_hours(now_hour: int, start_hour: int, end_hour: int) -> bool:
    """Return True if now_hour is within quiet hours. Supports wrap-around."""
    start_hour = int(start_hour)
    end_hour = int(end_hour)
    now_hour = int(now_hour)
    if start_hour == end_hour:
        return False
    if start_hour < end_hour:
        return start_hour <= now_hour < end_hour
    return now_hour >= start_hour or now_hour < end_hour


def _format_free_delayed_digest(items: list[dict]) -> str:
    lines = ["🔒 FREE USER (DELAYED SIGNAL SUMMARY)", "", "Recent high-score activity:", ""]
    for it in items:
        lines.append(
            f"• {it.get('asset')} {it.get('timeframe')} {it.get('direction')} (score {it.get('score', 0)})"
        )
    lines += [
        "",
        "Upgrade to Premium to get real-time entries, SL/TP, and alerts.",
        "Use /upgrade to subscribe.",
    ]
    return "\n".join(lines)

from apscheduler.schedulers.background import BackgroundScheduler
from db.pg_compat import get_all_user_ids_compat

def run_bot():
    print(
        "[boot] telegram bot starting | "
        f"host={socket.gethostname()} "
        f"run_mode={(os.getenv('RUN_MODE') or 'engine').strip().lower()} "
        f"railway_service={os.getenv('RAILWAY_SERVICE_NAME')} "
        f"railway_deployment={os.getenv('RAILWAY_DEPLOYMENT_ID')} "
        f"git_sha={os.getenv('RAILWAY_GIT_COMMIT_SHA')}",
        flush=True,
    )

    # Ensure an event loop exists in this (main) thread.
    # Python 3.12+ no longer creates one implicitly, and PTB's run_polling()
    # uses asyncio.get_event_loop().
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Preflight token + Telegram connectivity before starting long-polling.
    try:
        token = _require_telegram_token()
        print("[boot] telegram bot token_present=yes", flush=True)

        async def _preflight() -> None:
            me = await Bot(token=token).get_me()
            print(f"[boot] telegram bot getMe ok: @{me.username} ({me.id})", flush=True)

        loop.run_until_complete(_preflight())
    except Exception as exc:
        # Crash loudly: Railway logs should show this and restart.
        print(f"[boot] telegram bot preflight failed: {exc}", flush=True)
        raise

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
                    ("performance", "Performance"),
                    ("invite", "Invite"),
                ]
            )
        except Exception:
            pass

    application.post_init = _post_init

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("version", version_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("faq", faq_command))
    application.add_handler(CommandHandler("disclaimer", disclaimer_command))
    application.add_handler(CommandHandler("performance", performance_command))
    application.add_handler(CommandHandler("pricing", pricing_command))
    application.add_handler(CommandHandler("upgrade", upgrade_command))
    application.add_handler(CommandHandler("signals", signals_command))
    application.add_handler(CommandHandler("invite", invite_command))

    # Premium (not advertised)
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("risk", risk_command))
    application.add_handler(CommandHandler("alerts", alerts_command))

    # VIP (not advertised)
    application.add_handler(CommandHandler("elite", elite_command))
    application.add_handler(CommandHandler("early", early_command))
    application.add_handler(CommandHandler("report", report_command))

    application.add_handler(CommandHandler("policy", policy_command))
    application.add_handler(CommandHandler("refunds", policy_command))
    application.add_handler(CommandHandler("recap", recap_command))
    application.add_handler(CommandHandler("buy_extra_premium", buy_extra_premium))
    application.add_handler(CommandHandler("buy_extra_vip", buy_extra_vip))

    # Hidden owner-only commands (silent for non-owners)
    application.add_handler(CommandHandler("unlock", unlock))
    application.add_handler(CommandHandler("dev_pause", dev_pause))
    application.add_handler(CommandHandler("dev_resume", dev_resume))
    application.add_handler(CommandHandler("dev_force_signal", dev_force_signal))
    application.add_handler(CommandHandler("dev_invalidate", dev_invalidate))

    from db.database import fetch_user_trades
    def send_weekly_recap():
        user_ids = get_all_user_ids_compat()
        for user_id in user_ids:
            trades = fetch_user_trades(user_id)
            total_signals = len(trades)
            if total_signals == 0:
                recap_msg = (
                    "\U0001F4CA SignalRankAI Weekly Recap\n\n"
                    "No signals were sent to you this week.\n\n"
                    "Remember: No signals is sometimes better than bad signals.\n\n"
                    "Thank you for trading responsibly."
                )
            else:
                # Calculate most active markets, best strategy, avg RR
                from collections import Counter
                assets = [t[2] for t in trades]  # asset column
                strategies = [t[9] for t in trades]  # strategy_name column
                rr_ratios = [t[7] for t in trades if t[7] is not None]
                most_active = ', '.join([a for a, _ in Counter(assets).most_common(2)]) if assets else 'N/A'
                best_strategy = Counter(strategies).most_common(1)[0][0] if strategies else 'N/A'
                avg_rr = round(sum(rr_ratios)/len(rr_ratios), 2) if rr_ratios else 'N/A'
                recap_msg = (
                    f"\U0001F4CA SignalRankAI Weekly Recap\n\n"
                    f"Here’s a quick overview of your past week:\n\n"
                    f"• Total signals sent: {total_signals}\n"
                    f"• Markets most active: {most_active}\n"
                    f"• Best-performing strategy: {best_strategy}\n"
                    f"• Average risk/reward: {avg_rr}\n\n"
                    "Market conditions were mixed, so signal frequency was intentionally limited.\n\n"
                    "Remember:\nNo signals is sometimes better than bad signals.\n\n"
                    "Thank you for trading responsibly."
                )
            application.bot.send_message(chat_id=user_id, text=recap_msg)

    def send_free_delayed_summaries():
        # Respect kill-switch
        try:
            if state.get_killswitch_sync().enabled:
                return
        except Exception:
            pass

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
                except Exception:
                    due = {}

                if not due:
                    return

                now_hour = datetime.now().hour
                per_user_limit = int(os.getenv('FREE_DAILY_LIMIT', '2'))

                actions: list[tuple[int, list[int], list[str], str]] = []

                for uid, data in due.items():
                    items = list(data.get("items") or [])
                    prefs = dict(data.get("prefs") or {})

                    if not prefs.get("tp_sl_enabled", True):
                        actions.append(
                            (int(uid), [it["id"] for it in items], [it["signal_id"] for it in items], 'suppressed')
                        )
                        continue

                    qs = prefs.get("quiet_start_hour")
                    qe = prefs.get("quiet_end_hour")
                    if qs is not None and qe is not None:
                        try:
                            if _in_quiet_hours(now_hour, int(qs), int(qe)):
                                continue
                        except Exception:
                            pass

                    items = items[:per_user_limit]
                    msg = _format_free_delayed_digest(items)
                    status = 'sent'
                    try:
                        application.bot.send_message(chat_id=int(uid), text=msg)
                    except Exception:
                        status = 'failed'

                    actions.append(
                        (int(uid), [it["id"] for it in items], [it["signal_id"] for it in items], status)
                    )

                if not actions:
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
                except Exception:
                    pass
                return
        except Exception:
            pass

        # SQLite fallback
        try:
            from db.database import (
                get_due_free_signal_summaries,
                mark_free_signal_summaries_sent,
                expire_old_free_signal_summaries,
                get_alert_prefs,
            )
        except Exception:
            return

        try:
            expire_old_free_signal_summaries(max_age_hours=24)
        except Exception:
            pass

        try:
            due = get_due_free_signal_summaries()
        except Exception:
            due = {}
        if not due:
            return

        now_hour = datetime.now().hour
        per_user_limit = int(os.getenv('FREE_DAILY_LIMIT', '2'))

        for user_id, items in due.items():
            try:
                prefs = get_alert_prefs(int(user_id))
            except Exception:
                prefs = {"tp_sl_enabled": True, "quiet_start_hour": None, "quiet_end_hour": None}

            if not prefs.get("tp_sl_enabled", True):
                try:
                    mark_free_signal_summaries_sent([it["id"] for it in items], status='suppressed')
                except Exception:
                    pass
                continue

            qs = prefs.get("quiet_start_hour")
            qe = prefs.get("quiet_end_hour")
            if qs is not None and qe is not None:
                try:
                    if _in_quiet_hours(now_hour, int(qs), int(qe)):
                        continue
                except Exception:
                    pass

            items = items[:per_user_limit]
            msg = _format_free_delayed_digest(items)
            try:
                application.bot.send_message(chat_id=int(user_id), text=msg)
                mark_free_signal_summaries_sent([it["id"] for it in items], status='sent')
            except Exception:
                try:
                    mark_free_signal_summaries_sent([it["id"] for it in items], status='failed')
                except Exception:
                    pass

    scheduler = BackgroundScheduler()
    scheduler.add_job(send_free_delayed_summaries, 'interval', minutes=10)
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
