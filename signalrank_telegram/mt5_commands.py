from telegram import Update
from telegram.ext import ContextTypes

from signalrank_telegram.command_resilience import safe_command_error
from signalrank_telegram.utils import _effective_tier, tier_rank


def _mt5_not_configured_message() -> str:
    return (
        "⚠️ MT5 linking is not configured on this deployment.\n"
        "Signal analysis and paper trading remain available. Please contact /support."
    )

async def mt5_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open the secure first-party Broker Hub. Linking does not enable trading; never collect broker passwords in Telegram."""
    if update.effective_user is None or update.message is None:
        return

    user_id: int = update.effective_user.id
    tier: str = _effective_tier(user_id)
    if tier_rank(tier) < tier_rank("PREMIUM"):
        await update.message.reply_text(
            "🔒 MT5 account linking requires a Premium or VIP subscription.\n"
            "Use /upgrade to unlock broker connection and verification features."
        )
        return

    try:
        from signalrank_telegram.broker_linking import send_secure_broker_hub_link

        await send_secure_broker_hub_link(update)
    except Exception as exc:
        await update.message.reply_text(
            safe_command_error(
                "Secure broker linking is temporarily unavailable. "
                "Do not send broker passwords in Telegram.",
                exc,
            )
        )


async def mt5_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show linked MT5 account status."""
    if update.effective_user is None or update.message is None:
        return
    
    user_id: int = update.effective_user.id
    tier: str = _effective_tier(user_id)
    
    if tier_rank(tier) < tier_rank("PREMIUM"):
        await update.message.reply_text("🔒 MT5 requires Premium+. /upgrade")
        return
    
    try:
        from db.session import get_session
        from db.models import MT5Credentials, User
        from sqlalchemy import select
        
        async with get_session() as session:
            user_row = (await session.execute(
                select(User).where(User.telegram_user_id == int(user_id))
            )).scalar_one_or_none()
            if user_row is None:
                await update.message.reply_text("No profile. Send /start.")
                return
            
            row = (await session.execute(
                select(MT5Credentials).where(MT5Credentials.user_id == int(user_row.id))
            )).scalar_one_or_none()
        
        if row is None:
            await update.message.reply_text("No MT5 account linked.\n\nUse /mt5_link to open the secure Broker Hub.")
            return
        
        reply = (
            f"⚙️ Linked MT5 Account\n\n"
            f"🏦 Server: {row.server}\n"
            f"🔐 Login: {row.mt5_login}\n"
        )
        if row.metaapi_account_id:
            reply += f"☁️ MetaApi ID: {row.metaapi_account_id}\n"
        reply += "\n🔒 Linked only — execution permission remains OFF until separately verified and enabled."
        await update.message.reply_text(reply)
    except Exception as exc:
        await update.message.reply_text(safe_command_error("Could not fetch MT5 status.", exc))

__all__ = ['mt5_link_command', 'mt5_status_command']
