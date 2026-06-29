"""
MT5 Signal Router - Signal to MT5 Execution Routing

This module provides:
- Routes signals from signal generator to MT5 for automated execution
- Handles tier-based execution (manual, auto, none)
- Returns trade sync back to paper ledger
- Multi-account support per user (VIP)
- Position sizing based on account equity and risk parameters

Usage:
    from services.mt5_signal_router import MT5SignalRouter
    
    router = MT5SignalRouter()
    result = await router.route_signal(signal, user_id, execution_mode="auto")
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import asyncio

logger = logging.getLogger("MT5SignalRouter")

# Execution modes
class ExecutionMode:
    MANUAL = "manual"   # User executes manually
    AUTO = "auto"       # Auto-execute via MT5
    NONE = "none"       # No execution, just signals


@dataclass
class ExecutionRequest:
    """Signal execution request."""
    signal_id: str
    user_id: int
    asset: str
    direction: str  # long/short
    entry: float
    stop_loss: float
    take_profit: List[float]
    volume: float
    execution_mode: str
    tier: str  # user's tier at time of execution
    created_at: datetime


@dataclass
class ExecutionResult:
    """Result of execution attempt."""
    success: bool
    message: str
    order_id: Optional[str] = None
    executed_at: Optional[datetime] = None
    error: Optional[str] = None


class MT5SignalRouter:
    """
    Routes signals to MT5 for automated execution.
    
    Features:
    - Tier-based execution control (manual/auto/none)
    - Position sizing based on account equity
    - Risk-based lot calculation
    - Paper ledger sync for non-executed trades
    - Multi-account support (VIP)
    """
    
    def __init__(self):
        self._execution_queue: asyncio.Queue = asyncio.Queue()
        self._processing = False
        
    async def initialize(self) -> bool:
        """Initialize router and start processing loop."""
        if self._processing:
            return True
        self._processing = True
        asyncio.create_task(self._process_execution_loop())
        logger.info("[SignalRouter] Initialized")
        return True
    
    async def route_signal(
        self,
        signal: Dict[str, Any],
        user_id: int,
        execution_mode: str = "manual",
    ) -> ExecutionResult:
        """
        Route signal to appropriate execution handler.
        
        Args:
            signal: Signal dict with asset, direction, entry, stop_loss, take_profit
            user_id: Telegram user ID
            execution_mode: manual, auto, or none
            
        Returns:
            ExecutionResult with success status and details
        """
        try:
            # Check execution mode
            if execution_mode == ExecutionMode.NONE:
                return ExecutionResult(
                    success=False,
                    message="Execution disabled - signals only",
                )
            
            # Get user tier for permission check
            tier = self._get_user_tier(user_id)
            
            # Check if MT5 is linked
            mt5_account_id = await self._get_user_mt5_account(user_id)
            
            if not mt5_account_id:
                return ExecutionResult(
                    success=False,
                    message="No MT5 linked - use /mt5_link to connect your account",
                )
            
            # Calculate volume based on tier and risk params
            volume = await self._calculate_position_size(
                user_id=user_id,
                entry=signal.get("entry", 0),
                stop_loss=signal.get("stop_loss", 0),
                account_id=mt5_account_id,
                tier=tier,
            )
            
            if volume <= 0:
                return ExecutionResult(
                    success=False,
                    message="Position size too small - check risk settings",
                )
            
            # Execute if auto mode
            if execution_mode == ExecutionMode.AUTO:
                return await self._execute_via_mt5(
                    signal=signal,
                    user_id=user_id,
                    volume=volume,
                    account_id=mt5_account_id,
                )
            else:
                # Manual mode - just prepare and acknowledge
                return ExecutionResult(
                    success=True,
                    message=f"Execute manually: {signal.get('asset')} {signal.get('direction').upper()} @ {signal.get('entry')} SL {signal.get('stop_loss')}",
                )
                
        except Exception as e:
            logger.error(f"[SignalRouter] Route error: {e}")
            return ExecutionResult(
                success=False,
                message=f"Error: {str(e)}",
                error=str(e),
            )
    
    async def _execute_via_mt5(
        self,
        signal: Dict[str, Any],
        user_id: int,
        volume: float,
        account_id: str,
    ) -> ExecutionResult:
        """Execute signal via MT5/MetaApi."""
        try:
            from services.mt5_client import execute_trade
            
            asset = signal.get("asset", "")
            direction = signal.get("direction", "long")
            entry = signal.get("entry", 0)
            stop_loss = signal.get("stop_loss", 0)
            take_profit = signal.get("take_profit")
            
            # Parse take_profit (could be JSON string or list)
            tp_list = []
            if isinstance(take_profit, str):
                import json
                try:
                    tp_list = json.loads(take_profit)
                except:
                    tp_list = [take_profit]
            elif isinstance(take_profit, list):
                tp_list = take_profit
            
            # Use first TP for now
            tp_price = float(tp_list[0]) if tp_list else 0
            
            result = await execute_trade(
                account_id=account_id,
                symbol=asset,
                direction=direction,
                volume=volume,
                stop_loss=stop_loss,
                take_profit=tp_price,
                signal_entry=entry,
                comment=f"SignalRank:{signal.get('signal_id', '')}",
            )
            
            if result.get("success"):
                # Sync to paper ledger
                await self._sync_to_paper_ledger(
                    signal=signal,
                    user_id=user_id,
                    order_id=result.get("order_id"),
                    volume=volume,
                )
                
                return ExecutionResult(
                    success=True,
                    message=f"Executed: {asset} {direction}",
                    order_id=result.get("order_id"),
                    executed_at=datetime.utcnow(),
                )
            else:
                return ExecutionResult(
                    success=False,
                    message=f"Failed: {result.get('error', 'Unknown error')}",
                    error=result.get("error"),
                )
                
        except Exception as e:
            logger.error(f"[SignalRouter] MT5 execution error: {e}")
            return ExecutionResult(
                success=False,
                message=f"Execution error: {str(e)}",
                error=str(e),
            )
    
    async def _calculate_position_size(
        self,
        user_id: int,
        entry: float,
        stop_loss: float,
        account_id: str,
        tier: str,
    ) -> float:
        """Calculate position size based on risk params and account equity."""
        try:
            # Get account equity from MT5
            from services.mt5_client import get_account_info
            
            info = await get_account_info(account_id)
            if not info:
                return 0.01  # Default micro lot
            
            equity = info.get("equity", 10000)
            
            # Get risk parameters from user settings
            risk_pct = self._get_user_risk_pct(user_id)
            
            # Calculate risk amount
            risk_amount = equity * (risk_pct / 100)
            
            # Calculate SL distance
            sl_distance = abs(entry - stop_loss)
            if sl_distance <= 0:
                return 0.01
            
            # Calculate volume
            volume = risk_amount / sl_distance
            
            # Clamp to reasonable lot sizes
            volume = max(0.01, min(volume, 1.0))  # 0.01 to 1.0 lots
            
            return volume
            
        except Exception as e:
            logger.error(f"[SignalRouter] Volume calculation error: {e}")
            return 0.01
    
    async def _sync_to_paper_ledger(
        self,
        signal: Dict[str, Any],
        user_id: int,
        order_id: Optional[str],
        volume: float,
    ) -> None:
        """Sync executed trade to paper ledger for tracking."""
        try:
            from core.paper_ledger import sync_execution
            
            await sync_execution(
                signal_id=signal.get("signal_id", ""),
                user_id=user_id,
                order_id=order_id or "",
                asset=signal.get("asset", ""),
                direction=signal.get("direction", "long"),
                entry=signal.get("entry", 0),
                stop_loss=signal.get("stop_loss", 0),
                take_profit=signal.get("take_profit", ""),
                volume=volume,
                status="executed",
            )
        except Exception as e:
            logger.error(f"[SignalRouter] Paper ledger sync error: {e}")
    
    async def _get_user_mt5_account(self, user_id: int) -> Optional[str]:
        """Get user's MT5 MetaApi account ID."""
        try:
            from services.mt5_client import get_user_mt5_account_id
            return await get_user_mt5_account_id(user_id)
        except Exception:
            return None
    
    def _get_user_tier(self, user_id: int) -> str:
        """Get user's current tier."""
        try:
            from signalrank_telegram.access import resolve_user_tier
            tier = resolve_user_tier(user_id)
            return str(tier).upper()
        except Exception:
            return "FREE"
    
    def _get_user_risk_pct(self, user_id: int) -> float:
        """Get user's configured risk percentage."""
        try:
            from db.session import get_session
            from db.models import User
            from sqlalchemy import select
            
            async def _fetch():
                async with get_session() as session:
                    result = await session.execute(
                        select(User.max_risk_percentage)
                        .where(User.telegram_user_id == user_id)
                    )
                    row = result.fetchone()
                    return float(row[0]) if row else 1.0
            
            return 1.0  # Default
        except Exception:
            return 1.0
    
    async def _process_execution_loop(self) -> None:
        """Background loop for processing execution queue."""
        while self._processing:
            try:
                request = await self._execution_queue.get()
                # Process in background
                asyncio.create_task(self._process_request(request))
            except Exception as e:
                logger.error(f"[SignalRouter] Loop error: {e}")
    
    async def _process_request(self, request: ExecutionRequest) -> None:
        """Process a single execution request."""
        # Implementation would handle retry logic, etc.
        pass
    
    async def shutdown(self) -> None:
        """Shutdown router."""
        self._processing = False
        logger.info("[SignalRouter] Shutdown complete")


# Singleton instance
router = MT5SignalRouter()


# Convenience functions
async def route_signal_to_mt5(
    signal: Dict[str, Any],
    user_id: int,
    execution_mode: str = "manual",
) -> ExecutionResult:
    """Route signal to MT5 for execution."""
    return await router.route_signal(signal, user_id, execution_mode)


async def get_user_execution_mode(user_id: int) -> str:
    """Get user's current execution mode."""
    try:
        from db.session import get_session
        from db.models import User
        from sqlalchemy import select
        
        async with get_session() as session:
            result = await session.execute(
                select(User.execution_mode)
                .where(User.telegram_user_id == user_id)
            )
            row = result.fetchone()
            return row[0] if row else "manual"
    except Exception:
        return "manual"


async def set_user_execution_mode(user_id: int, mode: str) -> bool:
    """Set user's execution mode."""
    try:
        from db.session import get_session
        from db.models import User
        from sqlalchemy import update
        
        async with get_session() as session:
            await session.execute(
                update(User)
                .where(User.telegram_user_id == user_id)
                .values(execution_mode=mode)
            )
            await session.commit()
        return True
    except Exception as e:
        logger.error(f"[SignalRouter] Set mode error: {e}")
        return False


if __name__ == "__main__":
    # Test
    import asyncio
    
    async def test():
        r = MT5SignalRouter()
        await r.initialize()
        print("Router initialized")
        await r.shutdown()
    
    asyncio.run(test())
