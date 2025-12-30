import os
from telegram import Update, Bot
from telegram.ext import Application, ContextTypes
from .formatter import format_signal
from paystack.paystack import verify_payment
from db.database import has_full_access, get_user_tier, store_signal, auto_expire_subscriptions, get_extra_signals_left, increment_extra_signal_count, generate_referral_code, get_referral_by_code, record_referral_reward, get_referral_rewards

def dispatch_signals(strategy_signals, regime=None):
    bot = Bot(token=os.getenv('TELEGRAM_TOKEN'))
    # Example: send a message to a test user or log
    for signal in strategy_signals:
        msg = format_signal(signal)
        # Replace 123456789 with your test user/chat ID
        bot.send_message(chat_id=123456789, text=msg)
