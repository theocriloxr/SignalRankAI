import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ContextTypes, CommandHandler

BOT_OWNER = int(os.getenv("OWNER_TELEGRAM_ID", "0"))
BYPASS_KEY = os.getenv("BYPASS_KEY", None)

# ----- helpers (adapt these to your project) -----
def is_owner(user_id: int) -> bool:
    return user_id == BOT_OWNER

# These should be implemented in your project's auth/subscription module:
from db.database import has_full_access, set_subscription
from paystack.paystack import generate_paystack_link
from engine.signal_controller import SignalController

# ----- owner-only decorator -----
def owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if not is_owner(uid):
            return
        return await func(update, context)
    return wrapper

# ----- Public command handlers -----
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"👋 Hello {user.first_name} — welcome to SignalRank AI.\n\n"
        "We filter thousands of signals and deliver only the highest-probability Crypto & FX setups.\n\n"
        "Free: 1 delayed summary/day\n"
        "Premium: real-time alerts, confidence score, SL/TP\n"
        "VIP: elite signals only\n\n"
        "Use /pricing to see plans or /help to learn more."
    )
    keyboard = [
        [InlineKeyboardButton("View Pricing", callback_data="pricing")],
        [InlineKeyboardButton("Upgrade Now", callback_data="upgrade")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "How this works:\n"
        "- We run 15 strategies, require consensus, score signals.\n"
        "- Free users see delayed summaries. Premium users get instant alerts.\n\n"
        "Commands:\n"
        "/pricing — See plans\n"
        "/upgrade — Get a payment link\n"
        "/stats — (Premium) View performance\n\n"
        "Trade responsibly. This is not financial advice."
    )
    await update.message.reply_text(txt)

async def pricing_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "Plans:\n"
        "Weekly - ₦3,000\n"
        "Monthly - ₦10,000\n"
        "VIP - ₦25,000\n\n"
        "Use /upgrade <plan> e.g. /upgrade monthly"
    )
    await update.message.reply_text(txt)

async def upgrade_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args or []
    tier = args[0].lower() if args else "monthly"
    if tier not in ("weekly","monthly","vip"):
        await update.message.reply_text("Usage: /upgrade <weekly|monthly|vip>")
        return
    link = generate_paystack_link(user_id, tier)
    text = f"Click to pay for {tier.capitalize()}: {link}"
    await update.message.reply_text(text)

async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not has_full_access(user_id):
        await update.message.reply_text(
            "🔒 Performance stats are for Premium users. Use /upgrade to unlock."
        )
        return
    # Placeholder: Replace with actual summary logic
    await update.message.reply_text("Performance summary (stub).")

async def unlock_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args or []
    if not args:
        return
    key = args[0]
    if key == BYPASS_KEY:
        set_subscription(user_id, "OWNER", 365, payment_ref="BYPASS")
        await update.message.reply_text("✅ Bypass key accepted. Full access granted (test).")
    else:
        await update.message.reply_text("Invalid key.")

# ----- Owner / Dev commands (hidden) -----
@owner_only
async def dev_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Internal stats (owner-only stub).")

@owner_only
async def dev_force_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    controller = SignalController()
    # Placeholder: Implement force dispatch logic
    await update.message.reply_text("Forced test signal dispatched.")

@owner_only
async def dev_pause_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    controller = SignalController()
    controller.kill()
    await update.message.reply_text("Dispatch paused (owner override).")

@owner_only
async def dev_resume_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    controller = SignalController()
    controller.revive()
    await update.message.reply_text("Dispatch resumed (owner override).")

# ----- Register handlers function -----
def register_handlers(app):
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("pricing", pricing_handler))
    app.add_handler(CommandHandler("upgrade", upgrade_handler))
    app.add_handler(CommandHandler("stats", stats_handler))
    app.add_handler(CommandHandler("unlock", unlock_handler))
    app.add_handler(CommandHandler("dev_stats", dev_stats_handler))
    app.add_handler(CommandHandler("dev_force_signal", dev_force_signal))
    app.add_handler(CommandHandler("dev_pause", dev_pause_handler))
    app.add_handler(CommandHandler("dev_resume", dev_resume_handler))

async def set_bot_commands(app):
    cmds = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "How SignalRank AI works"),
        BotCommand("pricing", "View plans"),
        BotCommand("upgrade", "Upgrade your plan"),
        BotCommand("stats", "View performance (Premium)")
    ]
    await app.bot.set_my_commands(cmds)
