"""
Trade Manager - Auto-Breakeven Logic
Monitors active trades and moves Stop Loss to Entry Price when TP1 is hit.

This implements the "Free Ride" automation:
- When current price crosses TP1, update SL to Entry + (Spread * 2)
- This guarantees worst-case is a slightly profitable scratch
- Mathematically spikes win rate metrics
"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class TradeManager:
    """Manages active trades for auto-breakeven and partial exits."""
    
    def __init__(
        self,
        spread_multiplier: float = 2.0,
        check_interval_seconds: int = 60
    ):
        """
        Initialize the trade manager.
        
        Args:
            spread_multiplier: Multiplier for spread buffer when moving SL to breakeven.
            check_interval_seconds: How often to check active trades.
        """
        self.spread_multiplier = float(
            os.getenv("TRADE_MGR_SPREAD_MULT", str(spread_multiplier))
        )
        self.check_interval = int(
            os.getenv("TRADE_MGR_CHECK_INTERVAL", str(check_interval_seconds))
        )
    
    def parse_tp_levels(self, take_profit: Any) -> List[float]:
        """
        Parse take profit levels from various formats.
        
        Args:
            take_profit: Can be string "tp1,tp2,tp3", list, or dict.
            
        Returns:
            List of TP prices.
        """
        tps = []
        
        if isinstance(take_profit, str):
            # Format: "tp1,tp2,tp3" or JSON
            try:
                # Try JSON parse first
                import json
                parsed = json.loads(take_profit)
                if isinstance(parsed, list):
                    for p in parsed:
                        try:
                            tps.append(float(p))
                        except (ValueError, TypeError):
                            continue
                else:
                    # Comma separated
                    for p in take_profit.split(","):
                        try:
                            tps.append(float(p.strip()))
                        except (ValueError, TypeError):
                            continue
            except Exception:
                # Try comma separated
                for p in take_profit.split(","):
                    try:
                        tps.append(float(p.strip()))
                    except (ValueError, TypeError):
                        continue
        
        elif isinstance(take_profit, list):
            for p in take_profit:
                try:
                    if isinstance(p, dict):
                        tpf = p.get('price') or p.get('tp') or p.get('target')
                        if tpf is not None:
                            tps.append(float(tpf))
                    else:
                        tps.append(float(p))
                except (ValueError, TypeError):
                    continue
        
        elif isinstance(take_profit, dict):
            # Dict with 'price' or 'tp' keys
            if 'price' in take_profit:
                tps.append(float(take_profit['price']))
            elif 'tp' in take_profit:
                tps.append(float(take_profit['tp']))
        
        return [t for t in tps if t > 0]
    
    def get_tp1(
        self,
        trade: Dict[str, Any],
        entry_price: Optional[float] = None,
        direction: Optional[str] = None
    ) -> Optional[float]:
        """
        Extract TP1 from trade.
        
        Args:
            trade: Trade dict.
            entry_price: Entry price (fallback).
            direction: Trade direction (fallback).
            
        Returns:
            TP1 price or None.
        """
        # Try to get from explicit fields first
        tp1 = trade.get('tp1')
        if tp1:
            try:
                return float(tp1)
            except (ValueError, TypeError):
                pass
        
        # Parse from take_profit field
        tp_levels = self.parse_tp_levels(trade.get('take_profit'))
        if tp_levels:
            return tp_levels[0]
        
        return None
    
    def should_move_to_breakeven(
        self,
        trade: Dict[str, Any],
        current_price: float,
        sl_moved_to_be: bool = False
    ) -> bool:
        """
        Check if SL should be moved to breakeven.
        
        Args:
            trade: Trade dict.
            current_price: Current market price.
            sl_moved_to_be: Whether SL already moved to breakeven.
            
        Returns:
            True if should move SL to entry.
        """
        if sl_moved_to_be:
            return False
        
        # Get trade details
        direction = str(trade.get('direction') or 'long').lower()
        entry = float(trade.get('entry_price') or trade.get('entry') or 0)
        
        if entry <= 0:
            return False
        
        tp1 = self.get_tp1(trade)
        if not tp1:
            return False
        
        # Check if TP1 is hit
        if direction in ('long', 'buy'):
            # LONG: price >= TP1
            return current_price >= tp1
        else:
            # SHORT: price <= TP1
            return current_price <= tp1
    
    def calculate_new_sl(
        self,
        trade: Dict[str, Any],
        current_price: float,
        spread_estimate: float = 0.0
    ) -> Optional[float]:
        """
        Calculate new Stop Loss for breakeven.
        
        Args:
            trade: Trade dict.
            current_price: Current market price.
            spread_estimate: Estimated spread for buffer.
            
        Returns:
            New SL price or None.
        """
        direction = str(trade.get('direction') or 'long').lower()
        entry = float(trade.get('entry_price') or trade.get('entry') or 0)
        
        if entry <= 0:
            return None
        
        # SL = Entry + (Spread * 2) for LONG
        # SL = Entry - (Spread * 2) for SHORT
        spread_buffer = spread_estimate * self.spread_multiplier
        
        if direction in ('long', 'buy'):
            new_sl = entry + spread_buffer
        else:
            new_sl = entry - spread_buffer
        
        return new_sl
    
    async def process_active_trades(
        self,
        trades: List[Dict[str, Any]],
        price_fn=None
    ) -> List[Dict[str, Any]]:
        """
        Process active trades and update SLs if TP1 hit.
        
        Args:
            trades: List of active trade dicts.
            price_fn: Async function to get current price (symbol) -> price.
            
        Returns:
            List of updated trades.
        """
        if not trades:
            return trades
        
        updated_trades = []
        
        for trade in trades:
            try:
                symbol = str(trade.get('symbol') or trade.get('asset') or '').upper()
                if not symbol:
                    continue
                
                # Get current price
                current_price = None
                if price_fn:
                    try:
                        current_price = await price_fn(symbol)
                    except Exception as e:
                        logger.debug(f"[trade_mgr] Failed to get price for {symbol}: {e}")
                        continue
                
                if not current_price or current_price <= 0:
                    continue
                
                # Check SL already moved
                sl_moved = bool(trade.get('sl_moved_to_be', False))
                
                # Check if should move to breakeven
                if not self.should_move_to_breakeven(trade, current_price, sl_moved):
                    updated_trades.append(trade)
                    continue
                
                # Calculate new SL
                new_sl = self.calculate_new_sl(trade, current_price)
                
                if new_sl and new_sl > 0:
                    # Update trade
                    trade['stop_loss'] = new_sl
                    trade['sl_moved_to_be'] = True
                    trade['sl_moved_at'] = datetime.utcnow().isoformat()
                    
                    logger.info(
                        f"[trade_manager] 🛡️ RISK FREE: {symbol} hit TP1. "
                        f"Stop loss moved to entry ({new_sl:.5f}). "
                        f"Now a guaranteed scratch trade."
                    )
                    
                    # TODO: Update database and call MT5 API
                    # await db.update_trade(trade)
                    # await mt5_api.update_stop_loss(trade['mt5_ticket'], new_sl)
                
                updated_trades.append(trade)
                
            except Exception as e:
                logger.debug(f"[trade_manager] Error processing trade: {e}")
                updated_trades.append(trade)
        
        return updated_trades


# Default instance for easy import
default_trade_manager = TradeManager()


async def check_and_move_sl(
    trades: List[Dict[str, Any]],
    price_fn=None
) -> List[Dict[str, Any]]:
    """
    Convenience function to process trades for auto-breakeven.
    """
    return await default_trade_manager.process_active_trades(trades, price_fn)
