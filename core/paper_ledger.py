"""
Paper Trading Engine for SignalRankAI.

This module handles per-user paper trading with virtual accounts.
Every user gets a virtual balance (default $10,000) to practice trading.

Features:
- Per-user virtual accounts with balance tracking
- Paper position management (open/close)
- P&L calculation and balance updates
- Audit trail in account_ledger table

Usage:
    ledger = PaperLedger()
    
    # Execute a paper trade
    position = await ledger.open_position(user_id, signal)
    
    # Close with outcome
    await ledger.close_position(user_id, position_id, "TP", exit_price=165.50)
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from decimal import Decimal

from config import config

logger = logging.getLogger(__name__)

# Default paper trading balance
DEFAULT_PAPER_BALANCE = 10000.0


class PaperPosition:
    """Represents an open paper trading position."""
    
    def __init__(self, data: Dict[str, Any]):
        self.position_id = data.get("position_id")
        self.user_id = data.get("user_id")
        self.signal_id = data.get("signal_id")
        self.asset = data.get("asset")
        self.direction = data.get("direction")
        self.entry_price = float(data.get("entry_price", 0))
        self.stop_loss = float(data.get("stop_loss", 0))
        self.take_profit = data.get("take_profit")
        self.size = float(data.get("size", 0))
        self.status = data.get("status", "OPEN")
        self.opened_at = data.get("opened_at")
        self.pnl_realized = float(data.get("pnl_realized", 0))
        self.r_multiple = data.get("r_multiple")
        self.exit_reason = data.get("exit_reason")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "position_id": self.position_id,
            "user_id": self.user_id,
            "signal_id": self.signal_id,
            "asset": self.asset,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "size": self.size,
            "status": self.status,
            "opened_at": self.opened_at,
            "pnl_realized": self.pnl_realized,
            "r_multiple": self.r_multiple,
            "exit_reason": self.exit_reason,
        }


class PaperLedger:
    """
    Paper trading ledger for managing virtual accounts and positions.
    
    Each user has a virtual account with a balance. When they execute
    a paper trade, a position is created. When the trade closes,
    the P&L is added/subtracted from their balance.
    
    Usage:
        ledger = PaperLedger()
        
        # Get user balance
        balance = await ledger.get_balance(user_id)
        
        # Open a paper trade
        position = await ledger.open_position(user_id, signal)
        
        # Close with outcome
        await ledger.close_position(user_id, position_id, "TP", exit_price)
    """
    
    def __init__(self):
        self._redis = None
        self._redis_url = self._resolve_redis_url()
        
        if self._redis_url:
            self._init_redis()
    
    def _resolve_redis_url(self) -> Optional[str]:
        import os
        return os.getenv("REDIS_URL") or os.getenv("REDIS_PRIVATE_URL") or None
    
    def _init_redis(self):
        try:
            import redis
            self._redis = redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            self._redis.ping()
            logger.info("[paper_ledger] Connected to Redis")
        except Exception as e:
            logger.debug(f"[paper_ledger] Redis unavailable: {e}")
            self._redis = None
    
    async def get_balance(self, user_id: int) -> float:
        """
        Get a user's virtual account balance.
        
        Args:
            user_id: User ID
            
        Returns:
            Virtual balance (default $10,000 if no account)
        """
        # Check Redis first
        if self._redis:
            try:
                balance = self._redis.hget(f"paper_account:{user_id}", "balance")
                if balance:
                    return float(balance)
            except Exception:
                pass
        
        # Fallback to DB
        try:
            from db.session import get_session
            from db.models import User
            
            async with get_session() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.first()
                
                if user:
                    # Check if they have a virtual account record
                    from db.models import RuntimeState
                    
                    state_result = await session.execute(
                        select(RuntimeState).where(
                            RuntimeState.key == f"paper_balance:{user_id}"
                        )
                    )
                    state = state_result.first()
                    if state:
                        return float(state.value.get("balance", DEFAULT_PAPER_BALANCE))
        except Exception as e:
            logger.debug(f"[paper_ledger] Failed to get balance from DB: {e}")
        
        # Default balance for new users
        return DEFAULT_PAPER_BALANCE
    
    async def set_balance(self, user_id: int, balance: float) -> None:
        """Set a user's virtual account balance."""
        if self._redis:
            try:
                self._redis.hset(
                    f"paper_account:{user_id}",
                    mapping={"balance": str(balance)}
                )
                return
            except Exception:
                pass
        
        # Fallback to DB
        try:
            from db.session import get_session
            from db.models import RuntimeState
            
            async with get_session() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(RuntimeState).where(
                        RuntimeState.key == f"paper_balance:{user_id}"
                    )
                )
                existing = result.first()
                
                if existing:
                    existing.value = {**existing.value, "balance": balance}
                else:
                    state = RuntimeState(
                        key=f"paper_balance:{user_id}",
                        value={"balance": balance, "updated_at": datetime.utcnow().isoformat()}
                    )
                    session.add(state)
                
                await session.commit()
        except Exception as e:
            logger.error(f"[paper_ledger] Failed to set balance: {e}")
    
    async def open_position(
        self,
        user_id: int,
        signal: Dict[str, Any],
        size: Optional[float] = None,
        risk_pct: float = 1.0
    ) -> Optional[PaperPosition]:
        """
        Open a paper trading position.
        
        Args:
            user_id: User ID
            signal: Signal dict with asset, direction, entry, stop_loss, take_profit
            size: Position size (optional - calculated from risk if not provided)
            risk_pct: Risk percentage of balance (default 1%)
            
        Returns:
            PaperPosition if successful, None if insufficient balance
        """
        # Get current balance
        balance = await self.get_balance(user_id)
        
        # Calculate position size if not provided
        if size is None:
            entry = float(signal.get("entry", 0))
            stop_loss = float(signal.get("stop_loss") or signal.get("stop", 0))
            
            if entry > 0 and stop_loss > 0:
                risk_amount = balance * (risk_pct / 100)
                risk_per_unit = abs(entry - stop_loss)
                if risk_per_unit > 0:
                    size = risk_amount / risk_per_unit
        
        if size is None or size <= 0:
            size = balance * 0.01  # Default 1% of balance
        
        # Check sufficient balance
        if size > balance:
            logger.warning(f"[paper_ledger] Insufficient balance for user {user_id}")
            return None
        
        # Calculate entry value
        entry = float(signal.get("entry", 0))
        entry_value = size * entry
        
        if entry_value > balance:
            # Reduce size to fit balance
            size = balance / entry
            entry_value = size * entry
        
        try:
            from db.session import get_session
            from db.models import RuntimeState
            import json
            
            # Generate position ID
            position_id = f"paper_{user_id}_{signal.get('asset', 'unknown')}_{int(datetime.utcnow().timestamp())}"
            
            position_data = {
                "position_id": position_id,
                "user_id": user_id,
                "signal_id": signal.get("signal_id"),
                "asset": signal.get("asset"),
                "direction": signal.get("direction"),
                "entry_price": entry,
                "stop_loss": signal.get("stop_loss"),
                "take_profit": signal.get("take_profit"),
                "size": size,
                "status": "OPEN",
                "opened_at": datetime.utcnow().isoformat(),
                "entry_value": entry_value,
            }
            
            # Store in Redis
            if self._redis:
                self._redis.hset(
                    f"paper_positions:{user_id}",
                    position_id,
                    json.dumps(position_data)
                )
            
            # Also store in DB for persistence
            async with get_session() as session:
                state = RuntimeState(
                    key=f"paper_position:{position_id}",
                    value=position_data
                )
                session.add(state)
                await session.commit()
            
            # Deduct from balance
            new_balance = balance - entry_value
            await self.set_balance(user_id, new_balance)
            
            # Log the trade
            await self._add_ledger_entry(
                user_id,
                -entry_value,
                "TRADE_OPEN",
                f"Opened {signal.get('direction')} {size} {signal.get('asset')} at {entry}"
            )
            
            logger.info(f"[paper_ledger] Opened position {position_id} for user {user_id}: {signal.get('asset')} {signal.get('direction')} size={size}")
            
            return PaperPosition(position_data)
            
        except Exception as e:
            logger.error(f"[paper_ledger] Failed to open position: {e}")
            return None
    
    async def close_position(
        self,
        user_id: int,
        position_id: str,
        exit_reason: str,
        exit_price: float,
        exit_time: Optional[datetime] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Close a paper trading position.
        
        Args:
            user_id: User ID
            position_id: Position ID to close
            exit_reason: Reason for closing (e.g., "TP", "SL", "MANUAL")
            exit_price: Exit price
            exit_time: Exit time (default now)
            
        Returns:
            Dict with P&L details if successful
        """
        if exit_time is None:
            exit_time = datetime.utcnow()
        
        # Get position data
        position_data = await self._get_position(position_id, user_id=user_id)
        
        if not position_data:
            logger.warning(f"[paper_ledger] Position not found: {position_id}")
            return None
        
        if position_data.get("status") != "OPEN":
            logger.warning(f"[paper_ledger] Position not open: {position_id}")
            return None
        
        # Calculate P&L
        direction = position_data.get("direction", "").lower()
        entry_price = float(position_data.get("entry_price", 0))
        size = float(position_data.get("size", 0))
        
        if direction == "long":
            pnl = (exit_price - entry_price) * size
        else:  # short
            pnl = (entry_price - exit_price) * size
        
        # Calculate R multiple
        stop_loss = float(position_data.get("stop_loss", 0))
        if stop_loss > 0 and entry_price > 0:
            risk = abs(entry_price - stop_loss)
            r_multiple = pnl / (risk * size) if size > 0 else 0
        else:
            r_multiple = 0
        
        try:
            # Update position status
            position_data["status"] = "CLOSED"
            position_data["exit_price"] = exit_price
            position_data["closed_at"] = exit_time.isoformat()
            position_data["pnl_realized"] = pnl
            position_data["r_multiple"] = r_multiple
            position_data["exit_reason"] = exit_reason
            
            # Save to Redis
            if self._redis:
                self._redis.hset(
                    f"paper_positions:{user_id}",
                    position_id,
                    json.dumps(position_data))
            
            # Update balance
            balance = await self.get_balance(user_id)
            new_balance = balance + (exit_price * size)
            await self.set_balance(user_id, new_balance)
            
            # Log to ledger
            pnl_type = "TRADE_WIN" if pnl > 0 else "TRADE_LOSS"
            description = f"Closed {position_data.get('asset')} {exit_reason}: {pnl:+.2f} ({r_multiple:+.2f}R)"
            await self._add_ledger_entry(user_id, pnl, pnl_type, description)
            
            logger.info(f"[paper_ledger] Closed position {position_id}: {exit_reason} P&L={pnl:+.2f} ({r_multiple:+.2f}R)")
            
            return {
                "position_id": position_id,
                "pnl": pnl,
                "r_multiple": r_multiple,
                "exit_reason": exit_reason,
                "new_balance": new_balance,
            }
            
        except Exception as e:
            logger.error(f"[paper_ledger] Failed to close position: {e}")
            return None
    
    async def _get_position(self, position_id: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get position data by ID."""
        import json
        
        if self._redis:
            prefixes = [int(user_id)] if user_id is not None else list(range(100))
            for user_id_prefix in prefixes:
                try:
                    data = self._redis.hget(f"paper_positions:{user_id_prefix}", position_id)
                    if data:
                        return json.loads(data)
                except Exception:
                    pass
        
        # Try DB
        try:
            from db.session import get_session
            from db.models import RuntimeState
            
            async with get_session() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(RuntimeState).where(
                        RuntimeState.key == f"paper_position:{position_id}"
                    )
                )
                state = result.first()
                if state:
                    return state.value
        except Exception:
            pass
        
        return None
    
    async def get_open_positions(self, user_id: int) -> List[PaperPosition]:
        """Get all open positions for a user."""
        import json
        
        positions = []
        
        if self._redis:
            try:
                data = self._redis.hgetall(f"paper_positions:{user_id}")
                for pos_id, pos_json in (data or {}).items():
                    try:
                        pos_data = json.loads(pos_json)
                        if pos_data.get("status") == "OPEN":
                            positions.append(PaperPosition(pos_data))
                    except Exception:
                        continue
            except Exception:
                pass
        
        return positions
    
    async def _add_ledger_entry(
        self,
        user_id: int,
        amount: float,
        entry_type: str,
        description: str
    ) -> None:
        """Add an entry to the account ledger for audit trail."""
        try:
            from db.session import get_session
            from db.models import RuntimeState
            
            async with get_session() as session:
                # Find account
                balance = await self.get_balance(user_id)
                
                state = RuntimeState(
                    key=f"paper_ledger:{user_id}:{int(datetime.utcnow().timestamp())}",
                    value={
                        "user_id": user_id,
                        "amount": amount,
                        "type": entry_type,
                        "description": description,
                        "balance_after": balance + amount if amount > 0 else balance,
                        "created_at": datetime.utcnow().isoformat(),
                    }
                )
                session.add(state)
                await session.commit()
        except Exception as e:
            logger.debug(f"[paper_ledger] Failed to add ledger entry: {e}")
    
    async def check_tp_sl_hit(self, user_id: int, asset: str, current_price: float) -> Optional[str]:
        """
        Check if any open positions for an asset hit TP or SL.
        
        Args:
            user_id: User ID
            asset: Asset symbol
            current_price: Current market price
            
        Returns:
            "TP" if take profit hit, "SL" if stop loss hit, None if neither
        """
        def _first_tp(value: Any) -> Optional[float]:
            import json

            raw = value
            if isinstance(raw, str):
                text = raw.strip()
                if not text:
                    return None
                try:
                    raw = json.loads(text)
                except Exception:
                    raw = text
            if isinstance(raw, dict):
                raw = raw.get("price") or raw.get("tp") or raw.get("target") or raw.get("value")
            if isinstance(raw, (list, tuple)):
                for item in raw:
                    tp = _first_tp(item)
                    if tp is not None and tp > 0:
                        return tp
                return None
            try:
                tp = float(raw)
                return tp if tp > 0 else None
            except Exception:
                return None

        positions = await self.get_open_positions(user_id)
        
        for pos in positions:
            if pos.asset != asset or pos.status != "OPEN":
                continue
            
            direction = pos.direction.lower()
            entry = pos.entry_price
            sl = pos.stop_loss
            tp = _first_tp(pos.take_profit)

            if current_price <= 0 or entry <= 0:
                continue
            
            if direction == "long":
                if tp is not None and current_price >= tp:
                    return "TP"
                if sl > 0 and current_price <= sl:
                    return "SL"
            else:  # short
                if tp is not None and current_price <= tp:
                    return "TP"
                if sl > 0 and current_price >= sl:
                    return "SL"
        
        return None


# Global paper ledger instance
_paper_ledger: Optional[PaperLedger] = None


def get_paper_ledger() -> PaperLedger:
    """Get or create the global paper ledger."""
    global _paper_ledger
    if _paper_ledger is None:
        _paper_ledger = PaperLedger()
    return _paper_ledger


async def sync_execution(
    signal_id: str,
    user_id: int,
    order_id: str,
    asset: str,
    direction: str,
    entry: float,
    stop_loss: float,
    take_profit: Any,
    volume: float,
    status: str = "executed",
) -> Optional[PaperPosition]:
    """Mirror a live broker execution into the paper ledger for tracking."""
    signal = {
        "signal_id": signal_id,
        "broker_order_id": order_id,
        "asset": asset,
        "direction": direction,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "execution_status": status,
    }
    ledger = get_paper_ledger()
    position = await ledger.open_position(
        user_id=int(user_id),
        signal=signal,
        size=float(volume or 0.0) if volume is not None else None,
        risk_pct=1.0,
    )
    if position:
        await ledger._add_ledger_entry(
            int(user_id),
            0.0,
            "LIVE_SYNC",
            f"Synced live order {order_id or 'unknown'} for {asset} {direction}",
        )
    return position
