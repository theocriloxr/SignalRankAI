import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

"""LEGACY TELEGRAM BOT (kept for backward compatibility).

Primary bot implementation: `signalrank_telegram/`.

This module is intentionally guarded to avoid accidentally running the legacy
bot in production. To run it directly, set:

    ALLOW_LEGACY_TELEGRAM_BOT=true
"""

from functools import wraps
from telegram import Update, Bot
from telegram.ext import Application, ContextTypes, CallbackContext, CommandHandler
from engine.signal_controller import SignalController
from formatter import format_signal
from paystack.paystack import verify_payment
from db.database import has_full_access, get_user_tier, store_signal, auto_expire_subscriptions, get_extra_signals_left, increment_extra_signal_count, generate_referral_code, get_referral_by_code, record_referral_reward, get_referral_rewards

# --- Decorators ---
def owner_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not has_full_access(user_id):
            return
        return await func(update, context)
    return wrapper



signal_controller = SignalController()

# --- Public Command Handlers ---
async def killswitch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if str(user_id) not in os.getenv('OWNER_IDS', '').split(','):
        await update.message.reply_text("Unauthorized.")
        return
    args = context.args
    if args and args[0].lower() == 'on':
        reason = ' '.join(args[1:]) or 'No reason provided'
        signal_controller.enable_kill_switch(reason, admin_id=user_id)
        await update.message.reply_text(f"KILL SWITCH ENABLED. Reason: {reason}")
    elif args and args[0].lower() == 'off':
        signal_controller.disable_kill_switch(admin_id=user_id)
        await update.message.reply_text("KILL SWITCH DISABLED.")
    else:
        await update.message.reply_text("Usage: /killswitch on <reason> | /killswitch off")
    signal_controller.log_audit_event('admin_kill_switch', user_id=user_id, details={'args': args})
user_last_command = {}
def rate_limited(seconds=2):
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            now = time.time()
            last = user_last_command.get(user_id, 0)
            if now - last < seconds:
                await update.message.reply_text("⏳ Please wait before sending another command.")
                return
            user_last_command[user_id] = now
            return await func(update, context)
        return wrapper
    return decorator

def check_kill_switch(update, context):
    if signal_controller.is_kill_switch_enabled():
        update.message.reply_text("🚨 The system is currently in emergency shutdown (kill-switch enabled). Please contact admin.")
        return True
    return False

@rate_limited()
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if check_kill_switch(update, context):
        return
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

@rate_limited()
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if check_kill_switch(update, context):
        return
    user = update.effective_user
    tier = get_user_tier(user.id)
    await update.message.reply_text(f"Your status: {tier}\nExample: /status")

@rate_limited()
async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if check_kill_switch(update, context):
        return
    user = update.effective_user
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /subscribe <paystack_reference>\nExample: /subscribe abcd1234")
        return
    reference = context.args[0]
    verified, msg, tier = verify_payment(reference, user.id)
    await update.message.reply_text(msg)

@rate_limited()
async def buy_extra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if check_kill_switch(update, context):
        return
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

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    code = generate_referral_code(user.id)
    await update.message.reply_text(
        f"Your referral code: {code}\nShare this code. When someone subscribes using your code, you earn rewards!\nUse /my_referrals to view your rewards."
    )

async def my_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    rewards = get_referral_rewards(user.id)
    if not rewards:
        await update.message.reply_text("No referral rewards yet. Share your code to earn!")
        return
    msg = "Your referral rewards:\n"
    for r in rewards:
        _, referrer_id, referred_id, reward_type, reward_value, created_at = r
        msg += f"Referred user {referred_id}: {reward_type} ({reward_value}) on {created_at}\n"
    await update.message.reply_text(msg)

# --- Owner/Admin Commands ---
@owner_only
async def admin_kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    signal_controller.enable_kill_switch("Manual admin_kill", admin_id=update.effective_user.id)
    await update.message.reply_text("Kill-switch activated. All signals paused.")

@owner_only
async def admin_revive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    signal_controller.disable_kill_switch(admin_id=update.effective_user.id)
    await update.message.reply_text("Kill-switch deactivated. Signals resumed.")

@owner_only
async def dev_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Internal stats (owner-only stub).")

@owner_only
async def dev_users_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("User list (owner-only stub).")

@owner_only
async def dev_revenue_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Revenue summary (owner-only stub).")

@owner_only
async def dev_force_signal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Force signal sent (owner-only stub).")

@owner_only
async def dev_toggle_strategy_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Strategy toggled (owner-only stub).")

@owner_only
async def dev_pause_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot paused (owner-only stub).")

@owner_only
async def dev_resume_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot resumed (owner-only stub).")

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

if __name__ == "__main__":
    if os.getenv("ALLOW_LEGACY_TELEGRAM_BOT", "false").strip().lower() not in {"1", "true", "yes", "y", "on"}:
        raise SystemExit(
            "Legacy bot entrypoint blocked. "
            "Use RUN_MODE=bot python main.py (recommended), "
            "or set ALLOW_LEGACY_TELEGRAM_BOT=true to run telegram/bot.py."
        )

    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN')
    app = Application.builder().token(TELEGRAM_TOKEN).build()


    # Register public commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("buy_extra", buy_extra))
    app.add_handler(CommandHandler("killswitch", killswitch))
    app.add_handler(CommandHandler("referral", referral))
    app.add_handler(CommandHandler("my_referrals", my_referrals))

    # Register owner/admin/dev commands
    app.add_handler(CommandHandler("admin_kill", admin_kill))
    app.add_handler(CommandHandler("admin_revive", admin_revive))
    app.add_handler(CommandHandler("dev_stats", dev_stats_handler))
    app.add_handler(CommandHandler("dev_users", dev_users_handler))
    app.add_handler(CommandHandler("dev_revenue", dev_revenue_handler))
    app.add_handler(CommandHandler("dev_force_signal", dev_force_signal_handler))
    app.add_handler(CommandHandler("dev_toggle_strategy", dev_toggle_strategy_handler))
    app.add_handler(CommandHandler("dev_pause", dev_pause_handler))
    app.add_handler(CommandHandler("dev_resume", dev_resume_handler))
    app.add_handler(CommandHandler("users", users))
    app.add_handler(CommandHandler("revenue", revenue))
    app.add_handler(CommandHandler("approve", approve))

    print("SignalRankAI Telegram bot is running. Press Ctrl+C to stop.")
    app.run_polling()




@owner_only
async def dev_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Internal stats (owner-only stub).")

@owner_only
async def dev_users_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("User list (owner-only stub).")

@owner_only
async def dev_revenue_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Revenue summary (owner-only stub).")

@owner_only
async def dev_force_signal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Force signal sent (owner-only stub).")

@owner_only
async def dev_toggle_strategy_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Strategy toggled (owner-only stub).")

@owner_only
async def dev_pause_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot paused (owner-only stub).")

@owner_only
async def dev_resume_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot resumed (owner-only stub).")


from formatter import format_signal
from telegram import Update, Bot
from telegram.ext import Application, ContextTypes
import os
from paystack.paystack import verify_payment
from db.database import has_full_access, get_user_tier, store_signal, auto_expire_subscriptions, get_extra_signals_left, increment_extra_signal_count, generate_referral_code, get_referral_by_code, record_referral_reward, get_referral_rewards
async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    code = generate_referral_code(user.id)
    await update.message.reply_text(
        f"Your referral code: {code}\nShare this code. When someone subscribes using your code, you earn rewards!\nUse /my_referrals to view your rewards."
    )

async def my_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    rewards = get_referral_rewards(user.id)
    if not rewards:
        await update.message.reply_text("No referral rewards yet. Share your code to earn!")
        return
    msg = "Your referral rewards:\n"
    for r in rewards:
        _, referrer_id, referred_id, reward_type, reward_value, created_at = r
        msg += f"Referred user {referred_id}: {reward_type} ({reward_value}) on {created_at}\n"
    await update.message.reply_text(msg)
from engine.signal_controller import SignalController
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
    from telegram.commands import register_handlers, set_bot_commands
    register_handlers(app)
    import asyncio
    asyncio.run(set_bot_commands(app))
    app.run_polling()

import datetime
from paystack.paystack import generate_paystack_link
from db.database import get_free_signals_sent_today, increment_free_signal_count, unlock_paid_signal_for_user

def dispatch_signals(strategy_signals, regime):
    bot = Bot(token=TELEGRAM_TOKEN)
    controller = SignalController()
    approved = controller.approve_signals(strategy_signals, regime)
    ranked = controller.rank_and_release(approved)
    # VIP: instant, all info
    vip_user_ids = get_all_users_by_tier('VIP')
    # Add owner to VIP recipients
    from db.database import OWNER_TELEGRAM_ID
    if OWNER_TELEGRAM_ID not in vip_user_ids:
        vip_user_ids.append(OWNER_TELEGRAM_ID)
    for signal in ranked.get('vip', []):
        for user_id in vip_user_ids:
            bot.send_message(chat_id=user_id, text=format_signal(signal))
    # Premium: instant, all info
    for signal in ranked.get('premium', []):
        for user_id in get_all_users_by_tier('PREMIUM'):
            bot.send_message(chat_id=user_id, text=format_signal(signal))
    # Free: 1/day, delayed, stripped info, watermark, ₦250 per extra
    if ranked.get('premium'):
        free_signal = ranked['premium'][0]
        for user_id in get_all_users_by_tier('FREE'):
            today_count = get_free_signals_sent_today(user_id)
            extra_left = get_extra_signals_left(user_id)
            if today_count == 0:
                msg = format_signal({**free_signal, 'score': None, 'strategy_name': None})
                msg += f"\nUser: {hash(user_id) % 100000} (watermark)\nUpgrade for real-time, full info."
                # TODO: Add delay logic (30-60 min)
                bot.send_message(chat_id=user_id, text=msg)
                increment_free_signal_count(user_id)
            elif extra_left > 0:
                # Send extra signal
                extra_signal = ranked['premium'][min(today_count, len(ranked['premium'])-1)]
                msg = format_signal({**extra_signal, 'score': None, 'strategy_name': None})
                msg += f"\n(Extra signal unlocked)\nUpgrade for unlimited, real-time signals."
                bot.send_message(chat_id=user_id, text=msg)
                increment_extra_signal_count(user_id)
            else:
                # Offer paywall for extra signals
                paywall_msg = f"You have used your free and extra signals for today.\nUnlock more signals for ₦250 each using /buy_extra <count>. Example: /buy_extra 3 for 3 signals."
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


# --- Owner/Admin Command Handlers (moved up to avoid NameError) ---
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

