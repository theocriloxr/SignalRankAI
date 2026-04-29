"""Signal validation and correction system."""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def validate_signal(signal: dict) -> tuple[bool, Optional[str]]:
    """
    Validate a signal for correctness.
    
    Returns:
        (is_valid, error_description)
    """
    try:
        # Check required fields
        required_fields = ["asset", "direction", "entry", "stop_loss", "take_profit"]
        for field in required_fields:
            if field not in signal or signal[field] is None:
                return False, f"Missing required field: {field}"
        
        # Validate direction
        direction = str(signal.get("direction", "")).lower()
        if direction not in ["long", "short"]:
            return False, f"Invalid direction: {direction}"
        
        # Get price levels
        try:
            entry = float(signal["entry"])
            stop_loss = float(signal["stop_loss"])
            
            # Parse take_profit (could be list or single value)
            tp_raw = signal["take_profit"]
            if isinstance(tp_raw, list):
                if len(tp_raw) == 0:
                    return False, "Empty take_profit list"
                take_profit = float(tp_raw[0])
            else:
                take_profit = float(tp_raw)
        except (ValueError, TypeError) as e:
            return False, f"Invalid numeric values: {e}"
        
        # Validate price levels are positive
        if entry <= 0 or stop_loss <= 0 or take_profit <= 0:
            return False, "Entry, SL, and TP must be positive"
        
        # Validate price relationship for LONG
        if direction == "long":
            if entry <= stop_loss:
                return False, f"LONG: Entry ({entry}) must be above SL ({stop_loss})"
            if take_profit <= entry:
                return False, f"LONG: TP ({take_profit}) must be above Entry ({entry})"
        
        # Validate price relationship for SHORT
        elif direction == "short":
            if entry >= stop_loss:
                return False, f"SHORT: Entry ({entry}) must be below SL ({stop_loss})"
            if take_profit >= entry:
                return False, f"SHORT: TP ({take_profit}) must be below Entry ({entry})"
        
        # Validate RR ratio (should be at least 1.0)
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        
        if risk <= 0:
            return False, "Risk (entry-SL distance) must be positive"
        
        rr_ratio = reward / risk
        if rr_ratio < 1.5:
            return False, f"Poor RR ratio: {rr_ratio:.2f} (minimum 1.5)"
        
        # Check for extremely wide SL (>20% for crypto, >10% for stocks)
        sl_pct = (risk / entry) * 100.0
        asset = str(signal.get("asset", "")).upper()
        is_crypto = asset.endswith("USDT") or asset.endswith("USDC") or asset.endswith("BUSD")
        
        max_sl_pct = 8.0 if is_crypto else 5.0
        if sl_pct > max_sl_pct:
            return False, f"SL too wide: {sl_pct:.1f}% (max {max_sl_pct}% for { 'crypto' if is_crypto else 'traditional' } )"
        
        return True, None
        
    except Exception as e:
        logger.error(f"Signal validation error: {e}")
        return False, f"Validation exception: {e}"


async def create_signal_correction(
    session,
    original_signal_id: str,
    error_type: str,
    error_description: str,
    corrected_signal_id: Optional[str] = None
):
    """Create a signal correction record."""
    from db.models import SignalCorrection
    
    correction = SignalCorrection(
        original_signal_id=original_signal_id,
        corrected_signal_id=corrected_signal_id,
        error_type=error_type,
        error_description=error_description,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    
    session.add(correction)
    await session.flush()
    
    logger.info(f"Created correction for signal {original_signal_id}: {error_type}")
    return correction


async def notify_signal_correction(
    bot,
    original_signal_id: str,
    error_description: str,
    corrected_signal_id: Optional[str] = None
):
    """Notify all users who received the original signal about the correction."""
    from db.session import get_session
    from db.models import SignalDelivery, User
    from sqlalchemy import select
    
    correction_count = 0
    
    try:
        async with get_session() as session:
            # Get all users who received this signal
            query = select(SignalDelivery).where(
                SignalDelivery.signal_id == original_signal_id
            )
            result = await session.execute(query)
            deliveries = result.scalars().all()
            
            for delivery in deliveries:
                try:
                    # Get user
                    user_query = select(User).where(User.id == delivery.user_id)
                    user_result = await session.execute(user_query)
                    user = user_result.scalar_one_or_none()
                    
                    if user is None:
                        continue
                    
                    # Build correction message
                    msg_lines = [
                        "⚠️ SIGNAL CORRECTION",
                        "",
                        f"Reference: {original_signal_id[:8]}",
                        "",
                        f"Issue: {error_description}",
                    ]
                    
                    if corrected_signal_id:
                        msg_lines.extend([
                            "",
                            f"✅ Corrected signal sent: {corrected_signal_id[:8]}",
                            "Please use /signal command to view the corrected signal.",
                        ])
                    else:
                        msg_lines.extend([
                            "",
                            "❌ This signal has been invalidated.",
                            "Do not trade this signal. We apologize for the error.",
                        ])
                    
                    msg = "\n".join(msg_lines)
                    
                    # Send notification
                    await bot.send_message(
                        chat_id=user.telegram_user_id,
                        text=msg
                    )
                    
                    correction_count += 1
                    logger.info(f"Sent correction notification to user {user.telegram_user_id}")
                    
                except Exception as e:
                    logger.error(f"Failed to notify user {delivery.user_id}: {e}")
                    continue
            
            # Update the correction record
            from db.models import SignalCorrection
            corr_query = select(SignalCorrection).where(
                SignalCorrection.original_signal_id == original_signal_id
            ).order_by(SignalCorrection.created_at.desc()).limit(1)
            
            corr_result = await session.execute(corr_query)
            correction = corr_result.scalar_one_or_none()
            
            if correction:
                correction.users_notified = correction_count
                correction.correction_sent_at = datetime.now(timezone.utc).replace(tzinfo=None)
            
            await session.commit()
            
    except Exception as e:
        logger.error(f"Signal correction notification failed: {e}")
    
    return correction_count
