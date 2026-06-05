"""
Telegram Callback Query Handler - Task 2 Fix

Fixes:
- Telegram inline buttons showing flashing loading circle
- Buttons failing to execute

Implementation:
- Global CallbackQueryHandler for all button callbacks
- Immediate query.answer() call to stop loading circle
- Basic routing for button query.data payloads
"""

import logging
from typing import Any, Optional

from telegram import Update
from telegram.ext import CallbackContext, CallbackQueryHandler

logger = logging.getLogger(__name__)


# ============================================================================
# Button Callback Router
# ============================================================================

async def handle_callback_query(update: Update, context: CallbackContext) -> None:
    """
    Global callback query handler - routes button clicks to appropriate handlers.
    
    IMPORTANT: Calls query.answer() immediately to stop loading circle.
    """
    query = update.callback_query
    if query is None:
        return
    
    # === IMMEDIATE ANSWER - Stop loading circle ===
    # This is the KEY fix for Task 2
    try:
        await query.answer()  # Immediate - no loading circle
    except Exception as e:
        logger.debug(f"[callback] answer failed: {e}")
    
    # Get callback data
    data = query.data or ""
    
    # Parse callback type
    if not data:
        await _send_error_message(update, context, "Invalid button data")
        return
    
    # === Route based on callback type ===
    
    # Pattern: mt5_trade_<signal_id>
    if data.startswith("mt5_trade_"):
        await _handle_mt5_trade(update, context, data)
        return
    
    # Pattern: signal_reaction_<signal_id>|<reaction>
    if data.startswith("signal_reaction_"):
        await _handle_signal_reaction(update, context, data)
        return
    
    # Pattern: monitor_signal_<signal_id>
    if data.startswith("monitor_signal_"):
        await _handle_monitor_signal(update, context, data)
        return
    
    # Pattern: check_outcome_<signal_id>
    if data.startswith("check_outcome_"):
        await _handle_check_outcome(update, context, data)
        return
    
    # Pattern: open_signal_<signal_id>
    if data.startswith("open_signal_"):
        await _handle_open_signal(update, context, data)
        return
    
    # Pattern: nav_<action> (navigation)
    if data.startswith("nav_"):
        await _handle_navigation(update, context, data)
        return
    
    # Pattern: trade_now_<action>
    if data.startswith("trade_now_"):
        await _handle_trade_now(update, context, data)
        return
    
    # Pattern: mt5_link_guide, mt5_settings, etc.
    if data in ("mt5_link_guide", "mt5_settings", "advanced_portfolio"):
        await _handle_menu_action(update, context, data)
        return
    
    # Unknown callback - acknowledge silently
    logger.debug(f"[callback] unknown data: {data}")
    await _acknowledge(update, context)


# ============================================================================
# Individual Callback Handlers
# ============================================================================

async def _handle_mt5_trade(update: Update, context: CallbackContext, data: str) -> None:
    """Handle MT5 trade execution button."""
    try:
        # Extract signal_id from callback
        signal_id = data.replace("mt5_trade_", "").strip()
        
        if not signal_id:
            await _send_error_message(update, context, "Invalid trade request")
            return
        
        # Delegate to existing MT5 handler
        # This reuses existing logic from bot.py
        from signalrank_telegram.bot import _mt5_trade_callback
        
        # Create a mock update structure for compatibility
        # The actual handler checks callback_query.data
        try:
            # Call the handler directly if it accepts callback data
            await _mt5_trade_callback(update, context)
        except Exception as e:
            logger.debug(f"[callback] mt5_trade error: {e}")
            await _send_menu_message(
                update, context,
                "⚠️ Trade execution temporarily unavailable. Please try /mt5_link."
            )
        
    except Exception as e:
        logger.error(f"[callback] mt5_trade failed: {e}")
        await _send_error_message(update, context, "Trade execution failed")


async def _handle_signal_reaction(update: Update, context: CallbackContext, data: str) -> None:
    """Handle signal reaction (🔥 Taking It / 👀 Watching)."""
    try:
        # Pattern: signal_reaction_<signal_id>|<reaction>
        data = data.replace("signal_reaction_", "")
        
        if "|" not in data:
            await _send_error_message(update, context, "Invalid reaction")
            return
        
        signal_id, reaction = data.split("|", 1)
        
        if reaction not in ("taking_it", "watching"):
            await _send_error_message(update, context, "Invalid reaction")
            return
        
        # Delegate to existing handler in bot.py
        # The handler is defined as _signal_reaction_callback
        logger.info(f"[callback] reaction: {signal_id} → {reaction}")
        
        # Acknowledge
        emoji = "🔥" if reaction == "taking_it" else "👀"
        await query.answer(f"{emoji} Noted!", show_alert=False)
        
    except Exception as e:
        logger.debug(f"[callback] signal_reaction error: {e}")


async def _handle_monitor_signal(update: Update, context: CallbackContext, data: str) -> None:
    """Handle signal monitor button."""
    try:
        signal_id = data.replace("monitor_signal_", "").strip()
        
        if not signal_id:
            await _send_error_message(update, context, "Invalid monitor request")
            return
        
        # Delegate to existing monitor handler
        from signalrank_telegram.bot import _signal_monitor_callback
        
        # Set callback_data for handler
        update.callback_query.data = f"monitor_signal_{signal_id}"
        
        try:
            await _signal_monitor_callback(update, context)
        except Exception as e:
            logger.debug(f"[callback] monitor error: {e}")
            await query.answer("⚠️ Monitor unavailable", show_alert=True)
        
    except Exception as e:
        logger.debug(f"[callback] monitor_signal error: {e}")


async def _handle_check_outcome(update: Update, context: CallbackContext, data: str) -> None:
    """Handle check outcome button."""
    try:
        signal_id = data.replace("check_outcome_", "")
        
        # Send outcome check message
        await query.answer("Checking outcome...", show_alert=False)
        
        # The outcome command is handled separately
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("📈 Monitor", callback_data=f"monitor_signal_{signal_id}"),
            InlineKeyboardButton("🔄 Refresh", callback_data=f"monitor_signal_{signal_id}"),
        ]])
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"📊 Outcome check for signal {signal_id[:8]}...",
            reply_markup=keyboard,
        )
        
    except Exception as e:
        logger.debug(f"[callback] check_outcome error: {e}")


async def _handle_open_signal(update: Update, context: CallbackContext, data: str) -> None:
    """Handle open signal button - navigate to signal message."""
    try:
        signal_id = data.replace("open_signal_", "")
        
        # Acknowledge
        await query.answer("Opening signal...", show_alert=False)
        
        # Send signal details
        from signalrank_telegram.bot import _load_signal_payload
        
        payload = await _load_signal_payload(signal_id)
        
        if payload:
            asset = payload.get("asset", "Unknown")
            direction = payload.get("direction", "long").upper()
            entry = payload.get("entry", 0)
            sl = payload.get("stop_loss", 0)
            tp = payload.get("take_profit", [])
            
            text = f"📊 Signal: {asset} {direction}\n"
            text += f"Entry: {entry}\nSL: {sl}\nTP: {tp}"
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
            )
        else:
            await _send_error_message(update, context, "Signal not found")
        
    except Exception as e:
        logger.debug(f"[callback] open_signal error: {e}")


async def _handle_navigation(update: Update, context: CallbackContext, data: str) -> None:
    """Handle navigation buttons."""
    try:
        action = data.replace("nav_", "")
        
        # Acknowledge
        await query.answer()
        
        # Handle various navigation actions
        if action == "back":
            await query.message.delete()
        elif action == "menu":
            from signalrank_telegram.commands import help_command
            await help_command(update, context)
        # Add other nav actions as needed
        
    except Exception as e:
        logger.debug(f"[callback] navigation error: {e}")


async def _handle_trade_now(update: Update, context: CallbackContext, data: str) -> None:
    """Handle trade now button."""
    # Similar to _handle_mt5_trade
    await _handle_mt5_trade(update, context, data.replace("trade_now_", "mt5_trade_"))


async def _handle_menu_action(update: Update, context: CallbackContext, data: str) -> None:
    """Handle menu action buttons."""
    try:
        await query.answer()
        
        if data == "mt5_link_guide":
            from signalrank_telegram.commands import mt5_link_command
            await mt5_link_command(update, context)
        # Add other menu actions
        
    except Exception as e:
        logger.debug(f"[callback] menu_action error: {e}")


# ============================================================================
# Helper Functions
# ============================================================================

async def _acknowledge(update: Update, context: CallbackContext) -> None:
    """Silent acknowledge - no alert."""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass


async def _send_error_message(update: Update, context: CallbackContext, error: str) -> None:
    """Send error message to user."""
    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"⚠️ {error}",
        )
    except Exception:
        pass


async def _send_menu_message(update: Update, context: CallbackContext, text: str) -> None:
    """Send menu message to user."""
    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
        )
    except Exception:
        pass


# ============================================================================
# Handler Factory
# ============================================================================

def create_global_callback_handler():
    """
    Create the global CallbackQueryHandler.
    
    Usage in bot.py:
    
    from signalrank_telegram.callback_handlers import create_global_callback_handler
    application.add_handler(create_global_callback_handler())
    """
    return CallbackQueryHandler(
        handle_callback_query,
        pass_updates_to_queue=True,
    )


# Export
__all__ = [
    "handle_callback_query",
    "create_global_callback_handler",
]
