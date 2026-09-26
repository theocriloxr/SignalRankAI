"""Read-only broker-account verification through canonical connection ownership.

Verification may refresh connection health/permissions, but it never places an
order and never returns credentials.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
import time
from typing import Any

from sqlalchemy import select

from db.models import BrokerConnection
from db.session import get_session


def _masked(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if len(raw) <= 4:
        return "*" * len(raw)
    return "*" * min(8, len(raw) - 4) + raw[-4:]


async def _owned_connection(user_id: int, connection_id: str) -> BrokerConnection:
    async with get_session(label="broker.verify.owner", timeout_seconds=6.0) as session:
        row = (
            await session.execute(
                select(BrokerConnection)
                .where(
                    BrokerConnection.user_id == int(user_id),
                    BrokerConnection.connection_id == str(connection_id),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            raise LookupError("broker_connection_not_found")
        session.expunge(row)
        await session.rollback()
    return row


async def _verify_bybit(
    row: BrokerConnection,
    *,
    sample_symbol: str,
) -> dict[str, Any]:
    from services.bybit_client import BybitError, BybitV5Client
    from services.bybit_reconciler import load_bybit_connection_credentials

    credentials = await load_bybit_connection_credentials(
        int(row.user_id),
        str(row.connection_id),
    )
    if credentials is None:
        return {
            "success": False,
            "provider": "bybit",
            "error": "bybit_credentials_unavailable",
        }

    expected_demo = str(row.environment or "").strip().lower() == "demo"
    if bool(credentials.testnet) != expected_demo:
        return {
            "success": False,
            "provider": "bybit",
            "error": "bybit_environment_classification_mismatch",
        }

    client = BybitV5Client(credentials)
    try:
        permissions = await client.verify_trade_only_key(
            require_ip_binding=str(
                os.getenv("BYBIT_REQUIRE_IP_BINDING", "1")
            ).strip().lower()
            not in {"0", "false", "no", "off"}
        )
        wallet = await client.get_wallet_balance(coin="USDT")
        ticker = await client.get_ticker(sample_symbol)
    except BybitError as exc:
        return {
            "success": False,
            "provider": "bybit",
            "error": str(exc)[:200],
        }

    provider_ms = int(float(ticker.get("_provider_time_ms") or 0))
    quote_age_seconds = (
        max(0.0, time.time() - provider_ms / 1000.0)
        if provider_ms > 0
        else None
    )
    wallet_rows = list(wallet.get("list") or [])
    wallet_account = dict(wallet_rows[0]) if wallet_rows else {}
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    async with get_session(label="broker.verify.bybit.write", timeout_seconds=8.0) as session:
        persisted = (
            await session.execute(
                select(BrokerConnection)
                .where(
                    BrokerConnection.user_id == int(row.user_id),
                    BrokerConnection.connection_id == str(row.connection_id),
                    BrokerConnection.platform == "bybit",
                )
                .with_for_update()
                .limit(1)
            )
        ).scalar_one_or_none()
        if persisted is None:
            raise LookupError("broker_connection_not_found")
        persisted.status = "verified"
        persisted.environment = "demo" if credentials.testnet else "live"
        persisted.permissions = {
            "trade": True,
            "withdraw": False,
            "internal_transfer": False,
            "read_only": False,
            "ip_bound": bool(permissions.get("ip_bound")),
        }
        persisted.last_health_at = now
        persisted.verified_at = now
        persisted.last_error_code = None
        persisted.last_error_message = None
        persisted.updated_at = now
        await session.commit()

    return {
        "success": True,
        "provider": "bybit",
        "environment": "demo" if credentials.testnet else "live",
        "permissions": {
            "trade": True,
            "withdraw": False,
            "internal_transfer": False,
            "read_only": False,
            "ip_bound": bool(permissions.get("ip_bound")),
        },
        "wallet_access": bool(wallet_rows),
        "account_type": str(wallet_account.get("accountType") or "UNIFIED"),
        "sample_symbol": str(ticker.get("symbol") or sample_symbol).upper(),
        "quote_present": bool(float(ticker.get("lastPrice") or 0) > 0),
        "provider_timestamp_ms": provider_ms or None,
        "quote_age_seconds": quote_age_seconds,
    }


async def verify_broker_connection_read_only(
    user_id: int,
    connection_id: str,
    *,
    sample_symbol: str | None = None,
) -> dict[str, Any]:
    """Verify one owned broker connection without placing any order."""
    row = await _owned_connection(int(user_id), str(connection_id))
    from services.broker_connections import account_classification

    classification = account_classification(row)
    connector = str(row.connector or "").strip().lower()
    platform = str(row.platform or "").strip().lower()

    if connector == "metaapi" and platform in {"mt4", "mt5"}:
        from services.mt5_client import verify_platform_metatrader_connection

        result = await verify_platform_metatrader_connection(
            int(user_id),
            str(connection_id),
        )
        account_info = dict(result.get("account_info") or {})
        public = dict(result.get("connection") or {})
        safe_info = {
            "connected": bool(account_info.get("connected")),
            "is_demo": account_info.get("is_demo"),
            "currency": account_info.get("currency"),
            "platform": account_info.get("platform"),
            "account_number_masked": _masked(account_info.get("account_number")),
        }
        return {
            "success": bool(result.get("success")),
            "provider": "metaapi",
            "platform": platform,
            "account_classification": str(
                public.get("account_classification") or classification
            ).upper(),
            "connection_id": str(connection_id),
            "account_info": safe_info,
            "error": result.get("error"),
        }

    if platform == "bybit" or connector == "bybit":
        result = await _verify_bybit(
            row,
            sample_symbol=str(sample_symbol or "BTCUSDT").upper(),
        )
        return {
            **result,
            "platform": "bybit",
            "account_classification": classification,
            "connection_id": str(connection_id),
        }

    return {
        "success": False,
        "platform": platform,
        "provider": connector or platform,
        "account_classification": classification,
        "connection_id": str(connection_id),
        "error": "broker_verification_adapter_unavailable",
    }


__all__ = ["verify_broker_connection_read_only"]
