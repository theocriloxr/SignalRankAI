import os
from telegram import Update, Bot
from telegram.ext import Application, ContextTypes
from .formatter import format_signal
from paystack.paystack import verify_payment
from db.database import has_full_access, get_user_tier, store_signal, auto_expire_subscriptions, get_extra_signals_left, increment_extra_signal_count, generate_referral_code, get_referral_by_code, record_referral_reward, get_referral_rewards


OWNER_IDS = {int(os.getenv("OWNER_TELEGRAM_ID", "0"))}
TIER_LIMITS = {
    "FREE": 0,
    "PREMIUM": 3,
    "VIP": 6,
    "OWNER": 999
}

def get_user_tier(user_id):
    if user_id in OWNER_IDS:
        return "OWNER"
    return get_user_tier(user_id)

def dispatch_signals(strategy_signals, user_id, regime=None):
    bot = Bot(token=os.getenv('TELEGRAM_TOKEN'))
    tier = get_user_tier(user_id)
    limit = TIER_LIMITS.get(tier, 0)
    signals_to_send = strategy_signals[:limit]
    for signal in signals_to_send:
        msg = format_signal(signal)
        bot.send_message(chat_id=user_id, text=msg)
