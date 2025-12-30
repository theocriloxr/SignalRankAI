def buy_extra(update: Update, context: CallbackContext):
    user = update.effective_user
    if len(context.args) != 1:
        update.message.reply_text("Usage: /buy_extra <count>")
        return
    try:
        count = int(context.args[0])
        if count < 1:
            update.message.reply_text("Count must be at least 1.")
            return
    except ValueError:
        update.message.reply_text("Count must be a number.")
        return
    price = 300 * count
    paywall_link = generate_paystack_link(user.id, price, extra_count=count)
    update.message.reply_text(f"To unlock {count} extra signals for today, pay ₦{price}: {paywall_link}")



from .formatter import format_signal
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, CallbackContext
import os
from paystack.paystack import verify_payment
from db.database import has_full_access, get_user_tier, store_signal, auto_expire_subscriptions
import sqlite3

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN')

def start(update: Update, context: CallbackContext):
    user = update.effective_user
    update.message.reply_text("Welcome to SignalRank AI! Use /subscribe <paystack_reference> to upgrade.\n\nIf you pay the wrong amount, your money is NOT refunded. Pay the exact amount for your requested tier.")
def subscribe(update: Update, context: CallbackContext):
    user = update.effective_user
    if len(context.args) != 1:
        update.message.reply_text("Send /subscribe <paystack_reference>")
        return
    reference = context.args[0]
    verified, msg, tier = verify_payment(reference, user.id)
    update.message.reply_text(msg)

def status(update: Update, context: CallbackContext):
    user = update.effective_user
    tier = get_user_tier(user.id)
    update.message.reply_text(f"Your status: {tier}")

def run_bot():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("subscribe", subscribe))
    dp.add_handler(CommandHandler("status", status))
    dp.add_handler(CommandHandler("force_signal", force_signal))
    dp.add_handler(CommandHandler("stats", stats))
    dp.add_handler(CommandHandler("weights", weights))
    dp.add_handler(CommandHandler("pause", pause))
    dp.add_handler(CommandHandler("resume", resume))
    dp.add_handler(CommandHandler("users", users))
    dp.add_handler(CommandHandler("revenue", revenue))
    dp.add_handler(CommandHandler("approve", approve))
    dp.add_handler(CommandHandler("buy_extra", buy_extra))
    updater.start_polling()
    updater.idle()

import datetime
from paystack.paystack import generate_paystack_link
from db.database import get_free_signals_sent_today, increment_free_signal_count, unlock_paid_signal_for_user

def dispatch_signals(ranked_signals):
    bot = Bot(token=TELEGRAM_TOKEN)
    # VIP: instant, all info
    for signal in ranked_signals.get('vip', []):
        for user_id in get_all_users_by_tier('VIP'):
            bot.send_message(chat_id=user_id, text=format_signal(signal))
    # Premium: instant, all info
    for signal in ranked_signals.get('premium', []):
        for user_id in get_all_users_by_tier('PREMIUM'):
            bot.send_message(chat_id=user_id, text=format_signal(signal))
    # Free: 1/day, delayed, stripped info, watermark, ₦300 per extra
    if ranked_signals.get('premium'):
        free_signal = ranked_signals['premium'][0]
        for user_id in get_all_users_by_tier('FREE'):
            today_count = get_free_signals_sent_today(user_id)
            if today_count == 0:
                msg = format_signal({**free_signal, 'score': None, 'strategy_name': None})
                msg += f"\nUser: {hash(user_id) % 100000} (watermark)\nUpgrade for real-time, full info."
                # TODO: Add delay logic (30-60 min)
                bot.send_message(chat_id=user_id, text=msg)
                increment_free_signal_count(user_id)
            else:
                # Offer paywall for extra signals
                extra_signal = ranked_signals['premium'][min(today_count, len(ranked_signals['premium'])-1)]
                paywall_msg = f"You have used your free signal for today.\nUnlock this extra signal for ₦300: "
                paywall_link = generate_paystack_link(user_id, 300, signal_id=extra_signal.get('id'))
                bot.send_message(chat_id=user_id, text=paywall_msg + paywall_link)

# Webhook handler (to be called by Paystack webhook server)
def handle_paystack_webhook(event):
    # event: dict from Paystack webhook
    if event['event'] == 'charge.success':
        user_id = event['data']['metadata']['user_id']
        signal_id = event['data']['metadata'].get('signal_id')
        if event['data']['amount'] == 30000:  # ₦300 in kobo
            unlock_paid_signal_for_user(user_id, signal_id)
            # Optionally, send the unlocked signal instantly

def get_all_users_by_tier(tier):
    # Query DB for all user_ids with current tier
    import sqlite3
    from db.database import DB_PATH
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT user_id FROM subscriptions WHERE tier=?', (tier,))
        return [row[0] for row in c.fetchall()]


# OWNER-ONLY COMMANDS
from db.database import set_subscription, downgrade_to_free

def owner_only(func):
    def wrapper(update: Update, context: CallbackContext):
        user = update.effective_user
        if not has_full_access(user.id):
            return  # Silently ignore
        return func(update, context)
    return wrapper

@owner_only
def force_signal(update: Update, context: CallbackContext):
    update.message.reply_text("Test alert sent.")

@owner_only
def stats(update: Update, context: CallbackContext):
    update.message.reply_text("Full performance stats.")

@owner_only
def weights(update: Update, context: CallbackContext):
    update.message.reply_text("Strategy weights.")

@owner_only
def pause(update: Update, context: CallbackContext):
    update.message.reply_text("Alerts paused.")

@owner_only
def resume(update: Update, context: CallbackContext):
    update.message.reply_text("Alerts resumed.")

@owner_only
def users(update: Update, context: CallbackContext):
    update.message.reply_text("Active users list.")

@owner_only
def revenue(update: Update, context: CallbackContext):
    update.message.reply_text("Earnings summary.")

@owner_only
def approve(update: Update, context: CallbackContext):
    # Usage: /approve <user_id> <tier> <duration_days>
    args = context.args
    if len(args) != 3:
        update.message.reply_text("Usage: /approve <user_id> <tier> <duration_days>")
        return
    user_id, tier, days = int(args[0]), args[1].upper(), int(args[2])
    set_subscription(user_id, tier, days, payment_ref='MANUAL')
    update.message.reply_text(f"User {user_id} upgraded to {tier} for {days} days.")

