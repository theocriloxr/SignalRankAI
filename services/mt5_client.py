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

import math
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import aiohttp

from core.security import redact_secrets

logger = logging.getLogger(__name__)


def _safe_error_body(body: str) -> str:
    """Return bounded, redacted provider diagnostics without secret leakage."""
    try:
        import json

        parsed = json.loads(str(body or ""))
        return str(redact_secrets(parsed))[:200]
    except Exception:
        # Plain-text provider responses may echo request credentials.  Status
        # and URL are sufficient diagnostics; never log arbitrary body text.
        return "<non-json provider response>"

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


def _quote_max_age_seconds() -> float:
    try:
        value = float(os.getenv("BROKER_QUOTE_MAX_AGE_SECONDS", "15"))
    except Exception:
        value = 15.0
    return max(1.0, min(value, 120.0))


def _check_token() -> bool:
    if not (os.getenv("META_API_TOKEN") or "").strip():
        logger.error("[mt5_client] META_API_TOKEN is not set")
        return False
    return True


# ---------------------------------------------------------------------------
# Low-level HTTP helpers
# ---------------------------------------------------------------------------

async def _http_get(url: str, params: Dict | None = None) -> Optional[Any]:
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
                logger.error("[mt5_client] GET %s → %d  %s", url, resp.status, _safe_error_body(body))
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
                logger.error("[mt5_client] POST %s → %d  %s", url, resp.status, _safe_error_body(body))
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
                logger.error("[mt5_client] PUT %s → %d  %s", url, resp.status, _safe_error_body(body))
                return False
    except Exception as exc:
        logger.error("[mt5_client] PUT %s failed: %s", url, exc)
        return False


async def _deploy_account(account_id: str) -> None:
    """Ensure the account is deployed (connected to MT5) before trading."""
    url = f"{_provisioning_base()}/{account_id}/deploy"
    try:
        await _http_post(url, {})
    except Exception as exc:
        logger.debug("[mt5_client] deploy_account %s: %s", account_id, exc)


def _parse_provider_timestamp(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            raw = float(value)
            if raw > 10_000_000_000:
                raw /= 1000.0
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        raw = str(value).strip()
        if not raw:
            return None
        if raw.replace(".", "", 1).isdigit():
            return _parse_provider_timestamp(float(raw))
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            # MetaApi's canonical ``time`` field is UTC. A timezone-less
            # brokerTime is deliberately not selected by get_live_quote.
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _classify_demo_account(*payloads: Dict[str, Any]) -> Optional[bool]:
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key in ("isDemo", "is_demo", "demo"):
            value = payload.get(key)
            if isinstance(value, bool):
                return value
            if str(value).strip().lower() in {"1", "true", "yes"}:
                return True
            if str(value).strip().lower() in {"0", "false", "no"}:
                return False
        for key in (
            "accountType",
            "account_type",
            "environment",
            "mode",
            "server",
            "name",
        ):
            value = str(payload.get(key) or "").strip().lower()
            if not value:
                continue
            if "demo" in value or "paper" in value or "sandbox" in value:
                return True
            if "live" in value or "real" in value:
                return False
    return None


def _account_connection_ready(*payloads: Dict[str, Any]) -> bool:
    observed = False
    positive = False
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key in ("connectionStatus", "connection_status", "state", "status"):
            value = str(payload.get(key) or "").strip().lower()
            if not value:
                continue
            observed = True
            if value in {
                "connected",
                "deployed",
                "synchronized",
                "ready",
                "active",
            }:
                positive = True
            if value in {
                "disconnected",
                "undeployed",
                "deploying",
                "synchronizing",
                "failed",
                "error",
                "deleted",
                "inactive",
            }:
                return False
    if positive:
        return True
    # Account-information is only served by a connected terminal. If no
    # explicit state was returned, valid account numbers still prove readiness.
    if not observed:
        for payload in payloads:
            if isinstance(payload, dict) and (
                payload.get("accountNumber")
                or payload.get("login")
                or payload.get("currency")
            ):
                return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_account_info(account_id: str) -> Optional[Dict[str, Any]]:
    """Return normalized MetaApi account information used by risk sizing.

    Missing equity, free-margin, connection state, or demo/live
    classification remains visible to callers and therefore blocks execution.
    No synthetic balance/equity values are supplied.
    """
    account_id = str(account_id or "").strip()
    if not account_id:
        return None
    await _deploy_account(account_id)
    information = await _http_get(f"{_client_base(account_id)}/account-information")
    if not isinstance(information, dict):
        return None

    # Provisioning metadata carries the server/account environment while the
    # client endpoint carries balance/equity/margin. Failure to fetch metadata
    # does not fabricate a classification; ``is_demo`` stays None.
    provisioning = await _http_get(f"{_provisioning_base()}/{account_id}")
    provisioning = provisioning if isinstance(provisioning, dict) else {}

    normalized: Dict[str, Any] = dict(information)
    for source, target in (
        ("freeMargin", "free_margin"),
        ("marginFree", "free_margin"),
        ("accountNumber", "account_number"),
        ("connectionStatus", "connection_status"),
    ):
        if source in normalized and target not in normalized:
            normalized[target] = normalized[source]
    for key in ("balance", "equity", "margin", "free_margin", "leverage"):
        if key not in normalized:
            continue
        try:
            value = float(normalized[key])
            normalized[key] = value if math.isfinite(value) else None
        except (TypeError, ValueError):
            normalized[key] = None

    normalized["is_demo"] = _classify_demo_account(information, provisioning)
    normalized["connected"] = _account_connection_ready(information, provisioning)
    normalized["server"] = (
        information.get("server")
        or provisioning.get("server")
        or provisioning.get("broker")
    )
    normalized["provider"] = "metaapi"
    return normalized


async def get_symbol_specification(
    account_id: str,
    symbol: str,
) -> Optional[Dict[str, Any]]:
    """Return normalized broker symbol limits required for safe sizing."""
    account_id = str(account_id or "").strip()
    symbol = str(symbol or "").strip().upper()
    if not account_id or not symbol:
        return None
    await _deploy_account(account_id)
    data = await _http_get(
        f"{_client_base(account_id)}/symbols/{symbol}/specification"
    )
    if not isinstance(data, dict):
        return None
    normalized: Dict[str, Any] = dict(data)
    aliases = {
        "contractSize": "contract_size",
        "tickSize": "tick_size",
        "tickValue": "tick_value",
        "minVolume": "min_volume",
        "maxVolume": "max_volume",
        "volumeStep": "volume_step",
        "tradeAllowed": "trade_allowed",
    }
    for source, target in aliases.items():
        if source in normalized and target not in normalized:
            normalized[target] = normalized[source]
    for key in (
        "contract_size",
        "tick_size",
        "tick_value",
        "min_volume",
        "max_volume",
        "volume_step",
    ):
        try:
            value = float(normalized.get(key))
            normalized[key] = value if math.isfinite(value) else None
        except (TypeError, ValueError):
            normalized[key] = None
    trade_allowed = normalized.get("trade_allowed")
    if isinstance(trade_allowed, str):
        normalized["trade_allowed"] = trade_allowed.strip().lower() in {
            "1",
            "true",
            "yes",
            "enabled",
            "full",
        }
    elif trade_allowed is not None:
        normalized["trade_allowed"] = bool(trade_allowed)
    normalized["symbol"] = str(data.get("symbol") or symbol).upper()
    normalized["provider"] = "metaapi"
    return normalized


async def get_live_quote(
    account_id: str,
    symbol: str,
) -> Optional[Dict[str, Any]]:
    """Return a timestamped, broker-native quote with trust/freshness fields."""
    account_id = str(account_id or "").strip()
    symbol = str(symbol or "").strip().upper()
    if not account_id or not symbol:
        return None
    await _deploy_account(account_id)
    url = f"{_client_base(account_id)}/symbols/{symbol}/current-price"
    data = await _http_get(url)
    if not isinstance(data, dict):
        return None
    try:
        bid = float(data.get("bid"))
        ask = float(data.get("ask"))
    except (TypeError, ValueError):
        return None
    if (
        not math.isfinite(bid)
        or not math.isfinite(ask)
        or bid <= 0
        or ask <= 0
        or ask < bid
    ):
        return None

    # Require the provider's UTC timestamp. brokerTime may be in an arbitrary
    # terminal timezone and cannot prove freshness without its offset.
    quoted_at = None
    for key in ("time", "timestamp", "serverTime", "server_time"):
        quoted_at = _parse_provider_timestamp(data.get(key))
        if quoted_at is not None:
            break
    if quoted_at is None:
        return None
    age_seconds = (datetime.now(timezone.utc) - quoted_at).total_seconds()
    if age_seconds < -5:
        return None
    age_seconds = max(0.0, age_seconds)
    max_age = _quote_max_age_seconds()
    mid = (bid + ask) / 2.0
    return {
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread": ask - bid,
        "quoted_at": quoted_at,
        "age_seconds": age_seconds,
        "max_age_seconds": max_age,
        "trusted": age_seconds <= max_age,
        "provider": "metaapi",
        "raw": data,
    }


async def get_live_price(account_id: str, symbol: str) -> Optional[float]:
    """Return a fresh trusted mid-price for *symbol* via MetaApi REST."""
    quote = await get_live_quote(account_id, symbol)
    if not quote or not quote.get("trusted"):
        return None
    return float(quote["mid"])


async def validate_slippage(
    account_id: str,
    symbol: str,
    signal_price: float,
) -> Tuple[bool, float, Optional[float]]:
    """Check whether the live price is within slippage tolerance.

    Returns:
        (within_tolerance, slippage_points, live_price)
    """
    quote = await get_live_quote(account_id, symbol)
    if not quote or not quote.get("trusted"):
        logger.warning(
            "[mt5_client] validate_slippage: missing/stale broker quote for %s - blocking",
            symbol,
        )
        return False, float("inf"), None
    live = float(quote["mid"])
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
    *,
    execution_authorized: bool = False,
    idempotency_key: str | None = None,
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

    # Defense in depth: direct adapter calls cannot bypass ExecutionGate.
    if not execution_authorized:
        result["error"] = "ExecutionGate authorization is required"
        return result
    if not str(idempotency_key or "").strip():
        result["error"] = "A durable execution idempotency key is required"
        return result
    account_id = str(account_id or "").strip()
    symbol = str(symbol or "").strip().upper()
    direction_norm = str(direction or "").strip().lower()
    if not account_id or not symbol:
        result["error"] = "account_id and symbol are required"
        return result
    if direction_norm not in {"long", "buy", "short", "sell"}:
        result["error"] = "direction must be long/buy or short/sell"
        return result

    # Phase 1 hard-stop protection: never place an order without broker-side SL.
    try:
        volume = float(volume)
        signal_entry = float(signal_entry)
        stop_loss = float(stop_loss)
        take_profit = float(take_profit)
        if (
            not all(
                math.isfinite(value)
                for value in (volume, signal_entry, stop_loss, take_profit)
            )
            or volume <= 0
            or signal_entry <= 0
        ):
            result["error"] = "Invalid execution price or volume"
            return result
        if stop_loss <= 0:
            result["error"] = "Hard stop-loss is required for broker-side protection"
            return result
        if take_profit <= 0:
            result["error"] = "Take-profit is required for managed execution"
            return result
        if direction_norm in {"long", "buy"} and not (
            stop_loss < signal_entry < take_profit
        ):
            result["error"] = "Invalid long entry/stop/take-profit geometry"
            return result
        if direction_norm in {"short", "sell"} and not (
            take_profit < signal_entry < stop_loss
        ):
            result["error"] = "Invalid short entry/stop/take-profit geometry"
            return result
    except Exception:
        result["error"] = "Invalid execution values"
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
    action = (
        "ORDER_TYPE_BUY"
        if direction_norm in {"long", "buy"}
        else "ORDER_TYPE_SELL"
    )
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

    result["order_id"] = (
        data.get("orderId") or data.get("order_id") or data.get("positionId")
    )
    if not result["order_id"]:
        result["error"] = "MetaApi acknowledged submission without an order identifier"
        result["status"] = "AMBIGUOUS"
        return result
    result["success"] = True
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


async def get_open_positions_snapshot(
    account_id: str,
) -> Optional[list[dict[str, Any]]]:
    """Return positions, preserving ``None`` when reconciliation is unavailable."""
    if not str(account_id or "").strip():
        return None

    await _deploy_account(account_id)

    for _path in ("/positions", "/trading-positions"):
        try:
            data = await _http_get(f"{_client_base(account_id)}{_path}")
            if isinstance(data, list):
                return [dict(x) for x in data if isinstance(x, dict)]
            if isinstance(data, dict):
                arr = data.get("positions") or data.get("data") or data.get("items")
                if isinstance(arr, list):
                    return [dict(x) for x in arr if isinstance(x, dict)]
        except Exception as exc:
            logger.debug("[mt5_client] list_open_positions path=%s failed: %s", _path, exc)

    return None


async def list_open_positions(account_id: str) -> list[dict[str, Any]]:
    """Return current open positions for a MetaApi account.

    Compatibility callers receive an empty list on provider failure. Execution
    preflight uses :func:`get_reconciliation_snapshot`, which preserves and
    blocks on that unavailable state.
    """
    positions = await get_open_positions_snapshot(account_id)
    return positions if positions is not None else []


async def get_reconciliation_snapshot(
    account_id: str,
    *,
    account_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Prove account and position reconciliation endpoints are available."""
    info = account_info if isinstance(account_info, dict) else await get_account_info(account_id)
    positions = await get_open_positions_snapshot(account_id)
    ready = bool(
        isinstance(info, dict)
        and info.get("connected") is True
        and positions is not None
    )
    return {
        "ready": ready,
        "checked_at": datetime.now(timezone.utc),
        "account_info": info,
        "positions": positions,
        "provider": "metaapi",
    }


def _position_id_from_row(row: dict[str, Any]) -> str:
    for key in ("id", "positionId", "position_id", "orderId", "order_id"):
        val = row.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


async def close_all_positions(account_id: str, comment: str = "SignalRankAI-KillSwitch") -> Dict[str, Any]:
    """Close all currently open positions for a MetaApi account."""
    result: Dict[str, Any] = {
        "success": True,
        "attempted": 0,
        "closed": 0,
        "failed": 0,
        "errors": [],
    }
    positions = await list_open_positions(account_id)
    if not positions:
        return result

    result["attempted"] = len(positions)
    for row in positions:
        pid = _position_id_from_row(row)
        if not pid:
            result["failed"] += 1
            result["errors"].append("missing_position_id")
            continue
        vol = row.get("volume")
        try:
            close_res = await close_position(account_id, pid, volume=float(vol) if vol is not None else None, comment=comment)
            if close_res.get("success"):
                result["closed"] += 1
            else:
                result["failed"] += 1
                result["errors"].append(str(close_res.get("error") or f"close_failed:{pid}"))
        except Exception as exc:
            result["failed"] += 1
            result["errors"].append(str(exc))

    result["success"] = result["failed"] == 0
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

    result: Dict[str, Any] = {
        "success": False,
        "credentials_saved": False,
        "executable": False,
        "metaapi_account_id": None,
        "error": None,
    }

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
            result["credentials_saved"] = True
            result["executable"] = bool(metaapi_account_id)
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


async def ensure_user_mt5_account_id(telegram_user_id: int) -> Optional[str]:
    """Return an executable MetaApi account id, reprovisioning saved MT5 credentials if needed."""
    existing = await get_user_mt5_account_id(int(telegram_user_id))
    if existing:
        return existing
    if not _check_token():
        return None
    try:
        from db.session import get_session
        from services.security import decrypt_secret
        from sqlalchemy import text

        async with get_session() as session:
            row = await session.execute(
                text(
                    """
                    SELECT c.mt5_login, c.password_encrypted, c.server
                    FROM   mt5_credentials c
                    JOIN   users u ON u.id = c.user_id
                    WHERE  u.telegram_user_id = :tid
                    ORDER BY c.updated_at DESC NULLS LAST, c.created_at DESC NULLS LAST
                    LIMIT 1
                    """
                ),
                {"tid": int(telegram_user_id)},
            )
            found = row.fetchone()
        if not found:
            return None
        password = decrypt_secret(str(found[1] or ""))
        if not password:
            logger.warning("[mt5_client] saved MT5 credentials could not be decrypted for user=%s", telegram_user_id)
            return None
        result = await link_mt5_account(
            telegram_user_id=int(telegram_user_id),
            mt5_login=str(found[0] or ""),
            mt5_password=password,
            mt5_server=str(found[2] or ""),
        )
        return str(result.get("metaapi_account_id") or "").strip() or None
    except Exception:
        logger.debug("[mt5_client] ensure account id failed", exc_info=True)
        return None


async def get_user_mt5_link_status(telegram_user_id: int) -> Dict[str, Any]:
    """Return MT5 linked/executable state for a Telegram user."""
    status: Dict[str, Any] = {
        "linked": False,
        "executable": False,
        "metaapi_account_id": None,
        "mt5_login": None,
        "server": None,
    }
    try:
        from db.session import get_session
        from sqlalchemy import text
        async with get_session() as session:
            row = await session.execute(
                text(
                    """
                    SELECT c.mt5_login, c.server, c.metaapi_account_id
                    FROM   mt5_credentials c
                    JOIN   users u ON u.id = c.user_id
                    WHERE  u.telegram_user_id = :tid
                    ORDER BY c.updated_at DESC NULLS LAST, c.created_at DESC NULLS LAST
                    LIMIT 1
                    """
                ),
                {"tid": int(telegram_user_id)},
            )
            found = row.fetchone()
        if not found:
            return status
        status["linked"] = True
        status["mt5_login"] = found[0]
        status["server"] = found[1]
        status["metaapi_account_id"] = found[2]
        status["executable"] = bool(found[2])

        # Credentials may be saved while MetaApi provisioning was temporarily
        # unavailable. Re-attempt provisioning on status checks when possible.
        if status["linked"] and not status["executable"]:
            recovered_account_id = await ensure_user_mt5_account_id(int(telegram_user_id))
            if recovered_account_id:
                status["metaapi_account_id"] = recovered_account_id
                status["executable"] = True
    except Exception:
        logger.debug("[mt5_client] get link status failed", exc_info=True)
    return status



async def link_platform_mt5_account(
    user_id: int,
    mt5_login: str,
    mt5_password: str,
    mt5_server: str,
) -> Dict[str, Any]:
    """Link MT5 credentials directly to the canonical platform user.

    This is the web/mobile counterpart to link_mt5_account. Credentials are
    encrypted before persistence and the plaintext password is never returned
    or logged.
    """
    from services.security import encrypt_secret, is_encryption_available
    from db.session import get_session
    from sqlalchemy import text

    result: Dict[str, Any] = {
        "success": False,
        "credentials_saved": False,
        "executable": False,
        "metaapi_account_id": None,
        "error": None,
    }
    canonical_id = int(user_id)
    login = str(mt5_login or "").strip()
    server = str(mt5_server or "").strip()
    password = str(mt5_password or "")
    if not login or not server or not password:
        result["error"] = "MT5 login, password and server are required"
        return result
    if not is_encryption_available():
        result["error"] = "Encryption not configured (ENCRYPTION_KEY missing)"
        return result
    encrypted_pw = encrypt_secret(password)
    if not encrypted_pw:
        result["error"] = "Failed to encrypt password"
        return result

    metaapi_account_id: Optional[str] = None
    if _check_token():
        try:
            data = await _http_post(
                _provisioning_base(),
                {
                    "name": f"SignalRankAI-user-{canonical_id}",
                    "type": "cloud",
                    "login": login,
                    "password": password,
                    "server": server,
                    "platform": "mt5",
                    "magic": 12345,
                },
            )
            if data and data.get("id"):
                metaapi_account_id = str(data["id"])
            else:
                logger.warning(
                    "[mt5_client] platform MetaApi provisioning returned no account ID user=%s",
                    canonical_id,
                )
        except Exception as exc:
            logger.warning(
                "[mt5_client] platform MetaApi provisioning failed user=%s err=%s",
                canonical_id,
                type(exc).__name__,
            )

    try:
        async with get_session(label="mt5.platform.link", timeout_seconds=10.0) as session:
            exists = (
                await session.execute(
                    text("SELECT 1 FROM users WHERE id=:uid LIMIT 1"),
                    {"uid": canonical_id},
                )
            ).scalar_one_or_none()
            if exists is None:
                result["error"] = "Canonical user not found"
                return result
            await session.execute(
                text(
                    """
                    INSERT INTO mt5_credentials
                        (user_id, mt5_login, password_encrypted, server,
                         metaapi_account_id, created_at, updated_at)
                    VALUES (:uid, :login, :pw_enc, :server, :ma_id, NOW(), NOW())
                    ON CONFLICT (user_id) DO UPDATE
                        SET mt5_login=EXCLUDED.mt5_login,
                            password_encrypted=EXCLUDED.password_encrypted,
                            server=EXCLUDED.server,
                            metaapi_account_id=COALESCE(
                                EXCLUDED.metaapi_account_id,
                                mt5_credentials.metaapi_account_id
                            ),
                            updated_at=NOW()
                    """
                ),
                {
                    "uid": canonical_id,
                    "login": login,
                    "pw_enc": encrypted_pw,
                    "server": server,
                    "ma_id": metaapi_account_id,
                },
            )
            await session.commit()
        result.update(
            {
                "success": True,
                "credentials_saved": True,
                "executable": bool(metaapi_account_id),
                "metaapi_account_id": metaapi_account_id,
            }
        )
    except Exception as exc:
        result["error"] = f"DB save failed: {type(exc).__name__}"
        logger.error(
            "[mt5_client] platform credential save failed user=%s err=%s",
            canonical_id,
            type(exc).__name__,
        )
    return result


async def get_platform_mt5_account_id(user_id: int) -> Optional[str]:
    """Return the stored executable MetaApi account ID for one canonical user."""
    try:
        from db.session import get_session
        from sqlalchemy import text

        async with get_session(label="mt5.platform.account_id", timeout_seconds=5.0) as session:
            value = (
                await session.execute(
                    text(
                        "SELECT metaapi_account_id FROM mt5_credentials "
                        "WHERE user_id=:uid LIMIT 1"
                    ),
                    {"uid": int(user_id)},
                )
            ).scalar_one_or_none()
            await session.rollback()
        return str(value).strip() if value else None
    except Exception:
        return None


async def ensure_platform_mt5_account_id(user_id: int) -> Optional[str]:
    """Re-provision saved canonical-user MT5 credentials when possible."""
    existing = await get_platform_mt5_account_id(int(user_id))
    if existing:
        return existing
    if not _check_token():
        return None
    try:
        from db.session import get_session
        from services.security import decrypt_secret
        from sqlalchemy import text

        async with get_session(label="mt5.platform.ensure", timeout_seconds=8.0) as session:
            found = (
                await session.execute(
                    text(
                        """
                        SELECT mt5_login,password_encrypted,server
                        FROM mt5_credentials
                        WHERE user_id=:uid
                        ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
                        LIMIT 1
                        """
                    ),
                    {"uid": int(user_id)},
                )
            ).first()
            await session.rollback()
        if not found:
            return None
        password = decrypt_secret(str(found[1] or ""))
        if not password:
            return None
        result = await link_platform_mt5_account(
            int(user_id),
            str(found[0] or ""),
            password,
            str(found[2] or ""),
        )
        return str(result.get("metaapi_account_id") or "").strip() or None
    except Exception:
        logger.debug("[mt5_client] platform ensure account id failed", exc_info=True)
        return None


async def get_platform_mt5_link_status(user_id: int) -> Dict[str, Any]:
    """Return canonical-user MT5 state without exposing encrypted credentials."""
    status: Dict[str, Any] = {
        "linked": False,
        "executable": False,
        "metaapi_account_id": None,
        "mt5_login": None,
        "server": None,
    }
    try:
        from db.session import get_session
        from sqlalchemy import text

        async with get_session(label="mt5.platform.status", timeout_seconds=5.0) as session:
            found = (
                await session.execute(
                    text(
                        """
                        SELECT mt5_login,server,metaapi_account_id
                        FROM mt5_credentials
                        WHERE user_id=:uid
                        ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
                        LIMIT 1
                        """
                    ),
                    {"uid": int(user_id)},
                )
            ).first()
            await session.rollback()
        if not found:
            return status
        status.update(
            {
                "linked": True,
                "mt5_login": str(found[0] or ""),
                "server": str(found[1] or ""),
                "metaapi_account_id": str(found[2] or "") or None,
                "executable": bool(found[2]),
            }
        )
        if status["linked"] and not status["executable"]:
            recovered = await ensure_platform_mt5_account_id(int(user_id))
            if recovered:
                status["metaapi_account_id"] = recovered
                status["executable"] = True
    except Exception:
        logger.debug("[mt5_client] platform link status failed", exc_info=True)
    return status


# ---------------------------------------------------------------------------
# Provider-neutral MetaTrader connection helpers (MT4 + MT5)
# ---------------------------------------------------------------------------

async def _provision_metatrader_account(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create one MetaApi MT4/MT5 account without automatic retries.

    MetaApi can bill repeated invalid broker-auth attempts. A single request is
    therefore made per explicit user action; pending broker discovery is
    surfaced to the caller instead of being looped automatically.
    """
    if not _check_token():
        return {"success": False, "error": "META_API_TOKEN is not configured"}
    from uuid import uuid4

    headers = _headers()
    headers["transaction-id"] = uuid4().hex
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _provisioning_base(),
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=45),
            ) as resp:
                body = await resp.text()
                if resp.status in (200, 201):
                    try:
                        data = await resp.json()
                    except Exception:
                        data = {}
                    return {"success": True, "pending": False, "data": data}
                if resp.status == 202:
                    try:
                        data = await resp.json()
                    except Exception:
                        data = {}
                    return {
                        "success": True,
                        "pending": True,
                        "data": data,
                        "retry_after": resp.headers.get("Retry-After"),
                    }
                return {
                    "success": False,
                    "error": f"MetaApi provisioning failed ({resp.status})",
                    "diagnostic": _safe_error_body(body),
                }
    except Exception as exc:
        logger.warning(
            "[metatrader] provisioning request failed err=%s",
            type(exc).__name__,
        )
        return {"success": False, "error": f"MetaApi unavailable: {type(exc).__name__}"}


async def _create_configuration_link(
    account_id: str,
    *,
    ttl_days: int = 3,
) -> Dict[str, Any]:
    """Return a provider-hosted credential-entry link for one MetaApi account."""
    if not _check_token():
        return {"success": False, "error": "META_API_TOKEN is not configured"}
    account_id = str(account_id or "").strip()
    if not account_id:
        return {"success": False, "error": "MetaApi account id is required"}
    ttl = max(1, min(14, int(ttl_days)))
    url = f"{_provisioning_base()}/{account_id}/configuration-link"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.put(
                url,
                headers=_headers(),
                params={"ttlInDays": ttl},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                body = await resp.text()
                if resp.status == 200:
                    try:
                        data = await resp.json()
                    except Exception:
                        data = {}
                    link = str(data.get("configurationLink") or "").strip()
                    if link:
                        return {"success": True, "configuration_link": link}
                return {
                    "success": False,
                    "error": f"MetaApi configuration link failed ({resp.status})",
                    "diagnostic": _safe_error_body(body),
                }
    except Exception as exc:
        return {"success": False, "error": f"MetaApi unavailable: {type(exc).__name__}"}


def _environment_from_server(server: str, requested: str | None = None) -> str:
    requested_n = str(requested or "").strip().lower()
    if requested_n in {"demo", "live"}:
        return requested_n
    value = str(server or "").strip().lower()
    if "demo" in value or "practice" in value or "paper" in value:
        return "demo"
    if "live" in value or "real" in value:
        return "live"
    return "unknown"


async def link_platform_metatrader_account(
    user_id: int,
    *,
    platform: str,
    login: str,
    password: str,
    server: str,
    broker_name: str | None = None,
    account_label: str | None = None,
    environment: str = "unknown",
) -> Dict[str, Any]:
    """Link an MT4 or MT5 account to the canonical platform account."""
    import json as _json

    from services.broker_connections import upsert_connection
    from services.security import encrypt_secret, is_encryption_available

    platform_n = str(platform or "").strip().lower()
    if platform_n not in {"mt4", "mt5"}:
        return {"success": False, "error": "platform must be mt4 or mt5"}
    login_n = str(login or "").strip()
    password_n = str(password or "")
    server_n = str(server or "").strip()
    if not login_n or not password_n or not server_n:
        return {"success": False, "error": "login, password and broker server are required"}
    if not is_encryption_available():
        return {"success": False, "error": "Secure credential storage is unavailable"}

    secret_payload = _json.dumps(
        {
            "platform": platform_n,
            "login": login_n,
            "password": password_n,
            "server": server_n,
        },
        separators=(",", ":"),
    )
    encrypted = encrypt_secret(secret_payload)
    if not encrypted:
        return {"success": False, "error": "Failed to encrypt broker credentials"}

    provision = await _provision_metatrader_account(
        {
            "name": str(account_label or f"SignalRankAI-{platform_n}-{int(user_id)}")[:128],
            "type": "cloud-g2",
            "login": login_n,
            "password": password_n,
            "server": server_n,
            "platform": platform_n,
            "magic": int(os.getenv("SIGNALRANK_METAAPI_MAGIC", "12345") or 12345),
            "keywords": [str(broker_name).strip()] if broker_name else [],
            "reliability": "high",
            "metadata": {
                "signalrank_user_id": int(user_id),
                "source": "signalrank-platform",
            },
        }
    )
    if not provision.get("success"):
        return provision

    data = dict(provision.get("data") or {})
    account_id = str(data.get("id") or "").strip() or None
    env = _environment_from_server(server_n, environment)
    status = "provisioning" if provision.get("pending") else (
        "linked" if account_id else "credentials_saved"
    )
    verified_at = None
    info = None
    if account_id and not provision.get("pending"):
        info = await get_account_info(account_id)
        if isinstance(info, dict):
            if info.get("is_demo") is True:
                env = "demo"
            elif info.get("is_demo") is False:
                env = "live"
            if bool(info.get("connected")):
                status = "verified"
                verified_at = datetime.now(timezone.utc)

    connection = await upsert_connection(
        user_id=int(user_id),
        platform=platform_n,
        connector="metaapi",
        broker_name=broker_name,
        account_label=account_label or f"{platform_n.upper()} account",
        account_ref=login_n,
        external_account_id=account_id,
        environment=env,
        auth_mode="encrypted_password",
        secret_encrypted=encrypted,
        server=server_n,
        status=status,
        permissions={"read": True, "trade": True},
        capabilities={
            "market_data": True,
            "orders": True,
            "positions": True,
            "hard_stop": True,
            "close_positions": True,
            "modify_stop": True,
        },
        execution_enabled=False,
        meta={
            "provider": "metaapi",
            "provisioning_pending": bool(provision.get("pending")),
            "retry_after": provision.get("retry_after"),
        },
    )

    # Keep the mature MT5 compatibility store synchronized while the rest of
    # the application migrates to the provider-neutral registry.
    if platform_n == "mt5":
        from db.session import get_session
        from sqlalchemy import text

        legacy_pw = encrypt_secret(password_n)
        if legacy_pw:
            async with get_session(label="metatrader.mt5.compat", timeout_seconds=8.0) as session:
                await session.execute(
                    text(
                        """
                        INSERT INTO mt5_credentials(
                            user_id,mt5_login,password_encrypted,server,
                            metaapi_account_id,created_at,updated_at
                        )
                        VALUES(:uid,:login,:pw,:server,:account_id,NOW(),NOW())
                        ON CONFLICT(user_id) DO UPDATE
                        SET mt5_login=EXCLUDED.mt5_login,
                            password_encrypted=EXCLUDED.password_encrypted,
                            server=EXCLUDED.server,
                            metaapi_account_id=COALESCE(
                                EXCLUDED.metaapi_account_id,
                                mt5_credentials.metaapi_account_id
                            ),
                            updated_at=NOW()
                        """
                    ),
                    {
                        "uid": int(user_id),
                        "login": login_n,
                        "pw": legacy_pw,
                        "server": server_n,
                        "account_id": account_id,
                    },
                )
                await session.commit()

    return {
        "success": True,
        "pending": bool(provision.get("pending")),
        "connection": connection,
        "account_info": info,
    }


async def create_platform_metatrader_secure_link(
    user_id: int,
    *,
    platform: str,
    server: str,
    broker_name: str | None = None,
    account_label: str | None = None,
    environment: str = "unknown",
    ttl_days: int = 3,
) -> Dict[str, Any]:
    """Create an MT4/MT5 connection whose password is entered on MetaApi."""
    from services.broker_connections import upsert_connection

    platform_n = str(platform or "").strip().lower()
    server_n = str(server or "").strip()
    if platform_n not in {"mt4", "mt5"}:
        return {"success": False, "error": "platform must be mt4 or mt5"}
    if not server_n:
        return {"success": False, "error": "broker server is required"}

    provision = await _provision_metatrader_account(
        {
            "name": str(account_label or f"SignalRankAI-{platform_n}-{int(user_id)}")[:128],
            "type": "cloud-g2",
            "server": server_n,
            "platform": platform_n,
            "magic": int(os.getenv("SIGNALRANK_METAAPI_MAGIC", "12345") or 12345),
            "keywords": [str(broker_name).strip()] if broker_name else [],
            "reliability": "high",
            "metadata": {
                "signalrank_user_id": int(user_id),
                "source": "signalrank-secure-link",
            },
        }
    )
    if not provision.get("success"):
        return provision
    data = dict(provision.get("data") or {})
    account_id = str(data.get("id") or "").strip()
    if not account_id:
        return {
            "success": False,
            "error": "MetaApi is still detecting broker settings; retry this explicit connect action later",
            "pending": bool(provision.get("pending")),
            "retry_after": provision.get("retry_after"),
        }

    link_result = await _create_configuration_link(account_id, ttl_days=ttl_days)
    if not link_result.get("success"):
        return link_result

    connection = await upsert_connection(
        user_id=int(user_id),
        platform=platform_n,
        connector="metaapi",
        broker_name=broker_name,
        account_label=account_label or f"{platform_n.upper()} secure account",
        account_ref=None,
        external_account_id=account_id,
        environment=_environment_from_server(server_n, environment),
        auth_mode="provider_secure_link",
        secret_encrypted=None,
        server=server_n,
        status="awaiting_credentials",
        permissions={"read": True, "trade": True},
        capabilities={
            "market_data": True,
            "orders": True,
            "positions": True,
            "hard_stop": True,
            "close_positions": True,
            "modify_stop": True,
        },
        execution_enabled=False,
        meta={"provider": "metaapi", "credential_storage": "provider_managed"},
    )
    return {
        "success": True,
        "connection": connection,
        "configuration_link": link_result["configuration_link"],
    }


async def get_platform_metatrader_connection(
    user_id: int,
    *,
    platform: str | None = None,
    connection_id: str | None = None,
    require_execution_enabled: bool = False,
) -> Optional[Dict[str, Any]]:
    """Return one canonical MT4/MT5 connection, preferring the user's default."""
    from db.models import BrokerConnection
    from db.session import get_session
    from sqlalchemy import select

    async with get_session(label="metatrader.connection.lookup", timeout_seconds=6.0) as session:
        query = select(BrokerConnection).where(
            BrokerConnection.user_id == int(user_id),
            BrokerConnection.connector == "metaapi",
            BrokerConnection.platform.in_(("mt4", "mt5")),
        )
        if connection_id:
            query = query.where(BrokerConnection.connection_id == str(connection_id))
        if platform:
            query = query.where(BrokerConnection.platform == str(platform).strip().lower())
        if require_execution_enabled:
            query = query.where(BrokerConnection.execution_enabled.is_(True))
        row = (
            await session.execute(
                query.order_by(
                    BrokerConnection.is_default.desc(),
                    BrokerConnection.verified_at.desc().nullslast(),
                    BrokerConnection.created_at.asc(),
                ).limit(1)
            )
        ).scalar_one_or_none()
        await session.rollback()
    if row is None:
        return None
    from services.broker_connections import public_connection

    return public_connection(row)


async def verify_platform_metatrader_connection(
    user_id: int,
    connection_id: str,
) -> Dict[str, Any]:
    """Refresh broker connectivity and demo/live classification."""
    from db.models import BrokerConnection
    from db.session import get_session
    from sqlalchemy import select

    async with get_session(label="metatrader.connection.verify", timeout_seconds=8.0) as session:
        row = (
            await session.execute(
                select(BrokerConnection).where(
                    BrokerConnection.user_id == int(user_id),
                    BrokerConnection.connection_id == str(connection_id),
                    BrokerConnection.connector == "metaapi",
                    BrokerConnection.platform.in_(("mt4", "mt5")),
                ).with_for_update().limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return {"success": False, "error": "MetaTrader connection not found"}
        account_id = str(row.external_account_id or "").strip()
        if not account_id:
            return {"success": False, "error": "MetaApi account has not been provisioned yet"}

        info = await get_account_info(account_id)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        row.last_health_at = now
        if not isinstance(info, dict):
            row.status = "unhealthy"
            row.last_error_code = "account_info_unavailable"
            row.last_error_message = "Could not verify the broker account"
            row.updated_at = now
            await session.commit()
            return {"success": False, "error": row.last_error_message}

        if info.get("is_demo") is True:
            row.environment = "demo"
        elif info.get("is_demo") is False:
            row.environment = "live"
        connected = bool(info.get("connected"))
        row.status = "verified" if connected else "linked"
        row.verified_at = now if connected else row.verified_at
        row.last_error_code = None if connected else "broker_disconnected"
        row.last_error_message = None if connected else "Broker terminal is not connected"
        if info.get("account_number") and not row.account_ref:
            row.account_ref = str(info["account_number"])[:128]
        row.updated_at = now
        await session.commit()
        await session.refresh(row)

        from services.broker_connections import public_connection

        return {
            "success": connected,
            "connection": public_connection(row),
            "account_info": info,
            "error": None if connected else "Broker terminal is not connected",
        }


async def ensure_platform_metatrader_account_id(
    user_id: int,
    *,
    platform: str | None = None,
    connection_id: str | None = None,
    require_execution_enabled: bool = False,
) -> Optional[str]:
    """Resolve or explicitly re-provision a canonical MT4/MT5 connection."""
    import json as _json

    connection = await get_platform_metatrader_connection(
        int(user_id),
        platform=platform,
        connection_id=connection_id,
        require_execution_enabled=require_execution_enabled,
    )
    if not connection:
        # Legacy MT5 fallback during migration.
        if platform in (None, "mt5") and not require_execution_enabled:
            return await ensure_platform_mt5_account_id(int(user_id))
        return None
    account_id = str(connection.get("external_account_id") or "").strip()
    if account_id:
        return account_id

    connection_id_value = str(connection.get("connection_id") or "")
    try:
        from db.models import BrokerConnection
        from db.session import get_session
        from services.security import decrypt_secret
        from sqlalchemy import select

        async with get_session(label="metatrader.reprovision", timeout_seconds=8.0) as session:
            row = (
                await session.execute(
                    select(BrokerConnection).where(
                        BrokerConnection.user_id == int(user_id),
                        BrokerConnection.connection_id == connection_id_value,
                    ).limit(1)
                )
            ).scalar_one_or_none()
            await session.rollback()
        if row is None or not row.secret_encrypted:
            return None
        decoded = decrypt_secret(str(row.secret_encrypted))
        payload = _json.loads(decoded) if decoded else {}
        result = await link_platform_metatrader_account(
            int(user_id),
            platform=str(payload.get("platform") or row.platform),
            login=str(payload.get("login") or ""),
            password=str(payload.get("password") or ""),
            server=str(payload.get("server") or row.server or ""),
            broker_name=row.broker_name,
            account_label=row.account_label,
            environment=row.environment,
        )
        new_connection = dict(result.get("connection") or {})
        return str(new_connection.get("external_account_id") or "").strip() or None
    except Exception:
        logger.warning("[metatrader] reprovision failed user=%s", user_id, exc_info=True)
        return None
