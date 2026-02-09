"""
Active signal monitoring module.
Monitors unresolved signals and notifies users when SL/TP targets are hit.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from engine.price_validator import get_current_price, check_sl_tp_hit

logger = logging.getLogger(__name__)


class SignalMonitor:
    """Monitor active signals for SL/TP hits and notify users."""
    
    def __init__(self):
        self.check_interval = 30  # Check every 30 seconds
        self.running = False
        self._task = None
    
    async def start(self):
        """Start the monitoring loop."""
        if self.running:
            logger.warning("Signal monitor already running")
            return
        
        self.running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Signal monitor started")
    
    async def stop(self):
        """Stop the monitoring loop."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Signal monitor stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop."""
        news_check_counter = 0  # Check news every 10th iteration (5 minutes)
        
        while self.running:
            try:
                await self.check_active_signals()
                
                # Check news impact periodically (every 5 minutes)
                news_check_counter += 1
                if news_check_counter >= 10:
                    news_check_counter = 0
                    try:
                        from data.news import check_news_impact_on_active_signals
                        await check_news_impact_on_active_signals()
                    except Exception as e:
                        logger.error(f"Error checking news impact: {e}")
            
            except Exception as e:
                logger.error(f"Error in signal monitor loop: {e}", exc_info=True)
            
            await asyncio.sleep(self.check_interval)
    
    async def check_active_signals(self):
        """Check all active signals against current prices."""
        try:
            # Get active signals from database
            active_signals = await self._get_active_signals()
            
            if not active_signals:
                logger.debug("No active signals to monitor")
                return
            
            logger.info(f"Monitoring {len(active_signals)} active signals")
            
            for signal in active_signals:
                try:
                    await self._check_signal(signal)
                except Exception as e:
                    logger.error(f"Error checking signal {signal.get('signal_id')}: {e}")
        
        except Exception as e:
            logger.error(f"Error fetching active signals: {e}", exc_info=True)
    
    async def _get_active_signals(self) -> List[Dict]:
        """Fetch active (unresolved) signals from database."""
        try:
            from db.session import get_session
            from db.models import Signal
            from sqlalchemy import select
            from core.tier_constants import ACTIVE_SIGNAL_LOOKBACK_HOURS
            
            async with get_session() as session:
                # Get signals created in last N hours that are not archived
                cutoff = datetime.utcnow() - timedelta(hours=ACTIVE_SIGNAL_LOOKBACK_HOURS)
                stmt = select(Signal).where(
                    Signal.archived == False,
                    Signal.created_at >= cutoff
                )
                result = await session.execute(stmt)
                signals = result.scalars().all()
                
                # Convert to dict format
                return [
                    {
                        'signal_id': s.signal_id,
                        'asset': s.asset,
                        'direction': s.direction,
                        'entry': s.entry,
                        'stop_loss': s.stop_loss,
                        'take_profit': s.take_profit,
                        'created_at': s.created_at,
                        'timeframe': s.timeframe,
                        'score': s.score
                    }
                    for s in signals
                ]
        except Exception as e:
            logger.error(f"Error fetching active signals from DB: {e}")
            return []
    
    async def _check_signal(self, signal: Dict):
        """Check a single signal against current price."""
        asset = signal.get('asset')
        signal_id = signal.get('signal_id')
        
        # Get current price
        current_price = get_current_price(asset)
        if current_price is None:
            logger.debug(f"Could not fetch price for {asset}")
            return
        
        # Check if SL or TP hit
        should_notify, reason = check_sl_tp_hit(signal, current_price)
        
        if should_notify:
            logger.info(f"Signal {signal_id[:8]} hit target: {reason}")
            await self._notify_signal_outcome(signal, current_price, reason)
            await self._mark_signal_resolved(signal_id, reason)
    
    async def _notify_signal_outcome(self, signal: Dict, current_price: float, reason: str):
        """Notify users who received this signal about the outcome."""
        try:
            from signalrank_telegram.bot import send_message_to_user
            
            signal_id = signal.get('signal_id')
            asset = signal.get('asset')
            direction = signal.get('direction', '').upper()
            entry = signal.get('entry', 0)
            
            # Determine if it's a win or loss
            is_tp = 'take profit' in reason.lower()
            is_sl = 'stop loss' in reason.lower()
            
            if is_tp:
                outcome_emoji = "🎯✅"
                outcome_text = "TAKE PROFIT HIT"
            elif is_sl:
                outcome_emoji = "🛑❌"
                outcome_text = "STOP LOSS HIT"
            else:
                outcome_emoji = "ℹ️"
                outcome_text = "TARGET HIT"
            
            # Calculate P&L percentage
            if direction == 'LONG':
                pnl_pct = ((current_price - entry) / entry) * 100
            else:  # SHORT
                pnl_pct = ((entry - current_price) / entry) * 100
            
            pnl_sign = "+" if pnl_pct >= 0 else ""
            
            message = (
                f"{outcome_emoji} **{outcome_text}**\n\n"
                f"🪙 **{asset}** {direction}\n"
                f"📊 Ref: `{signal_id[:8]}`\n\n"
                f"💰 Entry: {entry:.4f}\n"
                f"📍 Current: {current_price:.4f}\n"
                f"📈 P&L: {pnl_sign}{pnl_pct:.2f}%\n\n"
                f"ℹ️ {reason}"
            )
            
            # Get users who received this signal
            user_ids = await self._get_signal_recipients(signal_id)
            
            for user_id in user_ids:
                try:
                    await send_message_to_user(user_id, message)
                    logger.info(f"Notified user {user_id} about signal {signal_id[:8]} outcome")
                except Exception as e:
                    logger.error(f"Failed to notify user {user_id}: {e}")
        
        except Exception as e:
            logger.error(f"Error notifying signal outcome: {e}", exc_info=True)
    
    async def _get_signal_recipients(self, signal_id: str) -> List[int]:
        """Get list of user IDs who received this signal."""
        try:
            from db.session import get_session
            from db.models import SignalDelivery
            from sqlalchemy import select
            
            async with get_session() as session:
                stmt = select(SignalDelivery.user_id).where(
                    SignalDelivery.signal_id == signal_id
                ).distinct()
                result = await session.execute(stmt)
                user_ids = [row[0] for row in result]
                return user_ids
        except Exception as e:
            logger.error(f"Error fetching signal recipients: {e}")
            return []
    
    async def _mark_signal_resolved(self, signal_id: str, reason: str):
        """Mark signal as resolved (archived) in database."""
        try:
            from db.session import get_session
            from db.models import Signal
            from sqlalchemy import select, update
            
            async with get_session() as session:
                stmt = update(Signal).where(
                    Signal.signal_id == signal_id
                ).values(archived=True)
                await session.execute(stmt)
                await session.commit()
                
                logger.info(f"Marked signal {signal_id[:8]} as resolved: {reason}")
        except Exception as e:
            logger.error(f"Error marking signal as resolved: {e}", exc_info=True)


# Global instance
signal_monitor = SignalMonitor()


async def start_signal_monitor():
    """Start the global signal monitor."""
    await signal_monitor.start()


async def stop_signal_monitor():
    """Stop the global signal monitor."""
    await signal_monitor.stop()
