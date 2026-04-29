from telegram import Update
from telegram.ext import ContextTypes

async def mt5_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Link a MetaTrader 5 account for one-click trade execution."""
    if update.effective_user is None or update.message is None:
        return
    
    user_id: int = update.effective_user.id
    tier: str = _effective_tier(user_id)
    
    # Require PREMIUM+
    if tier_rank(tier) < tier_rank("PREMIUM"):
        await update.message.reply_text(
            "🔒 MT5 account linking requires a Premium or VIP subscription.\n"
            "Use /upgrade to unlock one-click MT5 execution."
        )
        return
    
    missing_vars = []
    if not (os.getenv("ENCRYPTION_KEY") or "").strip():
        missing_vars.append("ENCRYPTION_KEY")
    if not (os.getenv("META_API_TOKEN") or "").strip():
        missing_vars.append("META_API_TOKEN")
    if missing_vars:
        await update.message.reply_text(_railway_env_hint("MT5 linking", missing_vars))
        return
    
    args = context.args or []
    if len(args) < 3:
        await update.message.reply_text(
            "⚙️ <b>Link your MT5 Account</b>\n\n"
            "Usage: <code>/mt5_link <login> <password> <server></code>\n\n"
            "Example:\n<code>/mt5_link 123456 MyP@ssw0rd MetaQuotes-Demo</code>\n\n"
            "🔒 Password encrypted with AES-256 before storage.",
            parse_mode="HTML"
        )
        return
    
    mt5_login = args[0].strip()
    mt5_password = args[1].strip()
    mt5_server = " ".join(args[2:]).strip()
    
    # Delete credential message
    try:
        await update.message.delete()
    except Exception:
        pass
    
    processing_msg = await update.effective_chat.send_message("🔄 Linking MT5 account...")
    
    try:
        from services.mt5_client import link_mt5_account
        result = await link_mt5_account(
            telegram_user_id=user_id,
            mt5_login=mt5_login,
            mt5_password=mt5_password,
            mt5_server=mt5_server,
        )
        if result.get("success"):
            meta_id = result.get("metaapi_account_id") or ""
            reply = (
                f"✅ MT5 Account Linked!\n\n"
                f"🏦 Server: {mt5_server}\n"
                f"🔐 Login: {mt5_login}\n"
            )
            if meta_id:
                reply += f"☁️ MetaApi ID: {meta_id}\n"
            reply += (
                "\n⚡ Use Trade buttons on signals to execute.\n\n"
                "⚙️ /execution manual|auto|none\n"
                "⚙️ /setlot 0.01\n"
                "⚙️ /setrisk 1.0%"
            )
        else:
            err = result.get("error", "Unknown error")
            reply = f"❌ MT5 Link Failed: {err}"
    except Exception as exc:
        reply = f"❌ Link Error: {exc}"
    
    await processing_msg.edit_text(reply)

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
            await update.message.reply_text("No MT5 account linked.\n\n/mt5_link <login> <password> <server>")
            return
        
        reply = (
            f"⚙️ Linked MT5 Account\n\n"
            f"🏦 Server: {row.server}\n"
            f"🔐 Login: {row.mt5_login}\n"
        )
        if row.metaapi_account_id:
            reply += f"☁️ MetaApi ID: {row.metaapi_account_id}\n"
        reply += "\n⚡ Ready for signal execution."
        await update.message.reply_text(reply)
    except Exception as exc:
        await update.message.reply_text(f"Status error: {exc}")

__all__ = ['mt5_link_command', 'mt5_status_command']
