"""
services/mt5_client.py — Pure aiohttp REST bridge for MetaApi Cloud MT5 integration.

Uses the MetaApi cloud REST API v1 over aiohttp — no SDK dependency, fully
Linux-compatible, works on Railway.

Same public API:
    execute_trade, validate_slippage, get_live_price,
    link_mt5_account, get_user_mt5_account_id, update_stop_loss

Environment variables:
    META_API_TOKEN       — MetaApi cloud token (https://metaapi.cloud dashboard)
    META_API_DOMAIN      — Optional: domain override
                           (default: agiliumtrade.agiliumtrade.ai)
    META_API_REGION      — Optional: region prefix
                           (default: mt-client-api-v1)
    SLIPPAGE_TOLERANCE   — Max pips/points between signal price and live price
                           (default: 10)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _client_base(account_id: str | None = None) -> str:
    """Base URL for the MetaApi *client* REST API (prices + trading)."""
    domain = os.getenv("META_API_DOMAIN", "agiliumtrade.agiliumtrade.ai")
    region = os.getenv("META_API_REGION", "mt-client-api-v1")
    root = f"https://{region}.{domain}/users/current/accounts"
    return f"{root}/{account_id}" if account_id else root


def _provisioning_base() -> str:
    """Base URL for the MetaApi *provisioning* REST API (account management)."""
    domain = os.getenv("META_API_DOMAIN", "agiliumtrade.agiliumtrade.ai")
    return f"https://mt-provisioning-api-v1.{domain}/users/current/accounts"


def _headers() -> Dict[str, str]:
    token = (os.getenv("META_API_TOKEN") or "").strip()
    return {
        "auth-token": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _slippage_tolerance() -> float:
    try:
        return float(os.getenv("SLIPPAGE_TOLERANCE", "10"))
    except Exception:
        return 10.0


def _check_token() -> bool:
    if not (os.getenv("META_API_TOKEN") or "").strip():
        logger.error("[mt5_client] META_API_TOKEN is not set")
        return False
    return True


# ---------------------------------------------------------------------------
# Low-level HTTP helpers
# ---------------------------------------------------------------------------

async def _http_get(url: str, params: Dict | None = None) -> Optional[Dict]:
    """Authenticated GET → parsed JSON or None."""
    if not _check_token():
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=_headers(),
                params=params or {},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status in (200, 201):
                    return await resp.json()
                body = await resp.text()
                logger.error("[mt5_client] GET %s → %d  %s", url, resp.status, body[:200])
                return None
    except Exception as exc:
        logger.error("[mt5_client] GET %s failed: %s", url, exc)
        return None


async def _http_post(url: str, payload: Dict) -> Optional[Dict]:
    """Authenticated POST → parsed JSON or None."""
    if not _check_token():
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers=_headers(),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status in (200, 201, 204):
                    try:
                        return await resp.json()
                    except Exception:
                        return {"status": resp.status}
                body = await resp.text()
                logger.error("[mt5_client] POST %s → %d  %s", url, resp.status, body[:200])
                return None
    except Exception as exc:
        logger.error("[mt5_client] POST %s failed: %s", url, exc)
        return None


async def _http_put(url: str, payload: Dict) -> bool:
    """Authenticated PUT → True on success."""
    if not _check_token():
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.put(
                url,
                headers=_headers(),
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status in (200, 201, 204):
                    return True
                body = await resp.text()
                logger.error("[mt5_client] PUT %s → %d  %s", url, resp.status, body[:200])
                return False
    except Exception as exc:
        logger.error("[mt5_client] PUT %s failed: %s", url, exc)
        return False


async def _deploy_account(account_id: str) -> None:
    """Ensure the account is deployed (connected to MT5) before trading."""
    url = f"{_client_base(account_id)}/deploy"
    try:
        await _http_post(url, {})
    except Exception as exc:
        logger.debug("[mt5_client] deploy_account %s: %s", account_id, exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_live_price(account_id: str, symbol: str) -> Optional[float]:
    """Return the current mid-price for *symbol* via MetaApi REST."""
    await _deploy_account(account_id)
    url = f"{_client_base(account_id)}/symbols/{symbol}/current-price"
    data = await _http_get(url)
    if not data:
        return None
    try:
        bid = float(data.get("bid") or 0)
        ask = float(data.get("ask") or 0)
        mid = (bid + ask) / 2.0 if bid and ask else (bid or ask)
        return mid or None
    except Exception as exc:
        logger.error("[mt5_client] get_live_price parse error symbol=%s: %s", symbol, exc)
        return None


async def validate_slippage(
    account_id: str,
    symbol: str,
    signal_price: float,
) -> Tuple[bool, float, Optional[float]]:
    """Check whether the live price is within slippage tolerance.

    Returns:
        (within_tolerance, slippage_points, live_price)
    """
    live = await get_live_price(account_id, symbol)
    if live is None:
        logger.warning("[mt5_client] validate_slippage: no live price for %s — allowing", symbol)
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
    """Place a market order via MetaApi REST.

    Args:
        account_id:   MetaApi account ID.
        symbol:       MT5 symbol (e.g. ``"BTCUSD"``, ``"EURUSD"``).
        direction:    ``"long"`` or ``"short"``.
        volume:       Lot size.
        stop_loss:    Stop-loss price.
        take_profit:  Take-profit price.
        signal_entry: Original signal entry price (slippage reference).
        comment:      Order comment tag (MT5 max 31 chars).

    Returns:
        ``dict`` with keys: ``success``, ``order_id``, ``live_price``,
        ``slippage``, ``error``.
    """
    result: Dict[str, Any] = {
        "success": False,
        "order_id": None,
        "live_price": None,
        "slippage": None,
        "error": None,
        "hard_stop_attached": False,
    }

    # Phase 1 hard-stop protection: never place an order without broker-side SL.
    try:
        if float(stop_loss or 0) <= 0:
            result["error"] = "Hard stop-loss is required for broker-side protection"
            return result
        if float(take_profit or 0) <= 0:
            result["error"] = "Take-profit is required for managed execution"
            return result
    except Exception:
        result["error"] = "Invalid stop-loss/take-profit values"
        return result

    # 1. Slippage guard
    ok, slippage, live_price = await validate_slippage(account_id, symbol, signal_entry)
    result["live_price"] = live_price
    result["slippage"] = slippage

    if not ok:
        result["error"] = (
            f"Slippage too high: {slippage:.4f} pts "
            f"(tolerance: {_slippage_tolerance():.0f})"
        )
        logger.warning(
            "[mt5_client] execute_trade rejected — slippage=%.4f > tol=%.0f  "
            "symbol=%s entry=%.5f live=%.5f",
            slippage, _slippage_tolerance(), symbol, signal_entry, live_price or 0,
        )
        return result

    # 2. Submit market order via REST
    await _deploy_account(account_id)
    url = f"{_client_base(account_id)}/trade"
    action = "ORDER_TYPE_BUY" if str(direction).lower() == "long" else "ORDER_TYPE_SELL"
    payload = {
        "actionType": action,
        "symbol": symbol,
        "volume": volume,
        "stopLoss": stop_loss,
        "takeProfit": take_profit,
        "comment": comment[:31],
    }
    result["hard_stop_attached"] = True
    data = await _http_post(url, payload)
    if data is None:
        result["error"] = "MetaApi trade request failed (see logs)"
        return result

    result["success"] = True
    result["order_id"] = (
        data.get("orderId") or data.get("order_id") or data.get("positionId")
    )
    logger.info(
        "[mt5_client] Order placed: symbol=%s dir=%s vol=%.2f order_id=%s",
        symbol, direction, volume, result["order_id"],
    )
    return result


async def close_position(
    account_id: str,
    position_id: str,
    volume: float | None = None,
    comment: str = "SignalRankAI-SmartExit",
) -> Dict[str, Any]:
    """Attempt to close an MT5 position using MetaApi REST.

    Uses multiple API payload variants for compatibility across bridge versions.
    """
    result: Dict[str, Any] = {
        "success": False,
        "position_id": str(position_id or ""),
        "error": None,
    }
    if not str(account_id or "").strip() or not str(position_id or "").strip():
        result["error"] = "account_id and position_id are required"
        return result

    await _deploy_account(account_id)

    # Variant A: dedicated close endpoint.
    try:
        close_url = f"{_client_base(account_id)}/positions/{position_id}/close"
        data = await _http_post(close_url, {"comment": comment[:31]})
        if data is not None:
            result["success"] = True
            return result
    except Exception as exc:
        logger.debug("[mt5_client] close endpoint failed position=%s: %s", position_id, exc)

    # Variant B: trade action payload.
    payload = {
        "actionType": "POSITION_CLOSE_ID",
        "positionId": str(position_id),
        "comment": comment[:31],
    }
    if volume is not None and float(volume) > 0:
        payload["volume"] = float(volume)
    data = await _http_post(f"{_client_base(account_id)}/trade", payload)
    if data is not None:
        result["success"] = True
        return result

    result["error"] = "MetaApi position close failed"
    return result


async def update_stop_loss(
    account_id: str,
    position_id: str,
    new_sl: float,
) -> bool:
    """Move stop-loss on an open position (e.g. break-even after TP1)."""
    url = f"{_client_base(account_id)}/positions/{position_id}"
    ok = await _http_put(url, {"stopLoss": new_sl})
    if ok:
        logger.info("[mt5_client] SL updated  position_id=%s  new_sl=%.5f", position_id, new_sl)
    else:
        logger.error("[mt5_client] update_stop_loss failed  position_id=%s", position_id)
    return ok


# ---------------------------------------------------------------------------
# Credential management (used by /mt5_link command)
# ---------------------------------------------------------------------------

async def link_mt5_account(
    telegram_user_id: int,
    mt5_login: str,
    mt5_password: str,
    mt5_server: str,
) -> Dict[str, Any]:
    """Provision a MetaApi account for *telegram_user_id* and persist credentials.

    Returns ``dict`` with keys: ``success``, ``metaapi_account_id``, ``error``.
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

    # --- Provision on MetaApi cloud ----------------------------------------
    if _check_token():
        try:
            url = _provisioning_base()
            payload = {
                "name": f"SignalRankAI-{telegram_user_id}",
                "type": "cloud",
                "login": mt5_login,
                "password": mt5_password,
                "server": mt5_server,
                "platform": "mt5",
                "magic": 12345,
            }
            data = await _http_post(url, payload)
            if data and data.get("id"):
                metaapi_account_id = data["id"]
                logger.info(
                    "[mt5_client] MetaApi account provisioned: user=%d  account_id=%s",
                    telegram_user_id, metaapi_account_id,
                )
            else:
                logger.warning(
                    "[mt5_client] MetaApi provisioning returned no account ID "
                    "— credentials will be saved locally only"
                )
        except Exception as exc:
            logger.warning("[mt5_client] MetaApi provisioning failed: %s", exc)

    # --- Persist to Postgres -------------------------------------------------
    try:
        async with get_session() as session:
            user = await get_or_create_user(session, telegram_user_id=telegram_user_id)
            from sqlalchemy import text
            await session.execute(
                text(
                    """
                    INSERT INTO mt5_credentials
                        (user_id, mt5_login, password_encrypted, server,
                         metaapi_account_id, created_at, updated_at)
                    VALUES (:uid, :login, :pw_enc, :server, :ma_id, NOW(), NOW())
                    ON CONFLICT (user_id) DO UPDATE
                        SET mt5_login            = EXCLUDED.mt5_login,
                            password_encrypted   = EXCLUDED.password_encrypted,
                            server               = EXCLUDED.server,
                            metaapi_account_id   = COALESCE(
                                                       EXCLUDED.metaapi_account_id,
                                                       mt5_credentials.metaapi_account_id),
                            updated_at           = NOW()
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
        logger.error(
            "[mt5_client] Failed to save credentials for user %d: %s",
            telegram_user_id, exc,
        )

    return result


async def get_user_mt5_account_id(telegram_user_id: int) -> Optional[str]:
    """Return the stored MetaApi account ID for a Telegram user, or ``None``."""
    try:
        from db.session import get_session
        from sqlalchemy import text
        async with get_session() as session:
            row = await session.execute(
                text(
                    """
                    SELECT c.metaapi_account_id
                    FROM   mt5_credentials c
                    JOIN   users u ON u.id = c.user_id
                    WHERE  u.telegram_user_id = :tid
                    """
                ),
                {"tid": telegram_user_id},
            )
            r = row.fetchone()
            return r[0] if r and r[0] else None
    except Exception:
        return None
