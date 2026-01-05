"""
Market Condition Monitor
- Periodic checks for NO TRADE alerts
- Broadcasts when market conditions are poor
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List

logger = logging.getLogger(__name__)


class MarketMonitor:
    """Monitor market conditions and send NO TRADE alerts."""
    
    def __init__(self):
        from engine.signal_context import SignalContext
        from engine.tier_notifications import TierNotificationManager
        
        self.signal_context = SignalContext()
        self.tier_notifier = TierNotificationManager()
        self.last_no_trade_alert = None
        self.check_interval_minutes = int(os.getenv('MARKET_CHECK_INTERVAL_MINUTES', '60'))
    
    async def get_current_market_conditions(self) -> Dict:
        """
        Get current market conditions for NO TRADE alert check.
        
        Returns dict with: volume_ratio, atr_percent, regime, adx, spread_pct
        """
        try:
            from data.market_data import fetch_market_data_cached
            
            # Check major crypto pairs for overall market health
            symbols = ['BTCUSDT', 'ETHUSDT']
            all_conditions = []
            
            for symbol in symbols:
                try:
                    data = await fetch_market_data_cached(symbol, ['1h'])
                    
                    if not data or '1h' not in data:
                        continue
                    
                    candles = data['1h'].get('candles', [])
                    if len(candles) < 20:
                        continue
                    
                    # Calculate volume ratio (current vs avg)
                    recent_volume = candles[-1].get('volume', 0)
                    avg_volume = sum(c.get('volume', 0) for c in candles[-20:]) / 20
                    volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1.0
                    
                    # Calculate ATR percentage
                    highs = [c['high'] for c in candles[-14:]]
                    lows = [c['low'] for c in candles[-14:]]
                    closes = [c['close'] for c in candles[-14:]]
                    
                    tr_values = []
                    for i in range(1, len(candles[-14:])):
                        tr = max(
                            highs[i] - lows[i],
                            abs(highs[i] - closes[i-1]),
                            abs(lows[i] - closes[i-1])
                        )
                        tr_values.append(tr)
                    
                    atr = sum(tr_values) / len(tr_values) if tr_values else 0
                    current_price = candles[-1]['close']
                    atr_percent = (atr / current_price * 100) if current_price > 0 else 0
                    
                    # Simple ADX approximation (for demo, would need full calculation)
                    # Using range as proxy: tight range = low ADX
                    recent_highs = [c['high'] for c in candles[-20:]]
                    recent_lows = [c['low'] for c in candles[-20:]]
                    price_range = max(recent_highs) - min(recent_lows)
                    range_pct = (price_range / min(recent_lows) * 100) if min(recent_lows) > 0 else 10
                    adx = min(50, range_pct * 3)  # Simple approximation
                    
                    # Detect regime
                    if range_pct < 5 and adx < 20:
                        regime = 'ranging'
                    elif atr_percent > 10:
                        regime = 'volatile'
                    else:
                        regime = 'trending'
                    
                    # Spread (assume 0.1% for crypto on major exchanges)
                    spread_pct = 0.1
                    
                    all_conditions.append({
                        'volume_ratio': volume_ratio,
                        'atr_percent': atr_percent,
                        'regime': regime,
                        'adx': adx,
                        'spread_pct': spread_pct
                    })
                    
                except Exception as e:
                    logger.debug(f"Error getting conditions for {symbol}: {e}")
                    continue
            
            # Average conditions across symbols
            if not all_conditions:
                return {
                    'volume_ratio': 1.0,
                    'atr_percent': 5.0,
                    'regime': 'unknown',
                    'adx': 25.0,
                    'spread_pct': 0.1
                }
            
            return {
                'volume_ratio': sum(c['volume_ratio'] for c in all_conditions) / len(all_conditions),
                'atr_percent': sum(c['atr_percent'] for c in all_conditions) / len(all_conditions),
                'regime': all_conditions[0]['regime'],  # Use first
                'adx': sum(c['adx'] for c in all_conditions) / len(all_conditions),
                'spread_pct': sum(c['spread_pct'] for c in all_conditions) / len(all_conditions)
            }
            
        except Exception as e:
            logger.error(f"Error getting market conditions: {e}")
            return {
                'volume_ratio': 1.0,
                'atr_percent': 5.0,
                'regime': 'unknown',
                'adx': 25.0,
                'spread_pct': 0.1
            }
    
    async def check_and_alert(self):
        """Check market conditions and send NO TRADE alert if needed."""
        try:
            # Get current conditions
            conditions = await self.get_current_market_conditions()
            
            # Check if alert should be sent
            should_alert, reasons = self.signal_context.should_send_no_trade_alert(
                conditions,
                self.last_no_trade_alert
            )
            
            if should_alert:
                # Get session
                session = self.signal_context.detect_trading_session()
                
                # Format alert
                msg = self.tier_notifier.format_no_trade_alert(reasons, session)
                
                # Broadcast to all active users
                await self.broadcast_to_active_users(msg)
                
                # Update last alert time
                self.last_no_trade_alert = datetime.utcnow()
                
                logger.info(f"[MarketMonitor] NO TRADE alert sent: {reasons}")
        
        except Exception as e:
            logger.error(f"[MarketMonitor] Error in check_and_alert: {e}")
    
    async def broadcast_to_active_users(self, message: str):
        """Broadcast NO TRADE alert to all active users."""
        try:
            from db.pg_features import list_all_user_telegram_ids
            from db.session import get_session
            from telegram import Bot
            
            # Get user IDs asynchronously (we're already in an async context)
            async with get_session() as session:
                user_ids = await list_all_user_telegram_ids(session)
            
            if not user_ids:
                return
            
            # Get telegram token
            token = os.getenv('TELEGRAM_TOKEN')
            if not token:
                logger.error("[MarketMonitor] No TELEGRAM_TOKEN found")
                return
            
            bot = Bot(token=token)
            
            # Send to all users (rate limited automatically by python-telegram-bot)
            sent_count = 0
            for user_id in user_ids:
                try:
                    await bot.send_message(chat_id=int(user_id), text=message)
                    sent_count += 1
                except Exception as e:
                    logger.debug(f"[MarketMonitor] Failed to send to {user_id}: {e}")
                    continue
            
            logger.info(f"[MarketMonitor] NO TRADE alert sent to {sent_count}/{len(user_ids)} users")
        
        except Exception as e:
            logger.error(f"[MarketMonitor] Error broadcasting: {e}")
    
    async def run_forever(self):
        """Run market monitor loop forever."""
        logger.info(f"[MarketMonitor] Starting (check every {self.check_interval_minutes}m)")
        
        while True:
            try:
                await self.check_and_alert()
            except Exception as e:
                logger.error(f"[MarketMonitor] Error in monitor loop: {e}")
            
            # Sleep until next check
            await asyncio.sleep(self.check_interval_minutes * 60)


# For integration with main.py
async def start_market_monitor():
    """Start the market monitor background task."""
    monitor = MarketMonitor()
    await monitor.run_forever()


if __name__ == '__main__':
    # For standalone testing
    asyncio.run(start_market_monitor())
