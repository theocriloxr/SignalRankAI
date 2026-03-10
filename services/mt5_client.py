"""
services/mt5_client.py - MetaApi Cloud Bridge for Linux-compatible MT5 integration.

The official MetaTrader5 Python library only works on Windows.
This module uses the metaapi.cloud async Python SDK as a Linux-compatible bridge.

Environment variables:
    META_API_TOKEN       - MetaApi cloud token (get from metaapi.cloud dashboard)
    META_API_DOMAIN      - Optional: override MetaApi domain (default: agiliumtrade.agiliumtrade.ai)
    SLIPPAGE_TOLERANCE   - Max pips/points allowed between signal price and live price (default: 10)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from metaapi_cloud_sdk import MetaApi
    _METAAPI_AVAILABLE = True
except ImportError:
    MetaApi = None  # type: ignore
    _METAAPI_AVAILABLE = False
    logger.warning(
        "[mt5_client] metaapi-cloud-sdk not installed. "
        "MT5 one-click execution will be disabled. "
        "Install with: pip install metaapi-cloud-sdk"
    )


def _slippage_tolerance() -> float:
    try:
        return float(os.getenv("SLIPPAGE_TOLERANCE", "10"))
    except Exception:
        return 10.0


async def _get_account(account_id: str) -> Optional[Any]:
    """Retrieve a MetaApi account object by ID."""
    token = (os.getenv("META_API_TOKEN") or "").strip()
    if not token:
        logger.error("[mt5_client] META_API_TOKEN not set")
        return None
    if not _METAAPI_AVAILABLE:
        logger.error("[mt5_client] metaapi-cloud-sdk not installed")
        return None
    try:
        domain = os.getenv("META_API_DOMAIN")
        api = MetaApi(token, {"domain": domain} if domain else {})
        account = await api.metatrader_account_api.get_account(account_id)
        return account
    except Exception as exc:
        logger.error("[mt5_client] Failed to get account %s: %s", account_id, exc)
        return None


async def get_live_price(account_id: str, symbol: str) -> Optional[float]:
    """Fetch the current ask/bid mid price for a symbol from MT5 via MetaApi.

    Returns the mid price (bid+ask)/2 or None on failure.
    """
    account = await _get_account(account_id)
    if account is None:
        return None
    try:
        # Ensure account is connected
        if account.state not in ("DEPLOYED", "DEPLOYING"):
            await account.deploy()
        connection = account.get_rpc_connection()
        await connection.connect()
        await connection.wait_synchronized()
        price_data = await connection.get_symbol_price(symbol)
        if price_data:
            bid = float(price_data.get("bid", 0) or 0)
            ask = float(price_data.get("ask", 0) or 0)
            mid = (bid + ask) / 2.0 if bid and ask else (bid or ask)
            return mid if mid else None
        return None
    except Exception as exc:
        logger.error("[mt5_client] get_live_price error symbol=%s: %s", symbol, exc)
        return None


async def validate_slippage(
    account_id: str,
    symbol: str,
    signal_price: float,
) -> Tuple[bool, float, Optional[float]]:
    """Check if the live price is within slippage tolerance of the signal entry.

    Returns:
        (within_tolerance: bool, slippage_points: float, live_price: Optional[float])
    """
    live = await get_live_price(account_id, symbol)
    if live is None:
        # Can't validate — allow with warning
        logger.warning("[mt5_client] validate_slippage: could not fetch live price for %s", symbol)
        return True, 0.0, None
    slippage = abs(live - signal_price)
    within = slippage <= _slippage_tolerance()
    return within, slippage, live


async def execute_trade(
    account_id: str,
    symbol: str,
    direction: str,
    volume: float,
    stop_loss: float,
    take_profit: float,
    signal_entry: float,
    comment: str = "SignalRankAI",
) -> Dict[str, Any]:
    """Place a market order via MetaApi.

    Args:
        account_id: MetaApi account ID.
        symbol:     MT5 symbol (e.g. "BTCUSD", "EURUSD").
        direction:  "long" or "short".
        volume:     Lot size.
        stop_loss:  Stop-loss price.
        take_profit: Take-profit price.
        signal_entry: Original signal entry price (used for slippage check).
        comment:    Order comment tag.

    Returns:
        Dict with keys: success, order_id, live_price, slippage, error.
    """
    result: Dict[str, Any] = {
        "success": False,
        "order_id": None,
        "live_price": None,
        "slippage": None,
        "error": None,
    }

    # 1. Validate slippage
    ok, slippage, live_price = await validate_slippage(account_id, symbol, signal_entry)
    result["live_price"] = live_price
    result["slippage"] = slippage

    if not ok:
        result["error"] = (
            f"Slippage too high: {slippage:.4f} points "
            f"(tolerance: {_slippage_tolerance():.0f})"
        )
        logger.warning(
            "[mt5_client] execute_trade rejected: slippage=%.4f > tolerance=%.0f "
            "symbol=%s signal_entry=%.5f live=%.5f",
            slippage, _slippage_tolerance(), symbol, signal_entry, live_price or 0,
        )
        return result

    # 2. Place order
    account = await _get_account(account_id)
    if account is None:
        result["error"] = "Could not retrieve MetaApi account"
        return result

    try:
        if account.state not in ("DEPLOYED", "DEPLOYING"):
            await account.deploy()
        connection = account.get_rpc_connection()
        await connection.connect()
        await connection.wait_synchronized()

        action = "ORDER_TYPE_BUY" if str(direction).lower() == "long" else "ORDER_TYPE_SELL"
        order_result = await connection.create_market_order(
            symbol=symbol,
            action_type=action,
            volume=volume,
            stop_loss=stop_loss,
            take_profit=take_profit,
            options={"comment": comment[:31]},  # MT5 comment max 31 chars
        )
        result["success"] = True
        result["order_id"] = order_result.get("orderId") or order_result.get("order_id")
        logger.info(
            "[mt5_client] Order placed: symbol=%s dir=%s vol=%.2f order_id=%s",
            symbol, direction, volume, result["order_id"],
        )
    except Exception as exc:
        result["error"] = str(exc)
        logger.error("[mt5_client] execute_trade failed symbol=%s: %s", symbol, exc)

    return result


async def update_stop_loss(
    account_id: str,
    order_id: str,
    new_sl: float,
) -> bool:
    """Modify an open position's stop-loss (e.g. move to break-even after TP1)."""
    account = await _get_account(account_id)
    if account is None:
        return False
    try:
        if account.state not in ("DEPLOYED", "DEPLOYING"):
            await account.deploy()
        connection = account.get_rpc_connection()
        await connection.connect()
        await connection.wait_synchronized()
        await connection.modify_position(order_id, stop_loss=new_sl)
        logger.info("[mt5_client] SL updated: order_id=%s new_sl=%.5f", order_id, new_sl)
        return True
    except Exception as exc:
        logger.error("[mt5_client] update_stop_loss failed order_id=%s: %s", order_id, exc)
        return False


# ---------------------------------------------------------------------------
# Credential management helpers (used by /mt5_link command)
# ---------------------------------------------------------------------------

async def link_mt5_account(
    telegram_user_id: int,
    mt5_login: str,
    mt5_password: str,
    mt5_server: str,
) -> Dict[str, Any]:
    """Provision a MetaApi account for the user and save encrypted credentials to DB.

    Returns dict with: success, metaapi_account_id, error.
    """
    from services.security import encrypt_secret, is_encryption_available
    from db.session import get_session
    from db.repository import get_or_create_user

    result: Dict[str, Any] = {"success": False, "metaapi_account_id": None, "error": None}

    if not is_encryption_available():
        result["error"] = "Encryption not configured (ENCRYPTION_KEY missing)"
        return result

    encrypted_pw = encrypt_secret(mt5_password)
    if not encrypted_pw:
        result["error"] = "Failed to encrypt password"
        return result

    metaapi_account_id: Optional[str] = None

    # Optionally provision on MetaApi cloud
    if _METAAPI_AVAILABLE:
        token = (os.getenv("META_API_TOKEN") or "").strip()
        if token:
            try:
                domain = os.getenv("META_API_DOMAIN")
                api = MetaApi(token, {"domain": domain} if domain else {})
                account = await api.metatrader_account_api.create_account({
                    "name": f"SignalRankAI-{telegram_user_id}",
                    "type": "cloud",
                    "login": mt5_login,
                    "password": mt5_password,
                    "server": mt5_server,
                    "platform": "mt5",
                    "magic": 12345,
                })
                metaapi_account_id = account.id
                logger.info(
                    "[mt5_client] MetaApi account provisioned: user=%d account_id=%s",
                    telegram_user_id, metaapi_account_id,
                )
            except Exception as exc:
                logger.warning("[mt5_client] MetaApi provisioning failed (will save creds only): %s", exc)

    # Persist to Postgres
    try:
        async with get_session() as session:
            user = await get_or_create_user(session, telegram_user_id=telegram_user_id)
            from sqlalchemy import text
            await session.execute(
                text(
                    """
                    INSERT INTO mt5_credentials (user_id, mt5_login, password_encrypted, server, metaapi_account_id, created_at, updated_at)
                    VALUES (:uid, :login, :pw_enc, :server, :ma_id, NOW(), NOW())
                    ON CONFLICT (user_id) DO UPDATE
                        SET mt5_login = EXCLUDED.mt5_login,
                            password_encrypted = EXCLUDED.password_encrypted,
                            server = EXCLUDED.server,
                            metaapi_account_id = COALESCE(EXCLUDED.metaapi_account_id, mt5_credentials.metaapi_account_id),
                            updated_at = NOW()
                    """
                ),
                {
                    "uid": user.id,
                    "login": mt5_login,
                    "pw_enc": encrypted_pw,
                    "server": mt5_server,
                    "ma_id": metaapi_account_id,
                },
            )
            await session.commit()
            result["success"] = True
            result["metaapi_account_id"] = metaapi_account_id
    except Exception as exc:
        result["error"] = f"DB save failed: {exc}"
        logger.error("[mt5_client] Failed to save credentials for user %d: %s", telegram_user_id, exc)

    return result


async def get_user_mt5_account_id(telegram_user_id: int) -> Optional[str]:
    """Return the stored MetaApi account ID for a Telegram user, or None."""
    try:
        from db.session import get_session
        from sqlalchemy import text
        async with get_session() as session:
            row = await session.execute(
                text(
                    """
                    SELECT c.metaapi_account_id
                    FROM mt5_credentials c
                    JOIN users u ON u.id = c.user_id
                    WHERE u.telegram_user_id = :tid
                    """
                ),
                {"tid": telegram_user_id},
            )
            r = row.fetchone()
            return r[0] if r and r[0] else None
    except Exception:
        return None
