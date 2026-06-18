"""
MT5 Signal Router - Route Signals to MT5 or Paper Trading

This module provides:
- Tier-gated signal routing (paid users only get MT5 execution)
- Paper trading for free users
- Trade sync back to paper ledger
- Multi-account support per user

Usage:
    from services.mt5_signal_router import route_signal
    
    # Route a signal to appropriate trading destination
    result = await route_signal(signal, user_id, tier)
"""

import logging
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime

logger = logging.getLogger("MT5SignalRouter")

# Default paper trading balance
DEFAULT_PAPER_BALANCE = 10000.0


class SignalRouter:
    """
    Routes signals to appropriate trading destination based on user tier.
    
    Flow:
    - VIP/Premium users with MT5 linked → MT5 execution
    - Premium/VIP users without MT5 → Paper trading
    - Free users → Paper trading only
    
    Supports multi-account per user, routing to default account unless
    specified otherwise.
    """
    
    def __init__(self):
        self._initialized = False
    
    async def initialize(self) -> bool:
        """Initialize the router."""
        if self._initialized:
            return True
        
        # Pre-import dependencies
        try:
            from services.mt5_client import (
                execute_trade,
                get_live_price,
                list_open_positions,
                get_user_mt5_account_id,
            )
            self._mt5_client_loaded = True
        except ImportError as e:
            logger.warning(f"[SignalRouter] MT5 client not available: {e}")
            self._mt5_client_loaded = False
        
        self._initialized = True
        return True
    
    async def route_signal(
        self,
        signal: Dict[str, Any],
        user_id: int,
        tier: str,
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Route a signal to the appropriate execution destination.
        
        Args:
            signal: Signal dict with asset, direction, entry, stop_loss, take_profit
            user_id: User ID
            tier: User tier (free, premium, vip, owner, admin)
            account_id: Optional specific MT5 account_id to use
            
        Returns:
            Dict with execution result including destination, status, and details
        """
        await self.initialize()
        
        result = {
            "success": False,
            "destination": "none",
            "signal_id": signal.get("signal_id"),
            "asset": signal.get("asset"),
            "direction": signal.get("direction"),
            "error": None,
            "execution": None,
            "position_id": None,
        }
        
        # Check tier for execution type
        tier = tier.lower() if tier else "free"
        
        # Determine execution path
        if tier in ("premium", "vip", "owner", "admin"):
            # Paid user - try MT5 first, fallback to paper
            mt5_result = await self._route_to_mt5(signal, user_id, account_id)
            
            if mt5_result.get("success"):
                result.update({
                    "success": True,
                    "destination": "mt5",
                    "execution": mt5_result,
                })
                return result
            elif mt5_result.get("error"):
                # MT5 failed but not critical - try paper as fallback
                paper_result = await self._route_to_paper(signal, user_id)
                result.update({
                    "success": paper_result.get("success", False),
                    "destination": "paper",
                    "execution": paper_result,
                    "error": f"MT5: {mt5_result.get('error')}, fallback: {paper_result.get('error')}",
                })
                return result
            else:
                # MT5 not configured - use paper
                paper_result = await self._route_to_paper(signal, user_id)
                result.update({
                    "success": paper_result.get("success", False),
                    "destination": "paper",
                    "execution": paper_result,
                })
                return result
        else:
            # Free user - paper only
            paper_result = await self._route_to_paper(signal, user_id)
            result.update({
                "success": paper_result.get("success", False),
                "destination": "paper",
                "execution": paper_result,
            })
            return result
    
    async def _route_to_mt5(
        self,
        signal: Dict[str, Any],
        user_id: int,
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Route signal to MT5 for execution."""
        result = {
            "success": False,
            "error": None,
            "order_id": None,
            "position_id": None,
        }
        
        if not self._mt5_client_loaded:
            result["error"] = "MT5 client not configured"
            return result
        
        try:
            from services.mt5_client import execute_trade, get_user_mt5_account_id
            
            # Get user's MetaApi account ID
            from db.repository import get_or_create_user
            from db.session import get_session
            
            telegram_user_id = None
            async with get_session() as session:
                user = await get_or_create_user(session, user_id=user_id)
                if user:
                    telegram_user_id = user.telegram_user_id
            
            if not telegram_user_id:
                result["error"] = "User not found"
                return result
            
            # Get MetaApi account ID
            if not account_id:
                account_id = await get_user_mt5_account_id(telegram_user_id)
            
            if not account_id:
                result["error"] = "No MT5 account linked"
                return result
            
            # Execute trade via MetaApi
            symbol = self._normalize_symbol(signal.get("asset", ""))
            direction = signal.get("direction", "long")
            volume = signal.get("position_size", 0.01)
            stop_loss = float(signal.get("stop_loss") or 0)
            take_profit = signal.get("take_profit")
            if isinstance(take_profit, list):
                take_profit = take_profit[0] if take_profit else 0
            entry = signal.get("entry", 0)
            
            trade_result = await execute_trade(
                account_id=account_id,
                symbol=symbol,
                direction=direction,
                volume=float(volume),
                stop_loss=stop_loss,
                take_profit=float(take_profit or 0),
                signal_entry=float(entry),
                comment=f"SignalRank:{signal.get('signal_id', '')}"
            )
            
            if trade_result.get("success"):
                result["success"] = True
                result["order_id"] = trade_result.get("order_id")
                result["position_id"] = trade_result.get("order_id")
                
                # Log execution
                await self._log_mt5_execution(
                    account_id=account_id,
                    user_id=user_id,
                    signal=signal,
                    order_id=trade_result.get("order_id"),
                    status="filled" if trade_result.get("success") else "rejected",
                )
            else:
                result["error"] = trade_result.get("error", "Trade failed")
            
            return result
            
        except Exception as e:
            logger.error(f"[SignalRouter] MT5 execution error: {e}")
            result["error"] = str(e)
            return result
    
    async def _route_to_paper(
        self,
        signal: Dict[str, Any],
        user_id: int
    ) -> Dict[str, Any]:
        """Route signal to paper trading."""
        result = {
            "success": False,
            "error": None,
            "position_id": None,
        }
        
        try:
            from core.paper_ledger import get_paper_ledger
            
            # Get paper ledger
            ledger = get_paper_ledger()
            
            # Open paper position
            position = await ledger.open_position(
                user_id=user_id,
                signal=signal,
                size=signal.get("position_size"),
                risk_pct=signal.get("risk_pct", 1.0)
            )
            
            if position:
                result["success"] = True
                result["position_id"] = position.position_id
            else:
                result["error"] = "Failed to open paper position"
            
            return result
            
        except Exception as e:
            logger.error(f"[SignalRouter] Paper execution error: {e}")
            result["error"] = str(e)
            return result
    
    async def _log_mt5_execution(
        self,
        account_id: str,
        user_id: int,
        signal: Dict[str, Any],
        order_id: Optional[str],
        status: str
    ) -> None:
        """Log MT5 execution for audit."""
        try:
            from db.mt5_models import log_execution
            
            await log_execution(
                account_id=account_id,
                user_id=user_id,
                symbol=signal.get("asset", ""),
                direction=signal.get("direction", "long"),
                volume=signal.get("position_size", 0.01),
                entry_price=signal.get("entry", 0),
                stop_loss=signal.get("stop_loss", 0),
                take_profit=str(signal.get("take_profit", "")),
                signal_id=signal.get("signal_id"),
                order_id=order_id,
                status=status,
            )
        except Exception as e:
            logger.error(f"[SignalRouter] Failed to log execution: {e}")
    
    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol for MT5/MetaApi."""
        symbol = symbol.upper().replace("/", "")
        
        # Handle common conversions
        conversions = {
            "BTCUSDT": "BTCUSD",
            "ETHUSDT": "ETHUSD",
            "XAUUSD": "GOLD",
            "XAGUSD": "SILVER",
        }
        
        return conversions.get(symbol, symbol)
    
    async def get_positions(
        self,
        user_id: int,
        destination: str = "all"
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get open positions from MT5 and/or paper."""
        positions = {
            "mt5": [],
            "paper": [],
        }
        
        try:
            # Get MT5 positions
            if destination in ("all", "mt5"):
                from services.mt5_client import list_open_positions, get_user_mt5_account_id
                from db.repository import get_or_create_user
                from db.session import get_session
                
                telegram_user_id = None
                async with get_session() as session:
                    user = await get_or_create_user(session, user_id=user_id)
                    if user:
                        telegram_user_id = user.telegram_user_id
                
                if telegram_user_id:
                    account_id = await get_user_mt5_account_id(telegram_user_id)
                    if account_id:
                        mt5_positions = await list_open_positions(account_id)
                        positions["mt5"] = mt5_positions
            
            # Get paper positions
            if destination in ("all", "paper"):
                from core.paper_ledger import get_paper_ledger
                
                ledger = get_paper_ledger()
                paper_positions = await ledger.get_open_positions(user_id)
                positions["paper"] = [p.to_dict() for p in paper_positions]
        
        except Exception as e:
            logger.error(f"[SignalRouter] Get positions error: {e}")
        
        return positions
    
    async def close_position(
        self,
        user_id: int,
        position_id: str,
        destination: str,
        reason: str = "manual"
    ) -> Dict[str, Any]:
        """Close a position."""
        result = {
            "success": False,
            "error": None,
        }
        
        try:
            if destination == "mt5":
                from services.mt5_client import close_position as mt5_close
                
                # Need to get account_id first
                from services.mt5_client import get_user_mt5_account_id
                from db.repository import get_or_create_user
                from db.session import get_session
                
                telegram_user_id = None
                async with get_session() as session:
                    user = await get_or_create_user(session, user_id=user_id)
                    if user:
                        telegram_user_id = user.telegram_user_id
                
                if telegram_user_id:
                    account_id = await get_user_mt5_account_id(telegram_user_id)
                    if account_id:
                        close_result = await mt5_close(account_id, position_id, comment=f"SignalRank:{reason}")
                        result["success"] = close_result.get("success", False)
                        result["error"] = close_result.get("error")
            
            elif destination == "paper":
                from core.paper_ledger import get_paper_ledger
                
                ledger = get_paper_ledger()
                
                # Get current price (would need to fetch)
                from data.get_live_price import get_price
                
                asset = position_id.split("_")[1] if "_" in position_id else "UNKNOWN"
                current_price = await get_price(asset) or 0
                
                close_result = await ledger.close_position(
                    user_id=user_id,
                    position_id=position_id,
                    exit_reason=reason.upper(),
                    exit_price=current_price
                )
                
                result["success"] = close_result is not None
                result["error"] = None if close_result else "Close failed"
        
        except Exception as e:
            logger.error(f"[SignalRouter] Close position error: {e}")
            result["error"] = str(e)
        
        return result


# Global router instance
_signal_router: Optional[SignalRouter] = None


def get_signal_router() -> SignalRouter:
    """Get or create the global signal router."""
    global _signal_router
    if _signal_router is None:
        _signal_router = SignalRouter()
    return _signal_router


async def route_signal(
    signal: Dict[str, Any],
    user_id: int,
    tier: str,
    account_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convenience function to route a signal.
    
    Args:
        signal: Signal dict
        user_id: User ID
        tier: User tier
        account_id: Optional MT5 account ID
        
    Returns:
        Execution result dict
    """
    router = get_signal_router()
    return await router.route_signal(signal, user_id, tier, account_id)


async def get_user_positions(
    user_id: int,
    destination: str = "all"
) -> Dict[str, List[Dict[str, Any]]]:
    """Get user's open positions."""
    router = get_signal_router()
    return await router.get_positions(user_id, destination)


async def close_user_position(
    user_id: int,
    position_id: str,
    destination: str,
    reason: str = "manual"
) -> Dict[str, Any]:
    """Close user's position."""
    router = get_signal_router()
    return await router.close_position(user_id, position_id, destination, reason)


if __name__ == "__main__":
    # Quick test
    import asyncio
    
    async def test():
        print("Testing Signal Router...")
        
        # Test with mock signal
        test_signal = {
            "signal_id": "test_123",
            "asset": "BTCUSDT",
            "direction": "long",
            "entry": 45000,
            "stop_loss": 44000,
            "take_profit": 48000,
            "position_size": 0.01,
        }
        
        # Test routing for different tiers
        for tier in ["free", "premium", "vip"]:
            result = await route_signal(test_signal, user_id=1, tier=tier)
            print(f"  {tier}: {result.get('destination')} - {result.get('success')}")
    
    asyncio.run(test())
