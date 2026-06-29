"""
Trading Mode Manager - User Trading Mode Selection

This module provides:
- Trading mode selection (paper vs live vs both)
- User decides how bot helps them trade
- Seamless switching between modes
- Position sync across modes

Usage:
    from services.trading_mode_manager import TradingModeManager
    
    # Get user's trading mode
    mode = await TradingModeManager.get_mode(user_id)
    
    # Execute based on user's mode
    result = await TradingModeManager.execute_signal(signal, user_id)
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger("TradingModeManager")

# Trading modes
TRADING_MODE_PAPER = "paper"
TRADING_MODE_LIVE = "live"
TRADING_MODE_BOTH = "both"

# Execution modes
EXEC_MODE_SIGNALS_ONLY = "signals_only"
EXEC_MODE_AUTO = "auto"
EXEC_MODE_SEMI_AUTO = "semi_auto"
EXEC_MODE_COPY_TRADE = "copy_trade"
EXEC_MODE_MANUAL = "manual"


def _normalize_execution_mode(mode: str | None) -> str:
    normalized = str(mode or EXEC_MODE_SIGNALS_ONLY).strip().lower()
    aliases = {
        "none": EXEC_MODE_SIGNALS_ONLY,
        "manual": EXEC_MODE_MANUAL,
        "paper": EXEC_MODE_SEMI_AUTO,
        "copy": EXEC_MODE_COPY_TRADE,
    }
    return aliases.get(normalized, normalized)


class TradingModeManager:
    """
    Manage user's trading mode and execution.
    
    This is the main entry point for signal execution that respects
    user's trading preferences:
    - Paper: Signals sent to paper ledger
    - Live: Signals executed on MT5/broker
    - Both: User receives signals, can choose per-signal
    
    Flow:
    1. Get user's trading mode
    2. Get execution preference (signals_only, auto, semi_auto)
    3. Execute based on mode and preference
    """
    
    def __init__(self):
        pass
    
    async def get_mode(self, user_id: int) -> str:
        """Get user's current trading mode."""
        try:
            from db.user_preferences import get_user_preferences
            
            prefs = await get_user_preferences(user_id)
            return prefs.trading_mode
        except Exception as e:
            logger.debug(f"[TradingModeManager] Get mode error: {e}")
            return TRADING_MODE_PAPER
    
    async def get_execution_mode(self, user_id: int) -> str:
        """Get user's execution preference."""
        try:
            from db.user_preferences import get_user_preferences
            
            prefs = await get_user_preferences(user_id)
            return prefs.execution_mode
        except Exception as e:
            logger.debug(f"[TradingModeManager] Get exec mode error: {e}")
            return EXEC_MODE_SIGNALS_ONLY
    
    async def should_auto_execute(self, user_id: int) -> bool:
        """Check if user wants auto-execution."""
        exec_mode = _normalize_execution_mode(await self.get_execution_mode(user_id))
        return exec_mode == EXEC_MODE_AUTO
    
    async def execute_signal(
        self,
        signal: Dict[str, Any],
        user_id: int
    ) -> Dict[str, Any]:
        """
        Execute signal based on user's trading mode.
        
        Args:
            signal: Signal dict
            user_id: User ID
            
        Returns:
            Execution result with destination, status, position_id
        """
        # Get user's trading mode
        mode = await self.get_mode(user_id)
        exec_mode = _normalize_execution_mode(await self.get_execution_mode(user_id))
        
        result = {
            "success": False,
            "destination": "none",
            "mode": mode,
            "execution_mode": exec_mode,
            "signal_id": signal.get("signal_id"),
            "error": None,
            "position_id": None,
        }
        
        # Handle based on mode
        if exec_mode == EXEC_MODE_SIGNALS_ONLY:
            result["success"] = True
            result["destination"] = "signals"
            result["note"] = "Signal delivered only; execution disabled."
            return result

        if mode == TRADING_MODE_PAPER:
            result = await self._execute_paper(signal, user_id)
            result["mode"] = TRADING_MODE_PAPER
            result["execution_mode"] = exec_mode
            return result
            
        elif mode == TRADING_MODE_LIVE:
            result = await self._execute_live(signal, user_id, exec_mode)
            result["mode"] = TRADING_MODE_LIVE
            result["execution_mode"] = exec_mode
            return result
            
        elif mode == TRADING_MODE_BOTH:
            # For "both" mode, default to paper but allow user to choose
            # This is where semi_auto could ask for confirmation
            if exec_mode in {EXEC_MODE_SEMI_AUTO, EXEC_MODE_MANUAL}:
                # Need user confirmation
                result = await self._execute_paper(signal, user_id)
                result["note"] = "Mirrored to paper; use live AUTO/COPY mode for broker execution."
                return result
            elif exec_mode in {EXEC_MODE_AUTO, EXEC_MODE_COPY_TRADE}:
                # Auto - execute on live
                result = await self._execute_live(signal, user_id, exec_mode)
                result["note"] = "Auto/copy execution attempted on linked live account."
                return result
        
        result["error"] = f"Unknown mode: {mode}"
        return result
    
    async def _execute_paper(
        self,
        signal: Dict[str, Any],
        user_id: int
    ) -> Dict[str, Any]:
        """Execute on paper trading."""
        try:
            from core.paper_ledger import get_paper_ledger
            
            ledger = get_paper_ledger()
            
            position = await ledger.open_position(
                user_id=user_id,
                signal=signal,
                size=signal.get("position_size"),
                risk_pct=signal.get("risk_pct", 1.0)
            )
            
            if position:
                return {
                    "success": True,
                    "destination": "paper",
                    "position_id": position.position_id,
                    "balance": await ledger.get_balance(user_id),
                }
            else:
                return {
                    "success": False,
                    "destination": "paper",
                    "error": "Failed to open paper position",
                }
        except Exception as e:
            logger.error(f"[TradingModeManager] Paper execution error: {e}")
            return {
                "success": False,
                "destination": "paper",
                "error": str(e),
            }
    
    async def _execute_live(
        self,
        signal: Dict[str, Any],
        user_id: int,
        execution_mode: str = EXEC_MODE_MANUAL,
    ) -> Dict[str, Any]:
        """Execute on live MT5 account."""
        try:
            from services.mt5_signal_router import route_signal_to_mt5
            from services.subscription_manager import SubscriptionManager
            
            # Check if user has active subscription
            sub_status = await SubscriptionManager.get_status(user_id)
            tier = str(sub_status.get("tier", "free") or "free").strip().lower()
            
            # Only premium+ users can use live trading
            if tier not in ("premium", "vip", "owner", "admin"):
                return {
                    "success": False,
                    "destination": "mt5",
                    "error": "Live trading requires premium subscription",
                }
            
            # Get user's MT5 account
            from db.user_preferences import get_user_preferences
            
            prefs = await get_user_preferences(user_id)
            account_id = prefs.default_mt5_account_id
            if not account_id:
                return {
                    "success": False,
                    "destination": "mt5",
                    "error": "No MT5 account linked. Use /mt5_link or /connect_broker first.",
                }
            
            # Execute via MT5 router
            router_mode = "auto" if execution_mode in {EXEC_MODE_AUTO, EXEC_MODE_COPY_TRADE} else "manual"
            routed = await route_signal_to_mt5(signal, user_id, router_mode)
            if hasattr(routed, "__dict__"):
                return {
                    "success": bool(getattr(routed, "success", False)),
                    "destination": "mt5",
                    "message": getattr(routed, "message", ""),
                    "order_id": getattr(routed, "order_id", None),
                    "error": getattr(routed, "error", None),
                }
            return dict(routed or {})
            
        except Exception as e:
            logger.error(f"[TradingModeManager] Live execution error: {e}")
            return {
                "success": False,
                "destination": "mt5",
                "error": str(e),
            }
    
    async def switch_mode(
        self,
        user_id: int,
        new_mode: str,
        mt5_account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Switch user's trading mode.
        
        Args:
            user_id: User ID
            new_mode: New trading mode
            mt5_account_id: Optional MT5 account for live mode
            
        Returns:
            Result of mode switch
        """
        valid_modes = [TRADING_MODE_PAPER, TRADING_MODE_LIVE, TRADING_MODE_BOTH]
        
        if new_mode not in valid_modes:
            return {
                "success": False,
                "error": f"Invalid mode: {new_mode}",
            }
        
        # Check if switching to live - verify MT5 account
        if new_mode in [TRADING_MODE_LIVE, TRADING_MODE_BOTH]:
            if not mt5_account_id:
                # Try to get default
                from db.user_preferences import get_user_preferences
                prefs = await get_user_preferences(user_id)
                mt5_account_id = prefs.default_mt5_account_id
            
            if not mt5_account_id:
                return {
                    "success": False,
                    "error": "No MT5 account linked. Use /mt5_link first.",
                }
        
        # Update mode
        try:
            from db.user_preferences import update_user_preferences
            
            updates = {"trading_mode": new_mode}
            if mt5_account_id:
                updates["default_mt5_account_id"] = mt5_account_id
            
            await update_user_preferences(user_id, updates)
            
            logger.info(f"[TradingModeManager] User {user_id} switched to mode: {new_mode}")
            
            return {
                "success": True,
                "mode": new_mode,
                "message": f"Trading mode changed to {new_mode}",
            }
            
        except Exception as e:
            logger.error(f"[TradingModeManager] Switch mode error: {e}")
            return {
                "success": False,
                "error": str(e),
            }
    
    async def get_portfolio_summary(
        self,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Get portfolio summary across all modes.
        
        Returns:
            Dict with paper and live positions
        """
        summary = {
            "user_id": user_id,
            "mode": await self.get_mode(user_id),
            "execution_mode": await self.get_execution_mode(user_id),
            "paper": {
                "positions": [],
                "balance": 0,
                "open_count": 0,
            },
            "live": {
                "positions": [],
                "balance": 0,
                "open_count": 0,
            },
        }
        
        try:
            # Get paper positions
            from core.paper_ledger import get_paper_ledger
            
            ledger = get_paper_ledger()
            summary["paper"]["balance"] = await ledger.get_balance(user_id)
            paper_positions = await ledger.get_open_positions(user_id)
            summary["paper"]["positions"] = [p.to_dict() for p in paper_positions]
            summary["paper"]["open_count"] = len(paper_positions)
            
        except Exception as e:
            logger.debug(f"[TradingModeManager] Paper summary error: {e}")
        
        try:
            # Get live positions (if MT5 linked)
            from db.user_preferences import get_user_preferences
            
            prefs = await get_user_preferences(user_id)
            if prefs.default_mt5_account_id:
                from services.mt5_client import list_open_positions
                
                live_positions = await list_open_positions(prefs.default_mt5_account_id)
                summary["live"]["positions"] = live_positions
                summary["live"]["open_count"] = len(live_positions)
                
        except Exception as e:
            logger.debug(f"[TradingModeManager] Live summary error: {e}")
        
        return summary
    
    async def close_all_positions(
        self,
        user_id: int,
        mode: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Close all positions for user.
        
        Args:
            user_id: User ID
            mode: Optional mode to close (default: current mode)
        """
        result = {
            "closed": 0,
            "failed": 0,
            "errors": [],
        }
        
        target_mode = mode or await self.get_mode(user_id)
        
        if target_mode in [TRADING_MODE_PAPER, TRADING_MODE_BOTH]:
            try:
                from core.paper_ledger import get_paper_ledger
                
                ledger = get_paper_ledger()
                positions = await ledger.get_open_positions(user_id)
                
                from data.get_live_price import get_price
                
                for pos in positions:
                    try:
                        price = await get_price(pos.asset) or pos.entry_price
                        await ledger.close_position(
                            user_id=user_id,
                            position_id=pos.position_id,
                            exit_reason="CLOSE_ALL",
                            exit_price=price
                        )
                        result["closed"] += 1
                    except Exception as e:
                        result["failed"] += 1
                        result["errors"].append(str(e))
                        
            except Exception as e:
                logger.error(f"[TradingModeManager] Paper close error: {e}")
        
        if target_mode in [TRADING_MODE_LIVE, TRADING_MODE_BOTH]:
            try:
                from db.user_preferences import get_user_preferences
                
                prefs = await get_user_preferences(user_id)
                if prefs.default_mt5_account_id:
                    from services.mt5_client import close_all_positions
                    
                    close_result = await close_all_positions(
                        prefs.default_mt5_account_id,
                        comment="User close all"
                    )
                    result["closed"] += close_result.get("closed", 0)
                    result["failed"] += close_result.get("failed", 0)
                    
            except Exception as e:
                logger.error(f"[TradingModeManager] Live close error: {e}")
        
        return result


_trading_mode_manager: Optional[TradingModeManager] = None


def get_trading_mode_manager() -> TradingModeManager:
    """Get or create the trading mode manager."""
    global _trading_mode_manager
    if _trading_mode_manager is None:
        _trading_mode_manager = TradingModeManager()
    return _trading_mode_manager


async def get_user_trading_mode(user_id: int) -> str:
    """Get user's trading mode."""
    manager = get_trading_mode_manager()
    return await manager.get_mode(user_id)


async def execute_user_signal(
    signal: Dict[str, Any],
    user_id: int
) -> Dict[str, Any]:
    """Execute signal based on user's mode."""
    manager = get_trading_mode_manager()
    return await manager.execute_signal(signal, user_id)


async def switch_user_mode(
    user_id: int,
    mode: str,
    mt5_account_id: Optional[str] = None
) -> Dict[str, Any]:
    """Switch user's trading mode."""
    manager = get_trading_mode_manager()
    return await manager.switch_mode(user_id, mode, mt5_account_id)


async def get_user_portfolio(user_id: int) -> Dict[str, Any]:
    """Get user's portfolio summary."""
    manager = get_trading_mode_manager()
    return await manager.get_portfolio_summary(user_id)


if __name__ == "__main__":
    # Quick test
    import asyncio
    
    async def test():
        print("Testing Trading Mode Manager...")
        
        # Get mode
        mode = await get_user_trading_mode(user_id=1)
        print(f"Mode: {mode}")
        
        # Test signal execution
        test_signal = {
            "signal_id": "test_123",
            "asset": "BTCUSDT",
            "direction": "long",
            "entry": 45000,
            "stop_loss": 44000,
            "take_profit": 48000,
            "position_size": 0.01,
        }
        
        result = await execute_user_signal(test_signal, user_id=1)
        print(f"Result: {result}")
    
    asyncio.run(test())
