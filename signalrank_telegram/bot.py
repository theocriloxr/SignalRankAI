import os
from telegram import Bot
from telegram.ext import Application, CommandHandler

from core.performance import performance_tracker
from db.database import get_all_user_ids
from signalrank_telegram.access import resolve_user_tier
from .formatter import format_signal
from .commands import (
    start_command,
    about_command,
    faq_command,
    disclaimer_command,
    performance_command,
    pricing_command,
    upgrade_command,
    policy_command,
    recap_command,
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

    # Local dev convenience: load from a `.env` file if present.
    # Railway/production should use real environment variables.
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
        user_ids = get_all_user_ids()
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
    bot = Bot(token=_require_telegram_token())
    tier_raw = resolve_user_tier(user_id)
    tier = (tier_raw or 'FREE').strip().lower()
    limit = TIER_LIMITS.get(tier, 0)

    if not strategy_signals:
        return

    sent = 0
    for signal in strategy_signals:
        if sent >= limit:
            break
        try:
            if tier in ('premium', 'vip', 'owner'):
                bot.send_message(chat_id=user_id, text=format_signal(signal))
            else:
                bot.send_message(chat_id=user_id, text=_format_free_preview(signal))
            sent += 1
        except Exception:
            # Don't crash dispatch loop on one bad message
            continue

from apscheduler.schedulers.background import BackgroundScheduler
from db.database import get_all_user_ids

def run_bot():
    application = Application.builder().token(_require_telegram_token()).build()

    async def _post_init(app):
        # Keep public commands concise; hidden commands are not registered.
        try:
            await app.bot.set_my_commands(
                [
                    ("start", "Start"),
                    ("about", "About"),
                    ("faq", "FAQ"),
                    ("pricing", "Pricing"),
                    ("upgrade", "Upgrade / subscribe"),
                    ("policy", "Policy / refunds"),
                    ("recap", "Weekly recap"),
                    ("performance", "(Premium) performance"),
                ]
            )
        except Exception:
            pass

    application.post_init = _post_init

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("faq", faq_command))
    application.add_handler(CommandHandler("disclaimer", disclaimer_command))
    application.add_handler(CommandHandler("performance", performance_command))
    application.add_handler(CommandHandler("pricing", pricing_command))
    application.add_handler(CommandHandler("upgrade", upgrade_command))
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
        user_ids = get_all_user_ids()
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

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        send_weekly_recap,
        'cron',
        day_of_week='sun',
        hour=18,
        minute=0
    )
    scheduler.start()

    application.run_polling()


if __name__ == "__main__":
    run_bot()
