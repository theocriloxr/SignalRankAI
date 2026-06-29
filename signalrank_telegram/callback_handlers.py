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

    # Signal chart / Gemini explanation
    "signal_chart": r"^signal_chart_(.+)$",
    "ask_gemini": r"^ask_gemini_(.+)$",
    
    # Navigation buttons
    "nav": r"^nav_(.+)$",
    
    # Trade now
    "trade_now": r"^trade_now_(.+)$",
    
    # MT5 link/guide
    "mt5_link_guide": r"^mt5_link_guide$",
    "mt5_settings": r"^mt5_settings$",
    "mt5_status": r"^mt5_status$",
    
    # Admin buttons
    "admin": r"^admin_(.+)$",
    
    # VIP sold out
    "vip_sold_out": r"^vip_sold_out$",
    
    # Locked buttons
    "locked": r"^locked_(.+)$",

    # Static agreement/help/waitlist callbacks
    "agree_terms": r"^agree_terms$",
    "decline_terms": r"^decline_terms$",
    "vip_waitlist": r"^vip_waitlist_join$",
    "cancel_confirm": r"^cancel_confirm$",
    "cancel_nevermind": r"^cancel_nevermind$",
    "help_page": r"^help_page_(.+)$",
}


def _parse_callback_data(data: str) -> Dict[str, Any]:
    """
    Parse callback data into action and payload.
    
    Args:
        data: Raw callback data string
        
    Returns:
        Dict with 'action' and 'payload' keys
    """
    if not data:
        return {"action": None, "payload": None}
    
    for action, pattern in CALLBACK_PATTERNS.items():
        match = re.match(pattern, data)
        if not match:
            continue
        groups = match.groups()
        if action == "signal_reaction" and len(groups) >= 2:
            return {"action": action, "payload": f"{groups[0]}|{groups[1]}"}
        if groups:
            return {"action": action, "payload": groups[0]}
        return {"action": action, "payload": None}

    parts = data.split("_", 1)
    if len(parts) < 2:
        return {"action": parts[0] if parts else None, "payload": None}
    return {"action": parts[0], "payload": parts[1]}


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
    
    logger.debug(f"[callback] Unknown action: {action}, payload: {payload}")


async def _global_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Main global callback handler.
    
    This is the CORE FIX - calls query.answer() IMMEDIATELY
    to stop the loading circle timeout bug.
    """
    query = update.callback_query
    
    # CRITICAL: Answer immediately to stop loading circle
    try:
        await query.answer()
    except Exception:
        pass  # May error if already answered
    
    data = query.data
    if not data:
        return
    
    # Parse the callback
    parsed = _parse_callback_data(data)
    action = parsed.get("action")
    payload = parsed.get("payload")
    
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

        elif action == "mt5_status":
            from signalrank_telegram.commands import mt5_status_command

            await mt5_status_command(update, context)
            
        elif action == "open_signal":
            await _handle_open_signal(update, context, payload)

        elif action == "signal_chart":
            await _handle_signal_chart(update, context, payload)

        elif action == "ask_gemini":
            await _handle_ask_gemini(update, context, payload)

        elif action == "locked":
            await _handle_locked(update, context, payload)
            
        elif action and action.startswith("nav"):
            await query.answer()
            
        else:
            await _handle_default_callback(update, context, action, payload)
            
    except Exception as e:
        logger.warning(f"[callback] Global handler error: {e}")
        try:
            await query.answer("Error processing request.", show_alert=True)
        except Exception:
            pass


async def _safe_answer(query, text: str = "", show_alert: bool = False) -> None:
    try:
        await query.answer(text=text or None, show_alert=show_alert)
    except Exception:
        pass


async def _handle_signal_chart(update: Update, context: ContextTypes.DEFAULT_TYPE, signal_id: str) -> None:
    query = update.callback_query
    await _safe_answer(query, "Chart view is not available yet.", show_alert=False)


async def _handle_ask_gemini(update: Update, context: ContextTypes.DEFAULT_TYPE, signal_id: str) -> None:
    query = update.callback_query
    await _safe_answer(query, "Gemini analysis is being prepared.", show_alert=False)


async def _handle_open_signal(update: Update, context: ContextTypes.DEFAULT_TYPE, signal_id: str) -> None:
    query = update.callback_query
    await _safe_answer(query, show_alert=False)


async def _handle_locked(update: Update, context: ContextTypes.DEFAULT_TYPE, feature: str) -> None:
    query = update.callback_query
    await _safe_answer(query, "Upgrade required for this feature.", show_alert=True)


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _global_callback_handler(update, context)


def create_global_callback_handler() -> CallbackQueryHandler:
    """
    Create the global callback query handler.
    
    Add this to your Application in bot.py:
    
        application.add_handler(create_global_callback_handler())
    
    This handler MUST be added AFTER other handlers to catch
    any unmatched callback queries.
    """
    return CallbackQueryHandler(
        _global_callback_handler,
        pattern=None,  # Catch all callbacks
    )


__all__ = [
    "create_global_callback_handler",
    "_global_callback_handler",
    "callback_router",
    "CB_SIGNAL_REACTION",
    "CB_MONITOR_SIGNAL",
    "CB_CHECK_OUTCOME",
    "CB_OPEN_SIGNAL",
    "CB_SIGNAL_CHART",
    "CB_MT5_TRADE",
    "CB_MT5_STATUS",
    "CB_ASK_GEMINI",
    "CB_AGREE_TERMS",
    "CB_DECLINE_TERMS",
    "CB_VIP_WAITLIST",
    "CB_CANCEL_CONFIRM",
    "CB_CANCEL_NEVERMIND",
    "CB_HELP_PAGE",
    "CB_NAV",
    "CB_TRADE_NOW",
    "CB_LOCKED",
    "CB_ADMIN",
    "CB_VIP_SOLD_OUT",
]
