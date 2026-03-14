"""Tiered MT5 Execution Engine.

Implements execution logic for the two paid tiers:

PREMIUM (₦15k/month)
    • Maximum 3 automated executions per calendar day (UTC)
    • Fixed lot size stored on ``User.fixed_lot_size`` (default 0.01)
    • Executes to TP2 only (single take-profit stage)
    • Stop-loss is NOT moved automatically

VIP (₦30k/month)
    • Unlimited daily executions
    • Risk-based lot sizing: ``account_balance × (risk_pct / 100) / pip_distance``
    • Multi-stage TPs:
        - Stage 1 (TP1): close 50 % of position → move SL to entry break-even
        - Stage 2 (TP2): close 50 % of remainder → move SL to TP1
        - Stage 3 (TP3): close rest with trailing SL

Usage::
    from engine.tiered_executor import execute_for_user, can_execute

    ok, reason = await can_execute(user)
    if ok:
        result = await execute_for_user(user, signal, db_session)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PREMIUM_DAILY_LIMIT: int = int(os.getenv("PREMIUM_DAILY_EXECUTIONS", "3"))
MAX_LOT_PREMIUM: float = float(os.getenv("PREMIUM_MAX_LOT", "1.0"))
DEFAULT_FIXED_LOT: float = float(os.getenv("DEFAULT_FIXED_LOT", "0.01"))
DEFAULT_RISK_PCT: float = float(os.getenv("DEFAULT_RISK_PCT", "1.0"))
MAX_RISK_PCT: float = float(os.getenv("MAX_RISK_PCT", "5.0"))
HARD_MAX_RISK_CAP_PCT: float = float(os.getenv("AUTO_MAX_RISK_CAP_PCT", "3.0"))
MIN_LOT: float = 0.001
MAX_LOT_VIP: float = float(os.getenv("VIP_MAX_LOT", "10.0"))

# Pip value (USD per lot per pip) for standard contracts
# For most FX: 1 pip = 0.0001 price move, 1 lot = 100k units → pip_value = $10
# For XAUUSD: 1 pip = 0.01, 1 lot = 100 oz → pip_value = $1
_PIP_VALUES: dict[str, float] = {
    "XAUUSD": 1.0,
    "XAGUSD": 0.50,
    "BTCUSD": 0.01,
    "BTCUSDT": 0.01,
    "ETHUSD": 0.10,
    "ETHUSDT": 0.10,
    "USDJPY": 9.09,
    "EURJPY": 9.09,
    "GBPJPY": 9.09,
}
_DEFAULT_PIP_VALUE = 10.0  # USD per lot per pip for standard FX


# ---------------------------------------------------------------------------
# Lot-size calculators
# ---------------------------------------------------------------------------

def calculate_lot_size_premium(user) -> float:  # type: ignore[valid-type]
    """Return the fixed lot size for a PREMIUM user.

    Reads ``user.fixed_lot_size``, clamps to ``[MIN_LOT, MAX_LOT_PREMIUM]``.
    Falls back to ``DEFAULT_FIXED_LOT`` if unset.
    """
    lot = getattr(user, "fixed_lot_size", None) or DEFAULT_FIXED_LOT
    lot = float(lot)
    return max(MIN_LOT, min(lot, MAX_LOT_PREMIUM))


def calculate_lot_size_vip(
    user,  # type: ignore[valid-type]
    account_balance: float,
    entry_price: float,
    stop_loss: float,
    symbol: str = "",
) -> float:
    """Return a risk-adjusted lot size for a VIP user.

    Formula:
        ``lots = (balance × risk_pct/100) / (sl_distance_pips × pip_value)``

    where:
        - ``sl_distance_pips = abs(entry - sl) / pip_size``
        - ``pip_size``  = 0.0001 for FX, 0.01 for XAUUSD, 1.0 for USDJPY, etc.
        - ``pip_value`` = USD per lot per pip (from ``_PIP_VALUES``)

    Result is clamped to ``[MIN_LOT, MAX_LOT_VIP]``.
    """
    risk_pct = getattr(user, "max_risk_percentage", None) or DEFAULT_RISK_PCT
    effective_max = min(float(MAX_RISK_PCT), float(HARD_MAX_RISK_CAP_PCT))
    risk_pct = max(0.1, min(float(risk_pct), effective_max))

    if account_balance <= 0 or entry_price <= 0 or stop_loss <= 0:
        return DEFAULT_FIXED_LOT

    sl_distance = abs(entry_price - stop_loss)
    if sl_distance <= 0:
        return DEFAULT_FIXED_LOT

    sym = str(symbol).upper()
    pip_value = _PIP_VALUES.get(sym, _DEFAULT_PIP_VALUE)

    # Determine pip size from symbol
    if "JPY" in sym:
        pip_size = 0.01
    elif sym in ("XAUUSD", "XAGUSD"):
        pip_size = 0.01
    elif sym in ("BTCUSD", "BTCUSDT", "ETHUSD", "ETHUSDT"):
        pip_size = 1.0
    else:
        pip_size = 0.0001

    sl_distance_pips = sl_distance / pip_size
    if sl_distance_pips <= 0:
        return DEFAULT_FIXED_LOT

    risk_amount = account_balance * (risk_pct / 100.0)
    lot = risk_amount / (sl_distance_pips * pip_value)
    lot = round(lot, 3)
    return max(MIN_LOT, min(lot, MAX_LOT_VIP))


# ---------------------------------------------------------------------------
# Daily execution guard
# ---------------------------------------------------------------------------

def _is_new_day(user) -> bool:  # type: ignore[valid-type]
    """Return True if user's execution counter should be reset (new UTC day)."""
    reset_at = getattr(user, "daily_executions_reset_at", None)
    if reset_at is None:
        return True
    now = datetime.now(tz=timezone.utc)
    if hasattr(reset_at, "tzinfo") and reset_at.tzinfo is None:
        reset_at = reset_at.replace(tzinfo=timezone.utc)
    return now.date() > reset_at.date()


def reset_daily_counter_if_needed(user) -> bool:  # type: ignore[valid-type]
    """Reset ``daily_executions_today`` if it is a new calendar day.

    Returns True if a reset was performed (caller must flush to DB).
    """
    if _is_new_day(user):
        user.daily_executions_today = 0
        user.daily_executions_reset_at = datetime.now(tz=timezone.utc)
        return True
    return False


def can_execute_premium(user) -> Tuple[bool, str]:  # type: ignore[valid-type]
    """Check whether a PREMIUM user may execute another trade today.

    Returns:
        (allowed, reason_string)
    """
    reset_daily_counter_if_needed(user)
    count = int(getattr(user, "daily_executions_today", 0) or 0)
    if count >= PREMIUM_DAILY_LIMIT:
        return (
            False,
            f"Daily limit reached ({PREMIUM_DAILY_LIMIT} executions/day on PREMIUM). "
            f"Upgrade to VIP for unlimited executions.",
        )
    return True, ""


def can_execute_vip(user) -> Tuple[bool, str]:  # type: ignore[valid-type]
    """VIP has no hard daily limit — always allowed (if credentials set)."""
    mt5_id = getattr(user, "metaapi_account_id", None) or getattr(user, "mt5_account_id", None)
    if not mt5_id:
        return False, "No MT5 account connected. Use /connect_broker to link your account."
    return True, ""


async def can_execute(user) -> Tuple[bool, str]:  # type: ignore[valid-type]
    """Return (allowed, reason) for the given user based on their tier."""
    tier = str(getattr(user, "tier", "FREE")).upper()
    if tier == "PREMIUM":
        return can_execute_premium(user)
    if tier in ("VIP", "OWNER", "ADMIN"):
        return can_execute_vip(user)
    return False, "Automated execution requires PREMIUM or VIP subscription."


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------

async def _record_execution(
    db: AsyncSession,
    user_id: int,
    signal_id: int,
    symbol: str,
    direction: str,
    lot_size: float,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    tier: str,
    order_id: Optional[str] = None,
    account_id: Optional[str] = None,
) -> None:
    """Persist an ``MT5Execution`` row and increment the user's daily counter."""
    try:
        from db.models import MT5Execution
        from db.session import get_session as _gs

        execution = MT5Execution(
            user_id=user_id,
            signal_id=signal_id,
            symbol=symbol,
            direction=direction,
            lot_size=lot_size,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            tier_at_execution=tier,
            order_id=order_id,
            metaapi_account_id=account_id,
            status="pending",
            executed_at=datetime.now(tz=timezone.utc),
        )
        db.add(execution)
        await db.flush()
        logger.info(f"[tiered_executor] Recorded MT5Execution id={execution.id} user={user_id}")
    except Exception as exc:
        logger.error(f"[tiered_executor] Failed to record execution: {exc}")


async def execute_premium_signal(
    user,  # type: ignore[valid-type]
    signal,  # type: ignore[valid-type]
    db: AsyncSession,
) -> dict:
    """Execute a signal for a PREMIUM user.

    - Uses ``user.fixed_lot_size``
    - Only executes to TP2 (single target)
    - Does NOT move SL automatically
    - Increments ``daily_executions_today``

    Returns a dict with ``{"success": bool, "order_id": str, "message": str}``.
    """
    allowed, reason = can_execute_premium(user)
    if not allowed:
        return {"success": False, "order_id": None, "message": reason}

    lot = calculate_lot_size_premium(user)
    symbol: str = getattr(signal, "symbol", "") or ""
    direction: str = getattr(signal, "direction", "BUY") or "BUY"
    entry: float = float(getattr(signal, "entry_price", 0) or 0)
    sl: float = float(getattr(signal, "stop_loss", 0) or 0)
    # PREMIUM: target only TP2
    tp2 = getattr(signal, "tp2", None) or getattr(signal, "take_profit2", None)
    tp1 = getattr(signal, "tp1", None) or getattr(signal, "take_profit1", None)
    take_profit: float = float(tp2 or tp1 or 0)

    if not entry or not sl or not take_profit:
        return {
            "success": False,
            "order_id": None,
            "message": "Signal missing entry/SL/TP values.",
        }

    order_id: Optional[str] = None
    account_id: Optional[str] = None
    error_msg = ""

    try:
        from services.mt5_client import execute_trade, get_user_mt5_account_id

        account_id = await get_user_mt5_account_id(user.telegram_user_id)
        if not account_id:
            return {
                "success": False,
                "order_id": None,
                "message": "No MT5 account linked. Use /connect_broker.",
            }

        result = await execute_trade(
            account_id=account_id,
            symbol=symbol,
            direction=direction.upper(),
            volume=lot,
            stop_loss=sl,
            take_profit=take_profit,
            signal_entry=entry,
        )
        order_id = str(result.get("order_id", "")) if isinstance(result, dict) else str(result)
        success = bool(order_id)

    except Exception as exc:
        logger.error(f"[tiered_executor][PREMIUM] execute_trade failed: {exc}")
        success = False
        error_msg = str(exc)

    if success:
        # Increment counter
        user.daily_executions_today = int(getattr(user, "daily_executions_today", 0) or 0) + 1
        user.daily_executions_reset_at = datetime.now(tz=timezone.utc)
        await _record_execution(
            db=db,
            user_id=user.telegram_user_id,
            signal_id=getattr(signal, "id", 0),
            symbol=symbol,
            direction=direction,
            lot_size=lot,
            entry_price=entry,
            stop_loss=sl,
            take_profit=take_profit,
            tier="PREMIUM",
            order_id=order_id,
            account_id=account_id,
        )
        remaining = max(0, PREMIUM_DAILY_LIMIT - int(user.daily_executions_today))
        msg = (
            f"✅ PREMIUM execution placed!\n"
            f"  Symbol: {symbol}  {direction}  @ {entry}\n"
            f"  Lot: {lot}  SL: {sl}  TP: {take_profit}\n"
            f"  Order ID: {order_id}\n"
            f"  Daily executions remaining: {remaining}/{PREMIUM_DAILY_LIMIT}"
        )
        return {"success": True, "order_id": order_id, "message": msg}
    else:
        msg = f"❌ Execution failed: {error_msg or 'MetaApi error'}"
        return {"success": False, "order_id": None, "message": msg}


async def execute_vip_signal(
    user,  # type: ignore[valid-type]
    signal,  # type: ignore[valid-type]
    db: AsyncSession,
    account_balance: float = 0.0,
) -> dict:
    """Execute a signal for a VIP user with multi-stage take-profits.

    Stage structure:
        - Execute full lot (risk-based)
        - On TP1 hit (handled by realtime_outcome_tracker):
            close 50 % → SL moves to entry (break-even)
        - On TP2 hit: close 50 % of remainder → SL moves to TP1
        - On TP3 hit: close rest

    This function places the initial order to TP1. The RealtimeOutcomeTracker
    handles subsequent stage management.

    Args:
        account_balance: MT5 account equity in USD.  If 0, fallback to default lot.

    Returns a dict with ``{"success": bool, "order_id": str, "message": str}``.
    """
    allowed, reason = can_execute_vip(user)
    if not allowed:
        return {"success": False, "order_id": None, "message": reason}

    symbol: str = getattr(signal, "symbol", "") or ""
    direction: str = getattr(signal, "direction", "BUY") or "BUY"
    entry: float = float(getattr(signal, "entry_price", 0) or 0)
    sl: float = float(getattr(signal, "stop_loss", 0) or 0)

    # VIP: place initial entry to TP1; tracker handles TP2/TP3
    tp1 = getattr(signal, "tp1", None) or getattr(signal, "take_profit1", None)
    tp2 = getattr(signal, "tp2", None) or getattr(signal, "take_profit2", None)
    tp3 = getattr(signal, "tp3", None) or getattr(signal, "take_profit3", None)
    first_tp: float = float(tp1 or tp2 or 0)

    if not entry or not sl or not first_tp:
        return {
            "success": False,
            "order_id": None,
            "message": "Signal missing entry/SL/TP values.",
        }

    lot = calculate_lot_size_vip(user, account_balance, entry, sl, symbol)
    order_id: Optional[str] = None
    account_id: Optional[str] = None
    error_msg = ""

    try:
        from services.mt5_client import execute_trade, get_user_mt5_account_id

        account_id = await get_user_mt5_account_id(user.telegram_user_id)
        if not account_id:
            return {
                "success": False,
                "order_id": None,
                "message": "No MT5 account linked. Use /connect_broker.",
            }

        result = await execute_trade(
            account_id=account_id,
            symbol=symbol,
            direction=direction.upper(),
            volume=lot,
            stop_loss=sl,
            take_profit=first_tp,
            signal_entry=entry,
        )
        order_id = str(result.get("order_id", "")) if isinstance(result, dict) else str(result)
        success = bool(order_id)

    except Exception as exc:
        logger.error(f"[tiered_executor][VIP] execute_trade failed: {exc}")
        success = False
        error_msg = str(exc)

    if success:
        await _record_execution(
            db=db,
            user_id=user.telegram_user_id,
            signal_id=getattr(signal, "id", 0),
            symbol=symbol,
            direction=direction,
            lot_size=lot,
            entry_price=entry,
            stop_loss=sl,
            take_profit=first_tp,
            tier="VIP",
            order_id=order_id,
            account_id=account_id,
        )
        tp_summary = (
            f"TP1: {tp1}  TP2: {tp2}" + (f"  TP3: {tp3}" if tp3 else "")
            if tp2 else f"TP: {first_tp}"
        )
        msg = (
            f"✅ VIP execution placed!\n"
            f"  Symbol: {symbol}  {direction}  @ {entry}\n"
            f"  Lot: {lot}  (risk {getattr(user, 'max_risk_percentage', DEFAULT_RISK_PCT):.1f}%)\n"
            f"  SL: {sl}  {tp_summary}\n"
            f"  Order ID: {order_id}\n"
            f"  ⚡ Multi-stage TP management active"
        )
        return {"success": True, "order_id": order_id, "message": msg}
    else:
        msg = f"❌ Execution failed: {error_msg or 'MetaApi error'}"
        return {"success": False, "order_id": None, "message": msg}


async def execute_for_user(
    user,  # type: ignore[valid-type]
    signal,  # type: ignore[valid-type]
    db: AsyncSession,
    account_balance: float = 0.0,
) -> dict:
    """Dispatch to the correct execution path based on the user's tier.

    Returns a result dict compatible with both ``execute_premium_signal``
    and ``execute_vip_signal``.
    """
    tier = str(getattr(user, "tier", "FREE")).upper()
    if tier == "PREMIUM":
        return await execute_premium_signal(user, signal, db)
    if tier in ("VIP", "OWNER", "ADMIN"):
        return await execute_vip_signal(user, signal, db, account_balance)
    return {
        "success": False,
        "order_id": None,
        "message": "Automated execution requires PREMIUM or VIP.",
    }


async def update_active_signal_messages(
    user_id: int,
    signal_id: int,
    new_text: str,
    bot,  # type: ignore[valid-type]
    db: AsyncSession,
) -> None:
    """Edit all tracked ``ActiveSignalMessage`` rows for a user/signal pair.

    Called after /setlot or /setrisk so the inline message reflects the
    updated lot/risk values.
    """
    try:
        from sqlalchemy import select
        from db.models import ActiveSignalMessage

        stmt = select(ActiveSignalMessage).where(
            ActiveSignalMessage.user_id == user_id,
            ActiveSignalMessage.signal_id == signal_id,
            ActiveSignalMessage.is_active.is_(True),
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        for row in rows:
            try:
                await bot.edit_message_text(
                    chat_id=row.chat_id,
                    message_id=row.message_id,
                    text=new_text,
                    parse_mode="HTML",
                )
            except Exception as exc:
                logger.debug(f"[tiered_executor] edit_message_text failed: {exc}")
    except Exception as exc:
        logger.error(f"[tiered_executor] update_active_signal_messages: {exc}")
