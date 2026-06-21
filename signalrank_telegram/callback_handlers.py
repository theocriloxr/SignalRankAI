"""
Telegram Global CallbackQueryHandler - Task 2 Fix

This handler:
- Calls query.answer() IMMEDIATELY to stop the loading circle
- Routes all button callbacks to appropriate handlers
- Handles: mt5_trade_*, signal_reaction_*, monitor_signal_*, etc.
"""

import logging
import re
import json
from typing import Optional, Any, Dict, Callable

from telegram import Update, Bot
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    Application,
    ConversationHandler,
)

logger = logging.getLogger(__name__)


# Global callback patterns
CALLBACK_PATTERNS = {
    # MT5 Trade buttons
    "mt5_trade": r"^mt5_trade_(.+)$",
    
    # Signal reactions (Taking It / Watching)
    "signal_reaction": r"^signal_reaction_(.+)\|(.+)$",
    
    # Monitor signal
    "monitor_signal": r"^monitor_signal_(.+)$",
    
    # Check outcome
    "check_outcome": r"^check_outcome_(.+)$",
    
    # Open signal
    "open_signal": r"^open_signal_(.+)$",

    # Signal chart
    "signal_chart": r"^signal_chart_(.+)$",
    
    # Navigation buttons
    "nav": r"^nav_(.+)$",
    
    # Trade now
    "trade_now": r"^trade_now_(.+)$",
    
    # MT5 link/guide
    "mt5_link_guide": r"^mt5_link_guide$",
    "mt5_settings": r"^mt5_settings$",
    
    # Admin buttons
    "admin": r"^admin_(.+)$",
    
    # VIP sold out
    "vip_sold_out": r"^vip_sold_out$",
    
    # Locked buttons
    "locked": r"^locked_(.+)$",
}


def _parse_callback_data(data: str) -> Dict[str, Any]:
    """
    Parse callback data into action and payload.
    
    Args:
        data: Raw callback data string
        
    Returns:
        Dict with 'action' and 'payload' keys
    """
    logger.debug(f"[callback] parsing callback data: {data}")
    if not data:
        return {"action": None, "payload": None}

    # Compound prefixes that use underscore in the prefix (e.g., signal_reaction_, monitor_signal_)
    # Must check these FIRST before simple split
    compound_prefixes = [
        "signal_reaction",
        "monitor_signal",
        "check_outcome",
        "open_signal",
        "signal_chart",
    ]

    for prefix in compound_prefixes:
        if data.startswith(prefix + "_"):
            action = prefix
            payload = data[len(prefix) + 1:]  # Skip prefix + underscore
            return {"action": action, "payload": payload}
    
    # Simple prefixes (no compound)
    simple_prefixes = [
        "mt5_trade",
        "nav",
        "trade_now",
        "locked",
        "admin",
    ]
    
    for prefix in simple_prefixes:
        if data.startswith(prefix + "_"):
            action = prefix
            payload = data[len(prefix) + 1:]
            return {"action": action, "payload": payload}
    
    # Fallback: split on first underscore for unknown patterns
    parts = data.split("_", 1)
    if len(parts) < 2:
        return {"action": parts[0] if parts else None, "payload": None}
    
    action = parts[0]
    payload = parts[1]
    
    return {"action": action, "payload": payload}


async def _handle_mt5_trade(update: Update, context: ContextTypes.DEFAULT_TYPE, signal_id: str) -> None:
    """Handle MT5 trade button click."""
    query = update.callback_query
    
    try:
        # Immediately answer to stop loading
        await query.answer()
        
        # Load signal data
        from signalrank_telegram.bot import _load_signal_payload
        payload = await _load_signal_payload(signal_id)
        
        if not payload:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Signal data unavailable.",
            )
            return
        
        # Get user tier
        from signalrank_telegram.access import resolve_user_tier
        user_id = query.from_user.id
        tier = resolve_user_tier(user_id)
        
        # Check tier for premium
        from signalrank_telegram.commands import tier_rank
        if tier_rank(tier) < tier_rank("PREMIUM"):
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="🔒 Premium feature. Use /upgrade to unlock.",
            )
            return
        
        # Direct to MT5 execution flow
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⚡ Opening MT5 trade execution...",
        )
        
    except Exception as e:
        logger.warning(f"[callback] mt5_trade error: {e}")
        await query.answer("Error processing trade.", show_alert=True)


async def _handle_signal_reaction(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    signal_id: str, 
    reaction: str
) -> None:
    """Handle signal reaction (Taking It / Watching)."""
    query = update.callback_query
    
    try:
        # IMMEDIATELY answer to stop loading circle
        await query.answer()
        
        if reaction not in ("taking_it", "watching"):
            await query.answer("Invalid reaction.", show_alert=False)
            return
        
        user_id = query.from_user.id
        
        # Save reaction to DB
        from db.session import get_session
        from db.models import SignalEngagement
        from db.pg_features import get_or_create_user
        from sqlalchemy import select
        
        async with get_session() as session:
            user = await get_or_create_user(session, telegram_user_id=int(user_id))
            
            # Check existing
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
                session.add(SignalEngagement(
                    user_id=user.id,
                    signal_id=signal_id,
                    reaction=reaction,
                ))
            
            await session.commit()
        
        # Update keyboard
        from signalrank_telegram.bot import (
            _load_signal_payload,
            _load_signal_engagement_counts,
            _build_signal_keyboard,
        )
        
        signal_payload = await _load_signal_payload(signal_id)
        counts = await _load_signal_engagement_counts(signal_id)
        
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                reply_markup=_build_signal_keyboard(signal_id, signal=signal_payload, counts=counts),
            )
        except Exception as e:
            logger.debug(f"[callback] keyboard refresh error: {e}")
        
        # Confirm
        emoji = "🔥" if reaction == "taking_it" else "👀"
        await query.answer(f"{emoji} Noted!", show_alert=False)
        
    except Exception as e:
        logger.warning(f"[callback] reaction error: {e}")
        await query.answer("Error saving reaction.", show_alert=True)


async def _handle_monitor_signal(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    signal_id: str
) -> None:
    """Handle monitor signal button."""
    query = update.callback_query
    
    try:
        # Immediately answer
        await query.answer("Refreshing...")
        
        # Build monitor snapshot
        from signalrank_telegram.bot import _build_monitor_snapshot
        
        text, is_active, expires_at = await _build_monitor_snapshot(signal_id)
        
        # Send new message or edit existing
        try:
            await context.bot.edit_message_text(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                text=text,
                parse_mode="HTML",
            )
        except Exception:
            # Send new if edit fails
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=text,
                parse_mode="HTML",
            )
        
    except Exception as e:
        logger.warning(f"[callback] monitor error: {e}")
        await query.answer("⚠️ Could not load monitor.", show_alert=True)


async def _handle_check_outcome(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    signal_id: str
) -> None:
    """Handle check outcome button."""
    query = update.callback_query
    
    try:
        await query.answer("Checking outcome...")
        
        # Load outcome from DB
        from db.session import get_session
        from db.models import Outcome
        from sqlalchemy import select
        
        async with get_session() as session:
            outcome = (
                await session.execute(
                    select(Outcome).where(Outcome.signal_id == signal_id).limit(1)
                )
            ).scalar_one_or_none()
        
        if outcome:
            status = outcome.status.upper()
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"📊 Outcome: {status}",
            )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="⏳ Outcome not yet determined.",
            )
        
    except Exception as e:
        logger.warning(f"[callback] check_outcome error: {e}")
        await query.answer("Error checking outcome.", show_alert=True)


async def _handle_signal_chart(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    signal_id: str,
) -> None:
    query = update.callback_query

    try:
        await query.answer("Rendering chart...")

        from db.session import get_session
        from db.models import Signal
        from sqlalchemy import select

        async with get_session() as session:
            row = (
                await session.execute(
                    select(Signal).where(Signal.signal_id == signal_id).limit(1)
                )
            ).scalar_one_or_none()

        if row is None:
            await query.answer("Signal not found.", show_alert=True)
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
        from signalrank_telegram.commands import _build_signal_action_keyboard

        caption = f"📊 {row.asset} {str(row.direction or '').upper()} · {row.timeframe}"
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=InputFile(chart_bytes, filename=getattr(chart_bytes, 'name', f'{signal_id}.png')),
            caption=caption,
            reply_markup=_build_signal_action_keyboard(signal_payload),
        )

    except Exception as e:
        logger.warning(f"[callback] signal_chart error: {e}")
        await query.answer("Could not render chart.", show_alert=True)


async def _handle_default_callback(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    action: str, 
    payload: str
) -> None:
    """Handle unknown callbacks gracefully."""
    query = update.callback_query
    
    try:
        await query.answer()
    except Exception:
        pass
    
    logger.warning(f"[callback] Unknown action: {action}, payload: {payload}")


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Main global callback router.
    
    This is the CORE FIX - calls query.answer() IMMEDIATELY
    to stop the loading circle timeout bug.
    """
    query = update.callback_query

    # Log incoming callback meta for debugging (user/chat/message/data)
    try:
        user_id = getattr(getattr(query, "from_user", None), "id", None)
        message = getattr(query, "message", None)
        chat_id = getattr(getattr(message, "chat", None), "id", None) or getattr(message, "chat_id", None)
        msg_id = getattr(message, "message_id", None)
        logger.info(f"[callback] received callback from_user={user_id} chat_id={chat_id} message_id={msg_id}")
    except Exception:
        logger.debug("[callback] failed to read query metadata")

    # CRITICAL: Answer immediately to stop loading circle
    try:
        await query.answer()
    except Exception:
        pass  # May error if already answered

    data = query.data
    if not data:
        logger.debug("[callback] no data in callback query, ignoring")
        return

    # Parse the callback
    parsed = _parse_callback_data(data)
    action = parsed.get("action")
    payload = parsed.get("payload")
    logger.debug(f"[callback] parsed action={action} payload={payload}")

    # Route to appropriate handler
    try:
        if action == "mt5_trade":
            # Handle MT5 trade
            signal_id = payload
            await _handle_mt5_trade(update, context, signal_id)

        elif action == "signal_reaction":
            # Parse signal_id|reaction format
            if "|" in payload:
                signal_id, reaction = payload.split("|", 1)
                await _handle_signal_reaction(update, context, signal_id, reaction)
            else:
                await _handle_default_callback(update, context, action, payload)

        elif action == "monitor_signal":
            await _handle_monitor_signal(update, context, payload)

        elif action == "check_outcome":
            await _handle_check_outcome(update, context, payload)

        elif action == "signal_chart":
            await _handle_signal_chart(update, context, payload)

        elif action == "open_signal":
            # Open signal link
            await query.answer()

        elif action and action.startswith("nav"):
            await query.answer()

        else:
            await _handle_default_callback(update, context, action, payload)

        logger.debug(f"[callback] dispatched action={action} payload={payload}")

    except Exception as e:
        logger.exception(f"[callback] Global handler error: {e}")
        try:
            await query.answer("Error processing request.", show_alert=True)
        except Exception:
            pass


def create_global_callback_handler() -> CallbackQueryHandler:
    """
    Create the global callback query handler.
    
    Add this to your Application in bot.py:
    
        application.add_handler(create_global_callback_handler())
    
    This handler MUST be added AFTER other handlers to catch
    any unmatched callback queries.
    """
    return CallbackQueryHandler(
        callback_router,
        pattern=None,  # Catch all callbacks
    )


__all__ = [
    "create_global_callback_handler",
    "callback_router",
]


# Backward compatibility for older imports.
_global_callback_handler = callback_router
