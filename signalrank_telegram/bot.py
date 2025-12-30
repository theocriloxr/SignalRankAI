import os
from telegram import Update, Bot
from telegram.ext import Application, ContextTypes
from .formatter import format_signal
from paystack.paystack import verify_payment
from db.database import store_signal
from telegram.access import resolve_user_tier

TIER_LIMITS = {
    "FREE": 0,
    "PREMIUM": 3,
    "VIP": 6,
    "OWNER": 999
}


from core.signal_governor import can_send_signal, record_signal_sent

def dispatch_signals(strategy_signals, user_id, regime=None):
    bot = Bot(token=os.getenv('TELEGRAM_TOKEN'))
    tier = resolve_user_tier(user_id)
    limit = TIER_LIMITS.get(tier, 0)
    signals_sent = 0
    for signal in strategy_signals:
        if signals_sent >= limit:
            break
        if not can_send_signal(tier):
            continue
        msg = format_signal(signal)
        bot.send_message(chat_id=user_id, text=msg)
        record_signal_sent(tier)
        signals_sent += 1
