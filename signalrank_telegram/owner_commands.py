import os
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from core.redis_state import state


def _owner_id() -> int:
    try:
        return int(os.getenv("OWNER_TELEGRAM_ID", "0"))
    except ValueError:
        return 0


async def _is_owner(user_id: int) -> bool:
    oid = _owner_id()
    if oid and user_id == oid:
        return True
    return await state.has_temp_owner(user_id)


def _bypass_key() -> Optional[str]:
    key = os.getenv("BYPASS_KEY")
    return key.strip() if key else None


async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not context.args or len(context.args) != 1:
        return  # silent

    provided = context.args[0]
    expected = _bypass_key()
    if not expected or provided != expected:
        return  # silent

    # 24h temporary owner access
    await state.set_temp_owner(update.effective_user.id, ttl_seconds=24 * 3600)
    await update.message.reply_text("Access granted.")


async def dev_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        return
    await state.set_killswitch(True, reason="paused via /dev_pause")
    await update.message.reply_text("Kill-switch enabled.")


async def dev_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        return
    await state.set_killswitch(False, reason="")
    await update.message.reply_text("Kill-switch disabled.")


async def dev_force_signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        return

    # Safe synthetic test message (explicitly a test)
    await update.message.reply_text(
        "[TEST] Forced signal trigger received.\n"
        "This is a system test message (not a trade recommendation)."
    )


async def dev_invalidate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if not await _is_owner(update.effective_user.id):
        return
    if not context.args or len(context.args) != 1:
        return
    signal_id = context.args[0]
    # TODO: persist invalidation to Postgres outcomes/admin_events.
    await update.message.reply_text(f"Invalidated: {signal_id}")
