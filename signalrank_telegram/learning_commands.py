"""/lessons and /why: what the bot has learned from every resolved trade (ml/trade_review.py)."""
from __future__ import annotations

from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from signalrank_telegram.command_resilience import safe_command_error


async def _signal_id_for(ref: str) -> str | None:
    """Accept a display id (e.g. SR-1234) or a raw signal id."""
    from sqlalchemy import text

    from db.session import get_session

    async with get_session(priority="interactive", label="telegram.why") as session:
        row = (await session.execute(
            text("SELECT signal_id FROM signals WHERE display_id = :r OR signal_id = :r LIMIT 1"), {"r": ref},
        )).first()
    return str(row[0]) if row else None


def format_why(review: dict[str, Any] | None, ref: str) -> str:
    if not review:
        return (f"No review for {ref} yet. Reviews are written for delivered and paper trades once they "
                "resolve (refreshed every few hours). Send /lessons for what the bot has learned so far.")
    head = f"🔎 {review.get('asset')} {review.get('timeframe')} — {ref}"
    return head + "\n" + str(review.get("text") or review.get("headline") or "")


async def lessons_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    try:
        from ml.trade_review import lessons_text, load_snapshot

        await update.message.reply_text("🧠 " + lessons_text(await load_snapshot())[:3900])
    except Exception as exc:
        await update.message.reply_text(safe_command_error("Could not load the lessons.", exc))


async def why_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    args = list(getattr(context, "args", None) or [])
    if not args:
        await update.message.reply_text("Send /why <signal id>, for example /why SR-1234.")
        return
    ref = str(args[0]).strip()
    try:
        from ml.trade_review import load_snapshot

        snapshot = await load_snapshot() or {}
        reviews = snapshot.get("reviews") or {}
        review = reviews.get(ref)
        if review is None:
            sid = await _signal_id_for(ref)
            review = reviews.get(sid) if sid else None
        await update.message.reply_text(format_why(review, ref)[:3900])
    except Exception as exc:
        await update.message.reply_text(safe_command_error("Could not load that trade review.", exc))
