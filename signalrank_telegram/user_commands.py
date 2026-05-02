import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from signalrank_telegram.access import resolve_user_tier
from signalrank_telegram.utils import _effective_tier, _public_guard, tier_rank, _build_dynamic_menu

async def start_command(update, context):
    # Diagnostic entry log
    try:
        logger.info(
            "[/start] handler invoked user_id=%s username=%s chat_id=%s",
            getattr(getattr(update, 'effective_user', None), 'id', 'unknown'),
            getattr(getattr(update, 'effective_user', None), 'username', 'unknown'),
            getattr(getattr(update, 'effective_chat', None), 'id', 'unknown'),
        )
    except Exception:
        pass
    if update.effective_user is None or update.message is None:
        return
    user_id = update.effective_user.id
    # Rate limit start command only
    try:
        if state.rate_limited_sync(
            int(user_id),
            limit=int(START_COMMAND_RATE_LIMIT["limit"]),
            window_seconds=int(START_COMMAND_RATE_LIMIT["window_seconds"]),
        ):
            await update.message.reply_text("Rate limit exceeded. Please wait.")
            return
    except Exception:
        pass
    
    username = getattr(update.effective_user, 'username', None)
    ref_token = str(context.args[0]) if getattr(context, "args", None) else None
    
    # Welcome message
    msg = (
        "SignalRankAI provides algorithmic market analysis for educational purposes only. "
        "This is not financial advice. Trading involves risk.\n\n"
        "What you get:\n"
        "• Risk-managed signals filtered for high-probability setups\n"
        "• Outcome tracking (no hype, no guarantees)\n\n"
        "Use /proof for verified outcomes, /pricing to see plans, or /upgrade to subscribe."
    )
    
    _tier = _effective_tier(int(user_id))
    _kbd_start = _build_dynamic_menu(user_id=int(user_id), tier=_tier)
    await update.message.reply_text(msg, reply_markup=_kbd_start)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user status, tier, signal quotas, expiry."""
    if update.effective_user is None:
        return
    if update.message is None and getattr(update, "callback_query", None) is not None:
        try:
            update.message = update.callback_query.message
        except Exception:
            pass
    if update.message is None:
        return
    
    user_id = update.effective_user.id
    msg, keyboard = await _compose_status_message(int(user_id))
    await update.message.reply_text(msg, reply_markup=keyboard)

async def account_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Alias for /status with dynamic tier menu."""
    return await status_command(update, context)

async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quick support contact."""
    if update.effective_user is None or update.message is None:
        return
    support_contact = "@theocrilox"
    await update.message.reply_text(f"For help or questions, contact support: {support_contact}")

async def about_command(update, context) -> None:
    """Show what SignalRankAI is about."""
    if update.message is not None:
        msg = (
            "\U0001F4CA About SignalRankAI\n\n"
            "SignalRankAI is a rule-based trading signal platform designed to deliver high-quality, risk-aware trade ideas.\n\n"
            "The system:\n"
            "• Uses multiple market strategies\n"
            "• Applies ML-assisted quality filters\n"
            "• Filters out weak or risky setups\n"
            "• Ranks signals by quality\n"
            "• Limits signal frequency to avoid noise\n\n"
            "Markets:\n"
            "• Crypto (BTC, ETH, SOL, and more)\n"
            "• Forex (EUR/USD, GBP/USD, USD/JPY, and more)\n"
            "• Stocks (AAPL, TSLA, MSFT, and more)\n"
            "• Commodities (Gold, Silver, Oil, Natural Gas)\n\n"
            "SignalRankAI does not execute trades and does not guarantee profits.\n"
            "All signals are for educational and informational purposes only.\n\n"
            "Trade responsibly.\n\n"
            "Support: @theocrilox"
        )
        await update.message.reply_text(msg)

async def faq_command(update, context) -> None:
    """Frequently asked questions."""
    if update.message is not None:
        msg = (
            "\u2754 Frequently Asked Questions\n\n"
            "1) Does SignalRankAI place trades for me?\n"
            "No. SignalRankAI only provides trade signals. You decide if and how you trade.\n\n"
            "2) Are profits guaranteed?\n"
            "No. Trading always involves risk. No system can guarantee profits.\n\n"
            "3) How often are signals sent?\n"
            "Only when high-quality setups appear. Some days may have fewer or no signals.\n\n"
            "4) What markets are covered?\n"
            "Crypto (BTC, ETH, SOL), Forex (EUR/USD, GBP/USD, USD/JPY), Stocks (AAPL, TSLA, MSFT), and Commodities (Gold, Silver, Oil, Natural Gas).\n\n"
            "5) What's the difference between Free, Premium, and VIP?\n"
            "Free: Proof-oriented feed (up to 3/day) with limited details.\n"
            "Premium: Broader active feed with full Entry, SL, TP, and analytics.\n"
            "VIP: Stricter high-conviction feed with elite controls and priority delivery.\n\n"
            "Yes. Subscriptions expire automatically. Auto-renew only applies if you opt in and link a card.\n\n"
            "7) Is this financial advice?\n"
            "No. Signals are for informational purposes only."
        )
        await update.message.reply_text(msg)

async def disclaimer_command(update, context) -> None:
    """Financial disclaimer."""
    if await _public_guard(update):
        return
    if update.message is not None:
        msg = (
            "⚠️ Disclaimer\n\n"
            "SignalRankAI provides trading signals for informational and educational purposes only.\n\n"
            "Nothing provided by this bot constitutes financial advice, investment advice, or a recommendation to buy or sell any asset.\n\n"
            "Trading involves risk, and you are fully responsible for your trading decisions.\n"
            "Past performance does not guarantee future results.\n\n"
            "By using SignalRankAI, you acknowledge and accept these risks."
        )
        await update.message.reply_text(msg)

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's Telegram ID."""
    if update.effective_user is None or update.message is None:
        return
    user_id: int = update.effective_user.id
    tier: str = _effective_tier(user_id)
    msg: str = f"Your Telegram user ID: `{user_id}`\nYour current tier: *{tier}*"
    await update.message.reply_text(msg, parse_mode="MarkdownV2")

__all__ = [
    'start_command', 'status_command', 'account_command',
    'support_command', 'about_command', 'faq_command',
    'disclaimer_command', 'myid_command'
]
