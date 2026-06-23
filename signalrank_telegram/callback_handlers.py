"""
SignalRankAI — Global CallbackQueryHandler (PERFECTED)

ROOT CAUSE OF INLINE KEYBOARD BUG:
  Telegram requires query.answer() within 30 seconds. If the handler crashes
  or is never reached (e.g. handler not registered / wrong pattern), the button
  just spins forever and nothing appears in logs because PTB swallows errors
  before they reach the handler. The fix is threefold:
    1. Register this catch-all AFTER all specific handlers.
    2. Call query.answer() as the ABSOLUTE FIRST async operation.
    3. Wrap everything in try/except so errors are logged, never swallowed.

ARCHITECTURE:
  - Specific handlers (signal_reaction_, monitor_signal_, etc.) own full behavior.
  - This module is the SAFETY NET — answers any callback that slipped through.
  - It also duplicates the specific behavior so it works standalone if specific
    handlers fail to register.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from typing import Any, Dict, Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
)

logger = logging.getLogger(__name__)

# ─── Callback data constants ──────────────────────────────────────────────────

CB_SIGNAL_REACTION = "signal_reaction_"
CB_MONITOR_SIGNAL = "monitor_signal_"
CB_CHECK_OUTCOME = "check_outcome_"
CB_OPEN_SIGNAL = "open_signal_"
CB_SIGNAL_CHART = "signal_chart_"
CB_MT5_TRADE = "mt5_trade_"
CB_MT5_STATUS = "mt5_status"
CB_ASK_GEMINI = "ask_gemini_"
CB_AGREE_TERMS = "agree_terms"
CB_DECLINE_TERMS = "decline_terms"
CB_VIP_WAITLIST = "vip_waitlist_join"
CB_CANCEL_CONFIRM = "cancel_confirm"
CB_CANCEL_NEVERMIND = "cancel_nevermind"
CB_HELP_PAGE = "help_page_"
CB_NAV = "nav_"
CB_TRADE_NOW = "trade_now"
CB_LOCKED = "locked_"
CB_ADMIN = "admin_"
CB_VIP_SOLD_OUT = "vip_sold_out"


# ─── Helper: answer immediately ───────────────────────────────────────────────

async def _safe_answer(query, text: str = "", show_alert: bool = False) -> None:
    """Answer callback query safely — always, even if already answered."""
    try:
        await query.answer(text=text, show_alert=show_alert)
    except Exception:
        pass  # Already answered or expired — that's fine


# ─── Signal reaction handler ──────────────────────────────────────────────────

async def _handle_signal_reaction(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    signal_id: str,
    reaction: str,
) -> None:
    """Handle 🔥 Taking It / 👀 Watching reactions."""
    query = update.callback_query
    user_id = getattr(getattr(query, "from_user", None), "id", None)
    if not user_id:
        return

    if reaction not in ("taking_it", "watching"):
        await _safe_answer(query, "Invalid reaction.", show_alert=True)
        return

    try:
        from db.session import get_session
        from db.models import SignalEngagement
        from db.pg_features import get_or_create_user
        from sqlalchemy import select

        async with get_session() as session:
            user = await get_or_create_user(session, telegram_user_id=int(user_id))
            existing = (
                await session.execute(
                    select(SignalEngagement).where(
                        SignalEngagement.user_id == user.id,
                        SignalEngagement.signal_id == signal_id,
                    )
                )
            ).scalar_one_or_none()

            if existing:
                existing.reaction = reaction
            else:
                session.add(
                    SignalEngagement(
                        user_id=user.id,
                        signal_id=signal_id,
                        reaction=reaction,
                    )
                )
            await session.commit()

        # Refresh keyboard counters
        try:
            from signalrank_telegram.bot import (
                _load_signal_payload,
                _load_signal_engagement_counts,
                _build_signal_keyboard,
            )
            payload = await _load_signal_payload(signal_id)
            counts = await _load_signal_engagement_counts(signal_id)
            keyboard = _build_signal_keyboard(signal_id, signal=payload, counts=counts)
            await context.bot.edit_message_reply_markup(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                reply_markup=keyboard,
            )
        except Exception as _kbe:
            if "message is not modified" not in str(_kbe).lower():
                logger.debug(f"[callback] keyboard refresh: {_kbe}")

        emoji = "🔥" if reaction == "taking_it" else "👀"
        await _safe_answer(query, f"{emoji} Noted!")

    except Exception as exc:
        logger.warning(f"[callback] signal_reaction error: {exc}")
        await _safe_answer(query, "Could not save reaction.", show_alert=True)


# ─── Monitor signal handler ───────────────────────────────────────────────────

async def _handle_monitor_signal(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    signal_id: str,
) -> None:
    """Handle 📈 Monitor button — show live trade snapshot."""
    query = update.callback_query
    user_id = getattr(getattr(update, "effective_user", None), "id", None)
    chat_id = getattr(getattr(update, "effective_chat", None), "id", None)

    try:
        from signalrank_telegram.bot import _build_monitor_snapshot, _build_monitor_keyboard
        text, is_active, expires_at = await _build_monitor_snapshot(signal_id)

        # Persist/update monitor message for future refreshes
        from db.session import get_session
        from db.models import RuntimeState
        from sqlalchemy import select

        runtime_key = f"monitor:{int(user_id or 0)}:{signal_id}"
        message_id = None
        async with get_session() as session:
            state_row = (
                await session.execute(
                    select(RuntimeState).where(RuntimeState.key == runtime_key).limit(1)
                )
            ).scalar_one_or_none()
            if state_row is not None:
                try:
                    message_id = int((state_row.value or {}).get("message_id") or 0) or None
                except Exception:
                    message_id = None
            await session.commit()

        keyboard = _build_monitor_keyboard(signal_id)
        edited = False
        if message_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=int(chat_id),
                    message_id=int(message_id),
                    text=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                edited = True
            except Exception as exc:
                err = str(exc).lower()
                if "message is not modified" in err:
                    edited = True  # No-op edit is fine
                elif any(t in err for t in ("not found", "blocked", "can't be edited")):
                    message_id = None  # Stale row — recreate

        if not edited:
            sent_msg = await context.bot.send_message(
                chat_id=int(chat_id),
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            message_id = int(sent_msg.message_id)

        # Persist updated message_id
        if message_id and user_id and chat_id:
            try:
                from datetime import datetime
                async with get_session() as session:
                    state_row = (
                        await session.execute(
                            select(RuntimeState).where(RuntimeState.key == runtime_key).limit(1)
                        )
                    ).scalar_one_or_none()
                    if state_row is None:
                        state_row = RuntimeState(key=runtime_key, value={})
                        session.add(state_row)
                    state_row.value = {
                        "telegram_user_id": int(user_id),
                        "chat_id": int(chat_id),
                        "message_id": int(message_id),
                        "signal_id": str(signal_id),
                    }
                    state_row.expires_at = expires_at
                    state_row.updated_at = datetime.utcnow()
                    await session.commit()
            except Exception:
                pass

    except Exception as exc:
        logger.warning(f"[callback] monitor_signal error: {exc}")
        await _safe_answer(query, "⚠️ Could not load monitor.", show_alert=True)


# ─── Check outcome handler ────────────────────────────────────────────────────

async def _handle_check_outcome(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    signal_id: str,
) -> None:
    """Handle 🔍 Check Outcome — show signal status as alert popup."""
    query = update.callback_query
    try:
        from db.session import get_session
        from db.models import Signal, Outcome
        from sqlalchemy import select
        from datetime import datetime, timezone

        async with get_session() as session:
            sig_row = (
                await session.execute(
                    select(Signal).where(Signal.signal_id == signal_id).limit(1)
                )
            ).scalar_one_or_none()
            out_row = None
            if sig_row:
                out_row = (
                    await session.execute(
                        select(Outcome).where(Outcome.signal_id == signal_id).limit(1)
                    )
                ).scalar_one_or_none()
            await session.commit()

        if sig_row is None:
            await _safe_answer(query, "❌ Signal not found.", show_alert=True)
            return

        asset = getattr(sig_row, "asset", "?")
        direction = str(getattr(sig_row, "direction", "?") or "?").upper()
        score = getattr(sig_row, "score", 0)
        expired = getattr(sig_row, "expired", False)
        created = getattr(sig_row, "created_at", None)

        age_str = ""
        if created:
            try:
                _c = created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created
                _mins = int((datetime.now(timezone.utc) - _c).total_seconds() / 60)
                age_str = f" | Age: {_mins}m"
            except Exception:
                pass

        if out_row:
            outcome = str(getattr(out_row, "status", "unknown") or "unknown").upper()
            r_multiple = getattr(out_row, "r_multiple", None)
            pct = getattr(out_row, "percent", None)
            emoji = "✅" if outcome.startswith("TP") else ("🛑" if outcome == "SL" else "ℹ️")
            r_str = f" | {r_multiple:.2f}R" if r_multiple is not None else ""
            pct_str = f" ({pct:+.2f}%)" if pct is not None else ""
            msg = f"{emoji} {asset} {direction}\nOutcome: {outcome}{pct_str}{r_str}\nScore: {score:.0f}{age_str}"
        elif expired:
            msg = f"⏰ {asset} {direction}\nStatus: Expired{age_str}"
        else:
            msg = f"🟢 {asset} {direction}\nStatus: Active (no outcome yet)\nScore: {score:.0f}{age_str}"

        await _safe_answer(query, msg, show_alert=True)

    except Exception as exc:
        logger.warning(f"[callback] check_outcome error: {exc}")
        await _safe_answer(query, "⚠️ Could not retrieve signal status.", show_alert=True)


# ─── Signal chart handler ─────────────────────────────────────────────────────

async def _handle_signal_chart(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    signal_id: str,
) -> None:
    """Handle 📊 Chart button — send price chart image."""
    query = update.callback_query
    try:
        from db.session import get_session
        from db.models import Signal
        from sqlalchemy import select

        async with get_session() as session:
            row = (
                await session.execute(
                    select(Signal).where(Signal.signal_id == signal_id).limit(1)
                )
            ).scalar_one_or_none()
            await session.commit()

        if row is None:
            await _safe_answer(query, "Signal not found.", show_alert=True)
            return

        signal_payload = {
            "signal_id": row.signal_id,
            "asset": row.asset,
            "timeframe": row.timeframe,
            "direction": row.direction,
            "entry": row.entry,
            "stop_loss": row.stop_loss,
            "take_profit": row.take_profit,
            "rr_ratio": getattr(row, "rr_estimate", None),
            "score": row.score,
            "regime": getattr(row, "regime", None),
            "strategy_name": getattr(row, "strategy_name", None),
            "strategy_group": getattr(row, "strategy_group", None),
            "recent_ohlcv": getattr(row, "recent_ohlcv", None),
        }

        from signalrank_telegram.signal_charts import build_signal_chart
        chart_bytes = await build_signal_chart(signal_payload)

        if chart_bytes is None:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="⚠️ Chart data is not available for this signal yet.",
            )
            return

        from telegram import InputFile
        caption = (
            f"📊 {row.asset} {str(row.direction or '').upper()} · {row.timeframe}\n"
            f"Score: {row.score:.0f} | Ref: {signal_id[:8]}"
        )
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=InputFile(chart_bytes, filename=f"{signal_id[:8]}.png"),
            caption=caption,
        )

    except Exception as exc:
        logger.warning(f"[callback] signal_chart error: {exc}")
        await _safe_answer(query, "Could not render chart.", show_alert=True)


# ─── Ask Gemini handler ───────────────────────────────────────────────────────

async def _handle_ask_gemini(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    signal_id: str,
) -> None:
    """Handle 🤖 Ask Gemini Why — explain why the signal was generated."""
    query = update.callback_query
    chat_id = getattr(getattr(update, "effective_chat", None), "id", None)
    try:
        from db.session import get_session
        from db.models import Signal
        from sqlalchemy import select

        async with get_session() as session:
            row = (
                await session.execute(
                    select(Signal).where(Signal.signal_id == signal_id).limit(1)
                )
            ).scalar_one_or_none()
            await session.commit()

        if row is None:
            await _safe_answer(query, "Signal not found.", show_alert=True)
            return

        # Build a brief explanation from stored data first (fallback)
        asset = getattr(row, "asset", "?")
        direction = str(getattr(row, "direction", "?") or "?").upper()
        score = getattr(row, "score", 0)
        regime = getattr(row, "regime", "UNKNOWN") or "UNKNOWN"
        strategy = getattr(row, "strategy_name", "Unknown") or "Unknown"
        ml_prob = getattr(row, "ml_probability", None)
        
        ml_str = f"ML Probability: {ml_prob * 100:.1f}%\n" if ml_prob else ""
        
        explanation = (
            f"🤖 <b>Why This Signal?</b>\n\n"
            f"<b>{asset}</b> {direction} — Score: <b>{score:.0f}/100</b>\n\n"
            f"<b>Strategy:</b> {strategy}\n"
            f"<b>Market Regime:</b> {regime}\n"
            f"{ml_str}"
            f"\n<i>SignalRankAI detected favorable conditions for this setup "
            f"based on technical confluence, market structure, and ML validation.</i>"
        )

        # Try to get a real Gemini explanation
        try:
            from services.gemini_ml import ask_gemini_signal_explanation
            signal_dict = {
                "asset": asset,
                "direction": direction,
                "timeframe": getattr(row, "timeframe", ""),
                "entry": getattr(row, "entry", None),
                "stop_loss": getattr(row, "stop_loss", None),
                "take_profit": getattr(row, "take_profit", None),
                "score": score,
                "regime": regime,
                "strategy_name": strategy,
                "ml_probability": ml_prob,
            }
            gemini_text = await ask_gemini_signal_explanation(signal_dict)
            if gemini_text:
                explanation = f"🤖 <b>Gemini Analysis — {asset} {direction}</b>\n\n{gemini_text}"
        except Exception:
            pass  # Use fallback explanation

        await context.bot.send_message(
            chat_id=int(chat_id),
            text=explanation,
            parse_mode="HTML",
        )

    except Exception as exc:
        logger.warning(f"[callback] ask_gemini error: {exc}")
        await _safe_answer(query, "Could not fetch explanation.", show_alert=True)


# ─── Open signal handler ───────────────────────────────────────────────────────

async def _handle_open_signal(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    signal_id: str,
) -> None:
    """Handle Go to Signal button — copy active signal message to user."""
    query = update.callback_query
    user_id = getattr(getattr(update, "effective_user", None), "id", None)
    if not user_id:
        await _safe_answer(query, "Unable to resolve account.", show_alert=True)
        return

    try:
        from db.session import get_session
        from db.models import ActiveSignalMessage
        from db.pg_features import get_or_create_user
        from sqlalchemy import select

        async with get_session() as session:
            user = await get_or_create_user(session, telegram_user_id=int(user_id))
            row = (
                await session.execute(
                    select(ActiveSignalMessage)
                    .where(
                        ActiveSignalMessage.user_id == int(user.id),
                        ActiveSignalMessage.signal_id == str(signal_id),
                        ActiveSignalMessage.is_active.is_(True),
                    )
                    .order_by(ActiveSignalMessage.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            await session.commit()

        if row is None:
            await _safe_answer(query, "Signal message not found. Use /signals for latest.", show_alert=True)
            return

        await context.bot.copy_message(
            chat_id=int(user_id),
            from_chat_id=int(row.chat_id),
            message_id=int(row.message_id),
        )

    except Exception as exc:
        logger.debug(f"[callback] open_signal error: {exc}")
        await _safe_answer(query, "Could not open signal right now.", show_alert=True)


# ─── Locked button handler ────────────────────────────────────────────────────

async def _handle_locked(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    feature: str,
) -> None:
    """Handle locked feature buttons — show upgrade prompt."""
    query = update.callback_query
    feature_labels = {
        "tp3": "TP3 Target",
        "exact_entry": "Exact Entry Price",
        "sl_details": "Stop Loss Details",
        "chart": "Live Chart",
        "gemini": "Gemini AI Analysis",
        "mt5": "MT5 Auto-Execute",
        "signals": "Full Signal Access",
    }
    label = feature_labels.get(feature, feature.replace("_", " ").title())

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            f"🔒 <b>{label} — Premium Feature</b>\n\n"
            "Upgrade to access full signal details including:\n"
            "• Exact entries, stop loss & all TP targets\n"
            "• Live trade monitoring\n"
            "• Gemini AI analysis\n"
            "• MT5 auto-execution\n\n"
            "Use /upgrade to subscribe."
        ),
        parse_mode="HTML",
    )


# ─── Main callback router ─────────────────────────────────────────────────────

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Global callback router — safety net for all inline keyboard presses.

    CRITICAL: query.answer() MUST be the first await call to stop the
    loading spinner. If this is skipped or delayed, the button spins
    indefinitely and nothing shows in the Telegram client.

    This handler is registered AFTER all specific handlers, so it only
    processes callbacks that weren't matched by specific patterns.
    """
    query = update.callback_query
    if query is None:
        return

    data = getattr(query, "data", "") or ""
    user_id = getattr(getattr(query, "from_user", None), "id", None)
    chat_id = getattr(getattr(getattr(query, "message", None), "chat", None), "id", None)
    msg_id = getattr(getattr(query, "message", None), "message_id", None)

    # CRITICAL STEP 1: Log the callback hit immediately (before any await)
    # This is the debug line that confirms the handler was reached.
    logger.warning(
        "[CALLBACK_ROUTER] HIT: user=%s chat=%s msg=%s data=%s",
        user_id,
        chat_id,
        msg_id,
        data,
    )

    # CRITICAL STEP 2: Answer the callback query IMMEDIATELY
    # This stops the loading spinner regardless of what happens next.
    await _safe_answer(query)

    if not data:
        logger.debug("[callback_router] empty data, ignoring")
        return

    # ── Route to specific handlers ───────────────────────────────────────────
    try:
        if data.startswith(CB_SIGNAL_REACTION):
            # Format: signal_reaction_<signal_id>|<reaction>
            payload = data[len(CB_SIGNAL_REACTION):]
            if "|" in payload:
                signal_id, reaction = payload.split("|", 1)
                await _handle_signal_reaction(update, context, signal_id.strip(), reaction.strip())
            else:
                logger.warning("[callback_router] malformed signal_reaction data: %s", data)

        elif data.startswith(CB_MONITOR_SIGNAL):
            signal_id = data[len(CB_MONITOR_SIGNAL):].strip()
            await _handle_monitor_signal(update, context, signal_id)

        elif data.startswith(CB_CHECK_OUTCOME):
            signal_id = data[len(CB_CHECK_OUTCOME):].strip()
            await _handle_check_outcome(update, context, signal_id)

        elif data.startswith(CB_OPEN_SIGNAL):
            signal_id = data[len(CB_OPEN_SIGNAL):].strip()
            await _handle_open_signal(update, context, signal_id)

        elif data.startswith(CB_SIGNAL_CHART):
            signal_id = data[len(CB_SIGNAL_CHART):].strip()
            await _handle_signal_chart(update, context, signal_id)

        elif data.startswith(CB_ASK_GEMINI):
            signal_id = data[len(CB_ASK_GEMINI):].strip()
            await _handle_ask_gemini(update, context, signal_id)

        elif data.startswith(CB_MT5_TRADE):
            # MT5 trade handled by specific handler in bot.py; this is the fallback
            logger.debug("[callback_router] mt5_trade caught by safety net: %s", data)

        elif data == CB_MT5_STATUS:
            # Proxy to mt5_status command
            try:
                from types import SimpleNamespace
                from signalrank_telegram.commands import mt5_status_command
                proxy = SimpleNamespace(
                    effective_user=update.effective_user,
                    message=query.message,
                )
                await mt5_status_command(proxy, context)
            except Exception as exc:
                logger.debug("[callback_router] mt5_status fallback error: %s", exc)

        elif data.startswith(CB_LOCKED):
            feature = data[len(CB_LOCKED):].strip()
            await _handle_locked(update, context, feature)

        elif data.startswith(CB_NAV) or data.startswith("trade_now") or data.startswith("admin_"):
            # Navigation/admin buttons answered above; no further action needed
            pass

        elif data == CB_VIP_SOLD_OUT:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=(
                    "⚠️ <b>VIP Tier Temporarily Full</b>\n\n"
                    "We limit VIP spots to ensure signal quality.\n"
                    "Join the waitlist to be notified when a spot opens.\n\n"
                    "/upgrade for current availability."
                ),
                parse_mode="HTML",
            )

        elif data in (CB_AGREE_TERMS, CB_DECLINE_TERMS, CB_VIP_WAITLIST,
                      CB_CANCEL_CONFIRM, CB_CANCEL_NEVERMIND) or data.startswith(CB_HELP_PAGE):
            # These have specific registered handlers; log if caught here
            logger.info("[callback_router] safety-net catch of known pattern: %s", data)

        else:
            logger.info("[callback_router] unrecognized callback data: %s", data)

    except Exception as exc:
        logger.exception("[callback_router] unhandled error for data=%s: %s", data, exc)
        # Try to show user an error (query already answered so use send_message)
        try:
            if chat_id:
                await context.bot.send_message(
                    chat_id=int(chat_id),
                    text="⚠️ Something went wrong processing that button. Please try again.",
                )
        except Exception:
            pass


def create_global_callback_handler() -> CallbackQueryHandler:
    """
    Create the global safety-net callback handler.

    Register this LAST in bot.py with:
        application.add_handler(create_global_callback_handler())

    It catches any callback that wasn't matched by earlier specific handlers,
    ensuring the loading spinner ALWAYS stops.
    """
    return CallbackQueryHandler(
        callback_router,
        pattern=None,  # Catch-all: matches every callback_data
    )


__all__ = [
    "create_global_callback_handler",
    "callback_router",
    "CB_SIGNAL_REACTION",
    "CB_MONITOR_SIGNAL",
    "CB_CHECK_OUTCOME",
    "CB_OPEN_SIGNAL",
    "CB_SIGNAL_CHART",
    "CB_ASK_GEMINI",
    "CB_MT5_TRADE",
    "CB_MT5_STATUS",
    "CB_ASK_GEMINI",
]

# Backward compatibility
_global_callback_handler = callback_router