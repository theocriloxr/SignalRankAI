import os
from telegram import Update, Bot
from telegram.ext import Application, ContextTypes
from .formatter import format_signal
from paystack.paystack import verify_payment
from db.database import store_signal
from signalrank_telegram.access import resolve_user_tier

import os
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
from .formatter import format_signal
from .commands import start_command, about_command, faq_command, disclaimer_command, performance_command, pricing_command, policy_command, recap_command


from core.signal_governor import can_send_signal, record_signal_sent

def dispatch_signals(strategy_signals, user_id, regime=None):
    bot = Bot(token=os.getenv('TELEGRAM_TOKEN'))
    tier = resolve_user_tier(user_id)
    limit = TIER_LIMITS.get(tier, 0)
    signals_sent = 0
    for signal in strategy_signals:
        pass

from apscheduler.schedulers.background import BackgroundScheduler
from db.database import get_all_user_ids

def run_bot():
    application = Application.builder().token(os.getenv('TELEGRAM_TOKEN')).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("faq", faq_command))
    application.add_handler(CommandHandler("disclaimer", disclaimer_command))
    application.add_handler(CommandHandler("performance", performance_command))

    application.add_handler(CommandHandler("pricing", pricing_command))
    application.add_handler(CommandHandler("policy", policy_command))
    application.add_handler(CommandHandler("refunds", policy_command))
    application.add_handler(CommandHandler("recap", recap_command))
    # Extra signal purchase for free users
    from .commands import buy_extra_premium, buy_extra_vip
    application.add_handler(CommandHandler("buy_extra_premium", buy_extra_premium))
    application.add_handler(CommandHandler("buy_extra_vip", buy_extra_vip))

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
