"""Provider-neutral broker connection catalogue and persistence.

This module separates "an account is connected" from "SignalRankAI may trade
that account".  Every connection starts execution-disabled.  Platform-specific
adapters can be added without changing the account, billing, UI, or audit
contract.
"""
from __future__ import annotations

import os
import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select, text

from core.tier_policy import normalize_tier
from db.models import BrokerConnection, User
from db.session import get_session


_PLATFORM_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "platform": "mt5",
        "name": "MetaTrader 5",
        "connector": "metaapi",
        "asset_classes": ["fx", "commodity", "index", "stock", "crypto"],
        "connection_modes": ["secure_link", "encrypted_password"],
        "execution_adapter": "ready",
        "demo_supported": True,
        "live_supported": True,
    },
    {
        "platform": "mt4",
        "name": "MetaTrader 4",
        "connector": "metaapi",
        "asset_classes": ["fx", "commodity", "index", "stock", "crypto"],
        "connection_modes": ["secure_link", "encrypted_password"],
        "execution_adapter": "ready",
        "demo_supported": True,
        "live_supported": True,
    },
    {
        "platform": "bybit",
        "name": "Bybit",
        "connector": "bybit",
        "asset_classes": ["crypto"],
        "connection_modes": ["api_key"],
        "execution_adapter": "ready",
        "demo_supported": True,
        "live_supported": True,
    },
    {
        "platform": "ctrader",
        "name": "cTrader",
        "connector": "ctrader_openapi",
        "asset_classes": ["fx", "commodity", "index", "stock", "crypto"],
        "connection_modes": ["oauth"],
        "execution_adapter": "integration",
        "demo_supported": True,
        "live_supported": True,
    },
    {
        "platform": "ibkr",
        "name": "Interactive Brokers",
        "connector": "ibkr_client_portal",
        "asset_classes": ["stock", "fx", "commodity", "index", "options", "futures"],
        "connection_modes": ["oauth_or_gateway"],
        "execution_adapter": "integration",
        "demo_supported": True,
        "live_supported": True,
    },
    {
        "platform": "tradovate",
        "name": "Tradovate",
        "connector": "tradovate_api",
        "asset_classes": ["futures"],
        "connection_modes": ["oauth_or_api"],
        "execution_adapter": "integration",
        "demo_supported": True,
        "live_supported": True,
    },
    {
        "platform": "oanda",
        "name": "OANDA",
        "connector": "oanda_v20",
        "asset_classes": ["fx", "commodity", "index"],
        "connection_modes": ["api_token"],
        "execution_adapter": "integration",
        "demo_supported": True,
        "live_supported": True,
    },
    {
        "platform": "custom_api",
        "name": "Custom broker / institutional API",
        "connector": "custom",
        "asset_classes": ["custom"],
        "connection_modes": ["oauth", "api_key", "signed_rest", "fix_bridge"],
        "execution_adapter": "custom",
        "demo_supported": True,
        "live_supported": True,
    },
)


def _connection_limit(tier: str) -> int:
    value = normalize_tier(tier).value
    return {
        "FREE": 0,
        "PREMIUM": 1,
        "VIP": 3,
        "PROFESSIONAL": 10,
        "INSTITUTIONAL": 50,
        "ADMIN": 50,
        "OWNER": 100,
    }.get(value, 0)


def platform_catalog(tier: str) -> list[dict[str, Any]]:
    limit = _connection_limit(tier)
    result: list[dict[str, Any]] = []
    for row in _PLATFORM_CATALOG:
        item = dict(row)
        platform = str(item["platform"])
        if platform in {"mt4", "mt5"}:
            item["configured"] = bool(str(os.getenv("META_API_TOKEN") or "").strip())
        elif platform == "ctrader":
            item["configured"] = bool(
                str(os.getenv("CTRADER_CLIENT_ID") or "").strip()
                and str(os.getenv("CTRADER_CLIENT_SECRET") or "").strip()
                and str(os.getenv("CTRADER_REDIRECT_URI") or "").strip()
            )
        else:
            item["configured"] = True
        item["connection_limit"] = limit
        item["connectable"] = bool(limit > 0 and item["configured"])
        result.append(item)
    return result


async def list_connections(user_id: int) -> list[dict[str, Any]]:
    async with get_session(label="broker.connections.list", timeout_seconds=8.0) as session:
        rows = (
            await session.execute(
                select(BrokerConnection)
                .where(BrokerConnection.user_id == int(user_id))
                .order_by(BrokerConnection.is_default.desc(), BrokerConnection.created_at.asc())
            )
        ).scalars().all()
        await session.rollback()
    return [public_connection(row) for row in rows]


def _mask_account_ref(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if len(raw) <= 4:
        return "*" * len(raw)
    return ("*" * min(8, len(raw) - 4)) + raw[-4:]


def public_connection(row: BrokerConnection | dict[str, Any]) -> dict[str, Any]:
    def get(name: str, default: Any = None) -> Any:
        if isinstance(row, dict):
            return row.get(name, default)
        return getattr(row, name, default)

    return {
        "connection_id": str(get("connection_id") or ""),
        "platform": str(get("platform") or ""),
        "connector": str(get("connector") or ""),
        "broker_name": get("broker_name"),
        "account_label": get("account_label"),
        "account_ref_masked": _mask_account_ref(get("account_ref")),
        "external_account_id": get("external_account_id"),
        "environment": str(get("environment") or "unknown"),
        "account_classification": account_classification(row),
        "auth_mode": str(get("auth_mode") or "existing"),
        "server": get("server"),
        "status": str(get("status") or "pending"),
        "permissions": dict(get("permissions") or {}),
        "capabilities": dict(get("capabilities") or {}),
        "execution_enabled": bool(get("execution_enabled")),
        "is_default": bool(get("is_default")),
        "verified_at": get("verified_at"),
        "last_health_at": get("last_health_at"),
        "last_error_code": get("last_error_code"),
        "last_error_message": get("last_error_message"),
        "meta": dict(get("meta") or {}),
        "created_at": get("created_at"),
        "updated_at": get("updated_at"),
    }


def account_classification(row: BrokerConnection | dict[str, Any]) -> str:
    """Normalize persisted account mode without downgrading explicit prop policy."""
    meta = row.get("meta", {}) if isinstance(row, dict) else row.meta
    environment = row.get("environment") if isinstance(row, dict) else row.environment
    explicit = (meta or {}).get("account_classification")
    if explicit is not None:
        return str(explicit).strip().upper()
    return {"paper": "PAPER", "demo": "DEMO", "live": "LIVE_PERSONAL", "prop": "PROP"}.get(
        str(environment or "").strip().lower(), "UNKNOWN"
    )


def execution_connection_error(row: BrokerConnection, user_id: int) -> str | None:
    """Evaluate persisted owner, permissions and account health before broker I/O."""
    if row.user_id != user_id or not str(row.connection_id or "").strip():
        return "broker_connection_not_found"
    mode = account_classification(row)
    if mode == "PAPER":
        return "paper_account_broker_execution_forbidden"
    # PROP accounts are allowed to reach the canonical execution gate; they
    # remain fail-closed there until the versioned prop policy is certified.
    if mode not in {"DEMO", "LIVE_PERSONAL", "PROP"}:
        return "account_classification_required"
    if str(row.status or "").strip().lower() not in {"linked", "ready", "verified"}:
        return "broker_account_not_ready"
    permissions = dict(row.permissions or {})
    if permissions.get("trade") is not True:
        return "broker_trade_permission_required"
    if permissions.get("withdraw", False) is not False or permissions.get("internal_transfer", False) is not False:
        return "broker_trade_only_permissions_required"
    if row.execution_enabled is not True:
        return "account_execution_disabled"
    return None


async def resolve_execution_connection(
    user_id: int, *, platform: str, connection_id: str | None = None,
) -> BrokerConnection:
    """Resolve one owned account; a preferred account cannot resolve ambiguity."""
    async with get_session(label="broker.execution.resolve", timeout_seconds=6.0) as session:
        query = select(BrokerConnection).where(
            BrokerConnection.user_id == int(user_id),
            BrokerConnection.platform == str(platform).strip().lower(),
        )
        if connection_id is not None:
            if not str(connection_id).strip():
                raise LookupError("broker_connection_not_found")
            query = query.where(BrokerConnection.connection_id == str(connection_id).strip())
        rows = (await session.execute(query.limit(2))).scalars().all()
        if not rows:
            raise LookupError("broker_connection_not_found")
        if len(rows) != 1:
            raise PermissionError("explicit_broker_connection_required")
        row = rows[0]
        error = execution_connection_error(row, int(user_id))
        if error:
            raise PermissionError(error)
        # The returned ORM row is a detached snapshot, not an implicit account cursor.
        session.expunge(row)
        await session.rollback()
        return row


async def register_exchange_connection(
    telegram_user_id: int, *, provider: str, api_key: str, payload: dict[str, Any],
) -> dict[str, Any]:
    """Migrate encrypted exchange linkage into the canonical account registry."""
    from services.security import encrypt_secret

    async with get_session(label="broker.exchange.owner", timeout_seconds=6.0) as session:
        owner = (await session.execute(
            select(User.id).where(User.telegram_user_id == int(telegram_user_id)).limit(1)
        )).scalar_one_or_none()
        await session.rollback()
    if owner is None:
        raise LookupError("canonical user not found")
    encrypted = encrypt_secret(json.dumps(payload, sort_keys=True))
    if not encrypted:
        raise ValueError("Broker credential encryption failed")
    sandbox = payload.get("sandbox")
    if type(sandbox) is not bool:
        raise ValueError("Broker demo/live classification is required")
    # API fingerprints are internal identifiers; masked keys are display-only.
    account_ref = hashlib.sha256(f"{provider}:{sandbox}:{api_key}".encode()).hexdigest()
    return await upsert_connection(
        user_id=int(owner), platform=provider, connector=provider,
        account_ref=account_ref, external_account_id=None,
        environment="demo" if sandbox else "live", auth_mode="api_key",
        secret_encrypted=encrypted, status="verified",
        permissions=dict(payload.get("permissions") or {}),
        meta={"account_classification": "DEMO" if sandbox else "LIVE_PERSONAL"},
    )


async def assert_connection_capacity(user_id: int, tier: str) -> None:
    limit = _connection_limit(tier)
    if limit <= 0:
        raise PermissionError("This plan does not include broker connections")
    async with get_session(label="broker.connections.capacity", timeout_seconds=6.0) as session:
        count = int(
            (
                await session.execute(
                    text("SELECT COUNT(*) FROM broker_connections WHERE user_id=:uid"),
                    {"uid": int(user_id)},
                )
            ).scalar_one()
            or 0
        )
        await session.rollback()
    if count >= limit:
        raise PermissionError(
            f"Your plan supports {limit} connected trading account(s). "
            "Upgrade or remove an existing connection before adding another."
        )


async def upsert_connection(
    *,
    user_id: int,
    platform: str,
    connector: str,
    account_ref: str | None,
    external_account_id: str | None,
    broker_name: str | None = None,
    account_label: str | None = None,
    environment: str = "unknown",
    auth_mode: str = "existing",
    secret_encrypted: str | None = None,
    server: str | None = None,
    status: str = "pending",
    permissions: dict[str, Any] | None = None,
    capabilities: dict[str, Any] | None = None,
    execution_enabled: bool = False,
    is_default: bool | None = None,
    last_error_code: str | None = None,
    last_error_message: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    platform_n = str(platform or "").strip().lower()
    connector_n = str(connector or "").strip().lower()
    if not platform_n or not connector_n:
        raise ValueError("platform and connector are required")

    async with get_session(label="broker.connections.upsert", timeout_seconds=10.0) as session:
        user_exists = (
            await session.execute(select(User.id).where(User.id == int(user_id)).limit(1))
        ).scalar_one_or_none()
        if user_exists is None:
            raise ValueError("canonical user not found")

        row = None
        if account_ref:
            row = (
                await session.execute(
                    select(BrokerConnection).where(
                        BrokerConnection.user_id == int(user_id),
                        BrokerConnection.platform == platform_n,
                        BrokerConnection.account_ref == str(account_ref),
                    ).limit(1)
                )
            ).scalar_one_or_none()
        if row is None and external_account_id:
            row = (
                await session.execute(
                    select(BrokerConnection).where(
                        BrokerConnection.user_id == int(user_id),
                        BrokerConnection.connector == connector_n,
                        BrokerConnection.external_account_id == str(external_account_id),
                    ).limit(1)
                )
            ).scalar_one_or_none()

        if row is None:
            existing_default = (
                await session.execute(
                    select(BrokerConnection.connection_id).where(
                        BrokerConnection.user_id == int(user_id),
                        BrokerConnection.is_default.is_(True),
                    ).limit(1)
                )
            ).scalar_one_or_none()
            row = BrokerConnection(
                connection_id=str(uuid4()),
                user_id=int(user_id),
                platform=platform_n,
                connector=connector_n,
                execution_enabled=False,
                is_default=bool(is_default) if is_default is not None else existing_default is None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(row)

        row.broker_name = str(broker_name).strip()[:128] if broker_name else None
        row.account_label = str(account_label).strip()[:128] if account_label else None
        row.account_ref = str(account_ref).strip()[:128] if account_ref else row.account_ref
        row.external_account_id = (
            str(external_account_id).strip()[:128]
            if external_account_id
            else row.external_account_id
        )
        next_environment = str(environment or "unknown").strip().lower()[:16]
        if row.environment != next_environment or (
            secret_encrypted is not None and row.secret_encrypted != secret_encrypted
        ):
            row.execution_enabled = False
        row.environment = next_environment
        row.auth_mode = str(auth_mode or "existing").strip().lower()[:32]
        if secret_encrypted is not None:
            row.secret_encrypted = str(secret_encrypted)
        row.server = str(server).strip()[:128] if server else row.server
        row.status = str(status or "pending").strip().lower()[:32]
        row.permissions = dict(permissions or row.permissions or {})
        row.capabilities = dict(capabilities or row.capabilities or {})
        # Never let a relink implicitly turn execution on.
        if bool(execution_enabled) and not bool(row.execution_enabled):
            row.execution_enabled = False
        if is_default is not None:
            row.is_default = bool(is_default)
        row.last_error_code = (
            str(last_error_code).strip()[:128] if last_error_code else None
        )
        row.last_error_message = (
            str(last_error_message).strip()[:512] if last_error_message else None
        )
        next_meta = dict(meta or row.meta or {})
        if (row.meta or {}).get("account_classification") is not None:
            # Relinking credentials must never downgrade a PROP account policy.
            next_meta["account_classification"] = row.meta["account_classification"]
        row.meta = next_meta
        row.updated_at = datetime.utcnow()

        # Every connection owns a conservative versioned policy from birth.
        # This prevents post-migration accounts from existing outside the
        # canonical policy boundary. Relinks never auto-upgrade permissions.
        await session.flush()
        from db.models import TradingAccountPolicyRecord

        account_policy = (
            await session.execute(
                select(TradingAccountPolicyRecord).where(
                    TradingAccountPolicyRecord.connection_id == str(row.connection_id),
                    TradingAccountPolicyRecord.user_id == int(user_id),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if account_policy is None:
            requested_classification = str(
                (row.meta or {}).get("account_classification") or ""
            ).strip().upper()
            if requested_classification not in {"PAPER", "DEMO", "LIVE_PERSONAL", "PROP"}:
                requested_classification = (
                    "LIVE_PERSONAL"
                    if str(row.environment or "").lower() == "live"
                    else "DEMO"
                )
            account_policy = TradingAccountPolicyRecord(
                policy_id=str(uuid4()),
                connection_id=str(row.connection_id),
                user_id=int(user_id),
                policy_version=1,
                account_mode=requested_classification,
                execution_permission="SIGNALS_ONLY",
                status="configured",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(account_policy)
            next_meta = dict(row.meta or {})
            next_meta["account_classification"] = requested_classification
            next_meta["account_policy_version"] = 1
            row.meta = next_meta
            row.execution_enabled = False

        await session.commit()
        await session.refresh(row)
        return public_connection(row)


async def set_execution_enabled(
    user_id: int,
    connection_id: str,
    *,
    enabled: bool,
    accepted_terms: bool,
) -> dict[str, Any]:
    async with get_session(label="broker.connections.execution_toggle", timeout_seconds=8.0) as session:
        row = (
            await session.execute(
                select(BrokerConnection).where(
                    BrokerConnection.connection_id == str(connection_id),
                    BrokerConnection.user_id == int(user_id),
                ).with_for_update().limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            raise LookupError("Broker connection not found")
        if enabled:
            if not accepted_terms:
                raise PermissionError("Execution-risk terms must be accepted first")
            if str(row.status or "").lower() not in {"linked", "ready", "verified"}:
                raise PermissionError("Verify the broker connection before enabling execution")
            reason = execution_connection_error(row, int(user_id))
            if reason and reason != "account_execution_disabled":
                raise PermissionError(reason)

            from db.models import TradingAccountPolicyRecord

            policy = (
                await session.execute(
                    select(TradingAccountPolicyRecord).where(
                        TradingAccountPolicyRecord.connection_id == str(connection_id),
                        TradingAccountPolicyRecord.user_id == int(user_id),
                    ).with_for_update().limit(1)
                )
            ).scalar_one_or_none()
            if policy is None:
                raise PermissionError("account_policy_required")
            permission = str(policy.execution_permission or "").strip().upper()
            if permission not in {"MANUAL", "ASSISTED_EXECUTION", "AUTO_EXECUTION"}:
                raise PermissionError("execution_permission_blocked")
            if policy.frozen_at is not None:
                raise PermissionError("account_policy_frozen")
            account_mode = str(policy.account_mode or "").strip().upper()
            if account_mode == "PAPER":
                raise PermissionError("paper_account_broker_execution_forbidden")
            if account_mode == "PROP":
                if policy.certified_at is None or not str(policy.certification_ref or "").strip():
                    raise PermissionError("prop_policy_certification_required")
                if not str(policy.prop_rules_version or "").strip():
                    raise PermissionError("prop_rules_version_required")
        row.execution_enabled = bool(enabled)
        row.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(row)
        return public_connection(row)


async def set_default_connection(user_id: int, connection_id: str) -> dict[str, Any]:
    async with get_session(label="broker.connections.default", timeout_seconds=8.0) as session:
        row = (
            await session.execute(
                select(BrokerConnection).where(
                    BrokerConnection.connection_id == str(connection_id),
                    BrokerConnection.user_id == int(user_id),
                ).with_for_update().limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            raise LookupError("Broker connection not found")
        await session.execute(
            text("UPDATE broker_connections SET is_default=FALSE,updated_at=NOW() WHERE user_id=:uid"),
            {"uid": int(user_id)},
        )
        row.is_default = True
        row.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(row)
        return public_connection(row)


async def delete_connection(user_id: int, connection_id: str) -> None:
    async with get_session(label="broker.connections.delete", timeout_seconds=8.0) as session:
        row = (
            await session.execute(
                select(BrokerConnection).where(
                    BrokerConnection.connection_id == str(connection_id),
                    BrokerConnection.user_id == int(user_id),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            raise LookupError("Broker connection not found")
        if bool(row.execution_enabled):
            raise PermissionError("Disable execution before removing a broker connection")
        await session.delete(row)
        await session.commit()


__all__ = [
    "assert_connection_capacity",
    "delete_connection",
    "list_connections",
    "platform_catalog",
    "public_connection",
    "set_default_connection",
    "set_execution_enabled",
    "upsert_connection",
]
