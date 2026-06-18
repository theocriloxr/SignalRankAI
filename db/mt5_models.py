"""
MT5 Account Models - Enhanced Multi-Account Tracking

This module provides:
- MT5Account table for tracking multiple accounts per user
- MT5ExecutionLog for trade history
- Integration with PostgreSQL session

Usage:
    from db.mt5_models import MT5Account, MT5ExecutionLog
    
    # Query user's accounts
    accounts = await get_user_mt5_accounts(user_id)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Get current UTC time."""
    return datetime.utcnow()


class MT5Account:
    """
    MT5 Account tracking for multiple accounts per user.
    
    Each user can have multiple MT5 accounts (e.g., for different strategies
    or risk profiles). This model tracks the linkage between user and broker accounts.
    """
    
    __tablename__ = "mt5_accounts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    
    # Account identification
    account_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    account_name: Mapped[str] = mapped_column(String(128), nullable=False)
    
    # MetaApi / Broker details
    metaapi_account_id: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    broker_server: Mapped[str] = mapped_column(String(128))
    mt5_login: Mapped[str] = mapped_column(String(64))
    
    # Connection status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Risk settings per account
    max_risk_pct: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    max_daily_loss_pct: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    
    # Execution mode
    execution_mode: Mapped[str] = mapped_column(String(16), default="live", nullable=False)
    # "live" = real money, "paper" = virtual
    
    # Limits
    max_positions: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    max_daily_trades: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    
    # Balance tracking (updated on sync)
    balance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    equity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Metadata
    meta: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    
    def __repr__(self):
        return f"<MT5Account account_id={self.account_id} user_id={self.user_id}>"


class MT5ExecutionLog:
    """
    Execution log for tracking MT5 trades.
    
    Records all trades executed via MT5 for audit and sync with paper ledger.
    """
    
    __tablename__ = "mt5_execution_log"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Account and user
    account_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    
    # Signal reference
    signal_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    execution_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    
    # Trade details
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, default=0.0)
    take_profit: Mapped[str] = mapped_column(Text, default="")
    
    # Execution result
    order_id: Mapped[Optional[str]] = mapped_column(String(128))
    position_id: Mapped[Optional[str]] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    # pending, filled, partially_filled, rejected, cancelled, closed
    
    # P&L tracking
    exit_price: Mapped[Optional[float]] = mapped_column(Float)
    realized_pnl: Mapped[Optional[float]] = mapped_column(Float)
    realized_pnl_pct: Mapped[Optional[float]] = mapped_column(Float)
    r_multiple: Mapped[Optional[float]] = mapped_column(Float)
    
    # Timing
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    
    # Metadata
    meta: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class MT5Position:
    """
    Live position tracking for MT5 positions.
    
    Synced from MetaApi to track open positions in real-time.
    """
    
    __tablename__ = "mt5_positions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Account
    account_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    
    # MetaApi position ID
    position_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    
    # Trade details
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, default=0.0)
    take_profit: Mapped[str] = mapped_column(Text, default="")
    
    # Unrealized P&L
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Status
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    # open, closed, partially_closed
    
    # Timing
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


# Convenience functions for DB operations
async def get_user_mt5_accounts(user_id: int) -> List[MT5Account]:
    """Get all MT5 accounts for a user."""
    from db.session import get_session
    from sqlalchemy import select
    
    async with get_session() as session:
        result = await session.execute(
            select(MT5Account).where(
                MT5Account.user_id == user_id,
                MT5Account.is_active == True
            )
        )
        return list(result.scalars().all())


async def get_default_account(user_id: int) -> Optional[MT5Account]:
    """Get the default MT5 account for a user."""
    from db.session import get_session
    from sqlalchemy import select
    
    async with get_session() as session:
        result = await session.execute(
            select(MT5Account).where(
                MT5Account.user_id == user_id,
                MT5Account.is_active == True,
                MT5Account.is_default == True
            )
        )
        account = result.first()
        
        if not account:
            # Get first active account as fallback
            result = await session.execute(
                select(MT5Account).where(
                    MT5Account.user_id == user_id,
                    MT5Account.is_active == True
                ).limit(1)
            )
            account = result.first()
        
        return account


async def get_account_by_id(account_id: str) -> Optional[MT5Account]:
    """Get MT5 account by account_id."""
    from db.session import get_session
    from sqlalchemy import select
    
    async with get_session() as session:
        result = await session.execute(
            select(MT5Account).where(
                MT5Account.account_id == account_id
            )
        )
        return result.first()


async def create_mt5_account(
    user_id: int,
    account_id: str,
    account_name: str,
    metaapi_account_id: Optional[str] = None,
    broker_server: str = "",
    mt5_login: str = "",
    is_default: bool = True
) -> Optional[MT5Account]:
    """Create a new MT5 account for a user."""
    from db.session import get_session
    from sqlalchemy import select, func
    
    async with get_session() as session:
        # Check if this is the first account (make it default)
        count_result = await session.execute(
            select(func.count(MT5Account.id)).where(
                MT5Account.user_id == user_id,
                MT5Account.is_active == True
            )
        )
        existing_count = count_result.scalar() or 0
        
        if existing_count == 0:
            is_default = True
        
        # If setting as default, unset other defaults
        if is_default:
            await session.execute(
                select(MT5Account).where(
                    MT5Account.user_id == user_id,
                    MT5Account.is_default == True
                )
            )
            for acc in session.scalars():
                if acc:
                    acc.is_default = False
        
        account = MT5Account(
            user_id=user_id,
            account_id=account_id,
            account_name=account_name,
            metaapi_account_id=metaapi_account_id,
            broker_server=broker_server,
            mt5_login=mt5_login,
            is_default=is_default,
            is_active=True,
        )
        session.add(account)
        await session.commit()
        
        logger.info(f"[mt5_models] Created account {account_id} for user {user_id}")
        return account


async def update_account_balance(
    account_id: str,
    balance: float,
    equity: float
) -> bool:
    """Update account balance after sync."""
    from db.session import get_session
    from sqlalchemy import select
    
    async with get_session() as session:
        result = await session.execute(
            select(MT5Account).where(
                MT5Account.account_id == account_id
            )
        )
        account = result.first()
        
        if account:
            account.balance = balance
            account.equity = equity
            account.last_sync_at = _utcnow()
            await session.commit()
            return True
        
        return False


async def log_execution(
    account_id: str,
    user_id: int,
    symbol: str,
    direction: str,
    volume: float,
    entry_price: float,
    stop_loss: float = 0.0,
    take_profit: str = "",
    signal_id: Optional[str] = None,
    order_id: Optional[str] = None,
    status: str = "pending"
) -> MT5ExecutionLog:
    """Log a new execution."""
    from db.session import get_session
    
    async with get_session() as session:
        log = MT5ExecutionLog(
            account_id=account_id,
            user_id=user_id,
            symbol=symbol,
            direction=direction,
            volume=volume,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signal_id=signal_id,
            order_id=order_id,
            status=status,
        )
        session.add(log)
        await session.commit()
        
        logger.info(f"[mt5_models] Logged execution for {symbol} status={status}")
        return log


async def update_execution_status(
    execution_id: int,
    status: str,
    position_id: Optional[str] = None,
    error_message: Optional[str] = None
) -> bool:
    """Update execution status."""
    from db.session import get_session
    from sqlalchemy import select
    
    async with get_session() as session:
        result = await session.execute(
            select(MT5ExecutionLog).where(
                MT5ExecutionLog.id == execution_id
            )
        )
        execution = result.first()
        
        if execution:
            execution.status = status
            if position_id:
                execution.position_id = position_id
            if error_message:
                execution.error_message = error_message
            await session.commit()
            return True
        
        return False


async def close_execution(
    execution_id: int,
    exit_price: float,
    realized_pnl: float,
    r_multiple: float
) -> bool:
    """Close an execution with P&L."""
    from db.session import get_session
    from sqlalchemy import select
    
    async with get_session() as session:
        result = await session.execute(
            select(MT5ExecutionLog).where(
                MT5ExecutionLog.id == execution_id
            )
        )
        execution = result.first()
        
        if execution:
            execution.status = "closed"
            execution.exit_price = exit_price
            execution.realized_pnl = realized_pnl
            execution.r_multiple = r_multiple
            execution.closed_at = _utcnow()
            
            # Calculate P&L percentage
            if execution.entry_price > 0:
                execution.realized_pnl_pct = (realized_pnl / (execution.entry_price * execution.volume)) * 100
            
            await session.commit()
            return True
        
        return False


async def get_open_executions(account_id: str) -> List[MT5ExecutionLog]:
    """Get all open executions for an account."""
    from db.session import get_session
    from sqlalchemy import select
    
    async with get_session() as session:
        result = await session.execute(
            select(MT5ExecutionLog).where(
                MT5ExecutionLog.account_id == account_id,
                MT5ExecutionLog.status == "filled"
            )
        )
        return list(result.scalars().all())


logger.info("✅ MT5 Models defined successfully")
