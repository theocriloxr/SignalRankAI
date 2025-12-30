
from .formatter import format_signal
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes
import os
from paystack.paystack import verify_payment
from db.database import has_full_access, get_user_tier, store_signal, auto_expire_subscriptions
import sqlite3

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        "Welcome to SignalRank AI!\n"
        "Tiers & Pricing:\n"
        "PREMIUM MONTHLY: ₦10,000 (30 days)\n"
        "PREMIUM WEEKLY: ₦3,000 (7 days)\n"
        "VIP MONTHLY: ₦25,000 (30 days)\n"
        "VIP WEEKLY: ₦8,000 (7 days)\n"
        "Free users get 1 signal/day.\n"
        "Extra signals: ₦250 each, use /buy_extra <count> to purchase.\n\n"
        "How to subscribe:\n"
        "1. Visit the payment page and pay the exact amount for your desired tier.\n"
        "2. After payment, copy your Paystack reference.\n"
        "3. Use /subscribe <paystack_reference> to activate your tier.\n"
        "Example: /subscribe abcd1234\n"
        "Example: /buy_extra 5\n"
        "If you pay the wrong amount, your money is NOT refunded. Pay the exact amount for your requested tier or extra signals."
    )
    
async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args or len(context.args) != 1:
        update.message.reply_text("Usage: /subscribe <paystack_reference>\nExample: /subscribe abcd1234")
        return
    reference = context.args[0]
    verified, msg, tier = verify_payment(reference, user.id)
    update.message.reply_text(msg)

async def buy_extra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /buy_extra <count>\nExample: /buy_extra 3")
        return
    try:
        count = int(context.args[0])
        if count < 1:
            await update.message.reply_text("Count must be at least 1.")
            return
    except ValueError:
        await update.message.reply_text("Count must be a number.")
        return
    price = 250 * count  # Adjusted price per extra signal
    paywall_link = generate_paystack_link(user.id, price, extra_count=count)
    await update.message.reply_text(
        f"To unlock {count} extra signals for today, pay ₦{price}: {paywall_link}\n"
        "Example: /buy_extra 3 will generate a link for ₦750."
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    tier = get_user_tier(user.id)
    await update.message.reply_text(f"Your status: {tier}\nExample: /status")

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("force_signal", force_signal))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("weights", weights))
    app.add_handler(CommandHandler("pause", pause))
    app.add_handler(CommandHandler("resume", resume))
    app.add_handler(CommandHandler("users", users))
    app.add_handler(CommandHandler("revenue", revenue))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("buy_extra", buy_extra))
    app.run_polling()

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
                paywall_msg = f"You have used your free signal for today.\nUnlock extra signals for ₦250 each using /buy_extra <count>. Example: /buy_extra 3 for 3 signals."
                bot.send_message(chat_id=user_id, text=paywall_msg)

# Webhook handler (to be called by Paystack webhook server)
def handle_paystack_webhook(event):
    # event: dict from Paystack webhook
    if event['event'] == 'charge.success':
        user_id = event['data']['metadata']['user_id']
        extra_count = event['data']['metadata'].get('extra_count', 1)
        amount_paid = int(event['data']['amount']) // 100
        # Unlock extra signals for user for today
        if amount_paid == 250 * extra_count:
            from db.database import approve_extra_signals
            approve_extra_signals(user_id, extra_count)
            # Optionally, notify user
        else:
            # Handle tier upgrades as before
            signal_id = event['data']['metadata'].get('signal_id')
            from db.database import unlock_paid_signal_for_user
            unlock_paid_signal_for_user(user_id, signal_id)

def get_all_users_by_tier(tier):
    # Query DB for all user_ids with current tier
    import sqlite3
    from db.database import DB_PATH
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT user_id FROM subscriptions WHERE tier=?', (tier,))
        return [row[0] for row in c.fetchall()]




# OWNER-ONLY COMMANDS
def owner_only(func):
    def wrapper(update: Update, context: CallbackContext):
        user = update.effective_user
        if not has_full_access(user.id):
            return  # Silently ignore
        return func(update, context)
    return wrapper


@owner_only
async def force_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Test alert sent.")

@owner_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Full performance stats.")

@owner_only
async def weights(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Strategy weights.")

@owner_only
async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Alerts paused.")

@owner_only
async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Alerts resumed.")

@owner_only
async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Active users list.")

@owner_only
async def revenue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Earnings summary.")

@owner_only
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args or len(args) != 3:
        await update.message.reply_text("Usage: /approve <user_id> <tier> <duration_days>\nExample: /approve 123456 PREMIUM 30")
        return
    user_id, tier, days = int(args[0]), args[1].upper(), int(args[2])
    set_subscription(user_id, tier, days, payment_ref='MANUAL')
    await update.message.reply_text(f"User {user_id} upgraded to {tier} for {days} days.")

