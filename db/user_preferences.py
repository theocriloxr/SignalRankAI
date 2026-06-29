"""
User Trading Preferences - Per-User Trading Configuration

This module provides:
- Trading mode selection (paper vs live)
- Execution preferences per user
- Position sizing preferences
- Notification preferences

Usage:
    from db.user_preferences import get_user_preferences, update_user_preferences
    
    # Get user's trading preferences
    prefs = await get_user_preferences(user_id)
    
    # Update preferences
    await update_user_preferences(user_id, {"trading_mode": "live", "auto_execute": True})
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger("UserPreferences")

# Trading modes
TRADING_MODE_PAPER = "paper"
TRADING_MODE_LIVE = "live"
TRADING_MODE_BOTH = "both"

# Execution modes
EXEC_MODE_SIGNALS_ONLY = "signals_only"  # Just receive signals, manual execution
EXEC_MODE_AUTO = "auto"  # Auto-execute on broker
EXEC_MODE_SEMI_AUTO = "semi_auto"  # Signal + confirmation before execution


@dataclass
class UserTradingPreferences:
    """User's trading configuration."""
    user_id: int
    
    # Trading mode
    trading_mode: str = TRADING_MODE_PAPER  # paper, live, both
    
    # Execution preference
    execution_mode: str = EXEC_MODE_SIGNALS_ONLY  # signals_only, auto, semi_auto
    
    # Position sizing
    default_position_size: float = 0.01  # Default lot size
    risk_per_trade_pct: float = 1.0  # Risk % per trade
    
    # MT5 account (for live trading)
    default_mt5_account_id: Optional[str] = None
    
    # Notifications
    notify_on_entry: bool = True
    notify_on_exit: bool = True
    notify_on_tp: bool = True
    notify_on_sl: bool = True
    
    # Signal filters
    min_signal_score: float = 0.0  # 0 = no filter
    preferred_asset_class: Optional[str] = None  # crypto, forex, etc.
    preferred_timeframes: List[str] = None  # List of timeframes
    
    # Risk limits
    max_daily_trades: int = 10
    max_concurrent_positions: int = 3
    max_daily_loss_pct: float = 5.0
    
    # Paper trading
    paper_balance: float = 10000.0
    paper_reset_on_loss: bool = False  # Reset balance if below threshold
    
    # Updated timestamp
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.preferred_timeframes is None:
            self.preferred_timeframes = ["5m", "15m", "1h"]


class UserPreferencesManager:
    """
    Manage user's trading preferences.
    
    Allows users to configure how the bot helps them trade:
    - Paper vs Live trading mode
    - Auto-execute or signals only
    - Position sizing
    - Risk limits
    - Notifications
    """
    
    @staticmethod
    async def get_preferences(user_id: int) -> UserTradingPreferences:
        """
        Get user's trading preferences.
        
        Args:
            user_id: User ID
            
        Returns:
            UserTradingPreferences with defaults if not set
        """
        try:
            from db.session import get_session
            from db.models import RuntimeState
            from sqlalchemy import select
            
            async with get_session() as session:
                result = await session.execute(
                    select(RuntimeState).where(
                        RuntimeState.key == f"user_prefs:{user_id}"
                    )
                )
                state = result.first()
                if state:
                    data = state.value
                    return UserTradingPreferences(
                        user_id=user_id,
                        trading_mode=data.get("trading_mode", TRADING_MODE_PAPER),
                        execution_mode=data.get("execution_mode", EXEC_MODE_SIGNALS_ONLY),
                        default_position_size=data.get("default_position_size", 0.01),
                        risk_per_trade_pct=data.get("risk_per_trade_pct", 1.0),
                        default_mt5_account_id=data.get("default_mt5_account_id"),
                        notify_on_entry=data.get("notify_on_entry", True),
                        notify_on_exit=data.get("notify_on_exit", True),
                        notify_on_tp=data.get("notify_on_tp", True),
                        notify_on_sl=data.get("notify_on_sl", True),
                        min_signal_score=data.get("min_signal_score", 0.0),
                        preferred_asset_class=data.get("preferred_asset_class"),
                        preferred_timeframes=data.get("preferred_timeframes", ["5m", "15m", "1h"]),
                        max_daily_trades=data.get("max_daily_trades", 10),
                        max_concurrent_positions=data.get("max_concurrent_positions", 3),
                        max_daily_loss_pct=data.get("max_daily_loss_pct", 5.0),
                        paper_balance=data.get("paper_balance", 10000.0),
                        paper_reset_on_loss=data.get("paper_reset_on_loss", False),
                    )
        
        except Exception as e:
            logger.debug(f"[UserPreferences] Get prefs error: {e}")
        
        # Return defaults
        return UserTradingPreferences(user_id=user_id)
    
    @staticmethod
    async def update_preferences(
        user_id: int,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update user's trading preferences.
        
        Args:
            user_id: User ID
            updates: Dict of preferences to update
            
        Returns:
            True if successful
        """
        try:
            # Get existing preferences
            prefs = await UserPreferencesManager.get_preferences(user_id)
            
            # Apply updates
            prefs_dict = {
                "trading_mode": prefs.trading_mode,
                "execution_mode": prefs.execution_mode,
                "default_position_size": prefs.default_position_size,
                "risk_per_trade_pct": prefs.risk_per_trade_pct,
                "default_mt5_account_id": prefs.default_mt5_account_id,
                "notify_on_entry": prefs.notify_on_entry,
                "notify_on_exit": prefs.notify_on_exit,
                "notify_on_tp": prefs.notify_on_tp,
                "notify_on_sl": prefs.notify_on_sl,
                "min_signal_score": prefs.min_signal_score,
                "preferred_asset_class": prefs.preferred_asset_class,
                "preferred_timeframes": prefs.preferred_timeframes,
                "max_daily_trades": prefs.max_daily_trades,
                "max_concurrent_positions": prefs.max_concurrent_positions,
                "max_daily_loss_pct": prefs.max_daily_loss_pct,
                "paper_balance": prefs.paper_balance,
                "paper_reset_on_loss": prefs.paper_reset_on_loss,
            }
            
            # Merge updates
            prefs_dict.update(updates)
            prefs_dict["updated_at"] = datetime.utcnow().isoformat()
            
            # Save to DB
            from db.session import get_session
            from db.models import RuntimeState
            
            async with get_session() as session:
                state = RuntimeState(
                    key=f"user_prefs:{user_id}",
                    value=prefs_dict,
                )
                session.add(state)
                await session.commit()
            
            logger.info(f"[UserPreferences] Updated preferences for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"[UserPreferences] Update error: {e}")
            return False
    
    @staticmethod
    async def set_trading_mode(
        user_id: int,
        mode: str,
        mt5_account_id: Optional[str] = None
    ) -> bool:
        """
        Set user's trading mode.
        
        Args:
            user_id: User ID
            mode: TRADING_MODE_PAPER, TRADING_MODE_LIVE, or TRADING_MODE_BOTH
            mt5_account_id: Optional MT5 account for live trading
            
        Returns:
            True if successful
        """
        valid_modes = [TRADING_MODE_PAPER, TRADING_MODE_LIVE, TRADING_MODE_BOTH]
        if mode not in valid_modes:
            logger.warning(f"[UserPreferences] Invalid mode: {mode}")
            return False
        
        updates = {"trading_mode": mode}
        if mt5_account_id:
            updates["default_mt5_account_id"] = mt5_account_id
        
        return await UserPreferencesManager.update_preferences(user_id, updates)
    
    @staticmethod
    async def set_execution_mode(
        user_id: int,
        mode: str
    ) -> bool:
        """
        Set user's execution mode.
        
        Args:
            user_id: User ID
            mode: EXEC_MODE_SIGNALS_ONLY, EXEC_MODE_AUTO, EXEC_MODE_SEMI_AUTO
            
        Returns:
            True if successful
        """
        valid_modes = [EXEC_MODE_SIGNALS_ONLY, EXEC_MODE_AUTO, EXEC_MODE_SEMI_AUTO]
        if mode not in valid_modes:
            logger.warning(f"[UserPreferences] Invalid execution mode: {mode}")
            return False
        
        return await UserPreferencesManager.update_preferences(user_id, {"execution_mode": mode})
    
    @staticmethod
    async def get_trading_mode(user_id: int) -> str:
        """Get user's current trading mode."""
        prefs = await UserPreferencesManager.get_preferences(user_id)
        return prefs.trading_mode
    
    @staticmethod
    async def get_execution_mode(user_id: int) -> str:
        """Get user's execution mode."""
        prefs = await UserPreferencesManager.get_preferences(user_id)
        return prefs.execution_mode
    
    @staticmethod
    async def should_auto_execute(user_id: int) -> bool:
        """Check if user wants auto-execution."""
        prefs = await UserPreferencesManager.get_preferences(user_id)
        return prefs.execution_mode == EXEC_MODE_AUTO
    
    @staticmethod
    async def get_position_size(user_id: int) -> float:
        """Get user's preferred position size."""
        prefs = await UserPreferencesManager.get_preferences(user_id)
        return prefs.default_position_size
    
    @staticmethod
    async def reset_paper_balance(user_id: int) -> bool:
        """Reset user's paper balance to default."""
        return await UserPreferencesManager.update_preferences(
            user_id, 
            {"paper_balance": 10000.0}
        )


# Convenience functions
async def get_user_preferences(user_id: int) -> UserTradingPreferences:
    """Get user's trading preferences."""
    return await UserPreferencesManager.get_preferences(user_id)


async def update_user_preferences(
    user_id: int,
    updates: Dict[str, Any]
) -> bool:
    """Update user's preferences."""
    return await UserPreferencesManager.update_preferences(user_id, updates)


async def set_user_trading_mode(
    user_id: int,
    mode: str,
    mt5_account_id: Optional[str] = None
) -> bool:
    """Set user's trading mode."""
    return await UserPreferencesManager.set_trading_mode(user_id, mode, mt5_account_id)


async def set_user_execution_mode(user_id: int, mode: str) -> bool:
    """Set user's execution mode."""
    return await UserPreferencesManager.set_execution_mode(user_id, mode)


if __name__ == "__main__":
    # Quick test
    import asyncio
    
    async def test():
        print("Testing User Preferences...")
        
        # Get defaults
        prefs = await get_user_preferences(user_id=1)
        print(f"Defaults: trading_mode={prefs.trading_mode}, execution={prefs.execution_mode}")
        
        # Update
        await update_user_preferences(1, {"trading_mode": "live", "execution_mode": "auto"})
        
        # Get updated
        prefs = await get_user_preferences(1)
        print(f"Updated: trading_mode={prefs.trading_mode}, execution={prefs.execution_mode}")
    
    asyncio.run(test())
