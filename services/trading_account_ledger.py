"""Persistent append-only ledger for one canonical broker trading account.

The database trigger is the final immutability boundary. This service adds
ownership, idempotency and secret-scrubbing before rows reach PostgreSQL.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from db.models import (
    BrokerConnection,
    TradingAccountLedgerEntry,
)
from db.session import get_session
from utils.timeutils import now_utc_naive


ACCOUNT_LEDGER_ENTRY_TYPES = frozenset(
    {
        "deposit",
        "withdrawal",
        "balance_snapshot",
        "equity_snapshot",
        "margin_snapshot",
        "realized_pnl",
        "unrealized_pnl_snapshot",
        "commission",
        "funding",
        "swap",
        "fee",
        "order",
        "fill",
        "position_snapshot",
        "adjustment",
        "reconciliation_correction",
    }
)

_SECRET_TOKENS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "private_key",
    "authorization",
)


def _decimal_or_none(value: Any, *, name: str) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"invalid_{name}") from None
    if not parsed.is_finite():
        raise ValueError(f"invalid_{name}")
    return parsed


def _safe_metadata(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "<truncated>"
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)[:128]
            lowered = key.lower()
            if any(token in lowered for token in _SECRET_TOKENS):
                result[key] = "<redacted>"
            else:
                result[key] = _safe_metadata(raw_value, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple, set)):
        return [_safe_metadata(item, depth=depth + 1) for item in list(value)[:100]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value if not isinstance(value, str) else value[:2048]
    return str(value)[:2048]


def _provider_time(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("invalid_provider_timestamp") from None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


async def _owned_connection(session: Any, user_id: int, connection_id: str) -> BrokerConnection:
    row = (
        await session.execute(
            select(BrokerConnection).where(
                BrokerConnection.user_id == int(user_id),
                BrokerConnection.connection_id == str(connection_id),
            ).limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise LookupError("broker_connection_not_found")
    return row


async def _append_account_ledger_in_session(
    session: Any,
    *,
    user_id: int,
    connection_id: str,
    provider: str,
    entry_type: str,
    source_event_id: str,
    currency: str = "USD",
    correlation_id: str | None = None,
    order_ref: str | None = None,
    fill_ref: str | None = None,
    position_ref: str | None = None,
    amount: Any = None,
    balance: Any = None,
    equity: Any = None,
    margin: Any = None,
    free_margin: Any = None,
    realized_pnl: Any = None,
    unrealized_pnl: Any = None,
    commission: Any = None,
    funding: Any = None,
    swap: Any = None,
    fees: Any = None,
    correction_of_entry_id: str | None = None,
    provider_timestamp: datetime | str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    """Append one account-owned event without committing the caller's session."""
    await _owned_connection(session, int(user_id), str(connection_id))

    kind = str(entry_type or "").strip().lower()
    if kind not in ACCOUNT_LEDGER_ENTRY_TYPES:
        raise ValueError("invalid_account_ledger_entry_type")
    provider_value = str(provider or "").strip().lower()
    if not provider_value:
        raise ValueError("provider_required")
    source = str(source_event_id or "").strip()
    if not source or len(source) > 160:
        raise ValueError("source_event_id_required")
    currency_value = str(currency or "USD").strip().upper()
    if not currency_value or len(currency_value) > 8:
        raise ValueError("invalid_currency")

    if correction_of_entry_id:
        original = (
            await session.execute(
                select(TradingAccountLedgerEntry).where(
                    TradingAccountLedgerEntry.entry_id == str(correction_of_entry_id),
                    TradingAccountLedgerEntry.user_id == int(user_id),
                    TradingAccountLedgerEntry.connection_id == str(connection_id),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if original is None:
            raise PermissionError("ledger_correction_target_not_owned")

    entry_id = str(uuid4())
    values = {
        "entry_id": entry_id,
        "user_id": int(user_id),
        "connection_id": str(connection_id),
        "provider": provider_value[:32],
        "entry_type": kind,
        "currency": currency_value,
        "source_event_id": source,
        "correlation_id": str(correlation_id)[:128] if correlation_id else None,
        "order_ref": str(order_ref)[:160] if order_ref else None,
        "fill_ref": str(fill_ref)[:160] if fill_ref else None,
        "position_ref": str(position_ref)[:160] if position_ref else None,
        "amount": _decimal_or_none(amount, name="amount"),
        "balance": _decimal_or_none(balance, name="balance"),
        "equity": _decimal_or_none(equity, name="equity"),
        "margin": _decimal_or_none(margin, name="margin"),
        "free_margin": _decimal_or_none(free_margin, name="free_margin"),
        "realized_pnl": _decimal_or_none(realized_pnl, name="realized_pnl"),
        "unrealized_pnl": _decimal_or_none(unrealized_pnl, name="unrealized_pnl"),
        "commission": _decimal_or_none(commission, name="commission"),
        "funding": _decimal_or_none(funding, name="funding"),
        "swap": _decimal_or_none(swap, name="swap"),
        "fees": _decimal_or_none(fees, name="fees"),
        "correction_of_entry_id": (
            str(correction_of_entry_id) if correction_of_entry_id else None
        ),
        "provider_timestamp": _provider_time(provider_timestamp),
        "metadata": _safe_metadata(dict(metadata or {})),
        "created_at": now_utc_naive(),
    }

    statement = (
        insert(TradingAccountLedgerEntry.__table__)
        .values(**values)
        .on_conflict_do_nothing(
            constraint="uq_trading_account_ledger_provider_event"
        )
        .returning(TradingAccountLedgerEntry.entry_id)
    )
    inserted = (await session.execute(statement)).scalar_one_or_none()
    if inserted:
        return str(inserted)

    existing = (
        await session.execute(
            select(TradingAccountLedgerEntry.entry_id).where(
                TradingAccountLedgerEntry.connection_id == str(connection_id),
                TradingAccountLedgerEntry.provider == provider_value[:32],
                TradingAccountLedgerEntry.source_event_id == source,
            ).limit(1)
        )
    ).scalar_one_or_none()
    if existing is None:
        raise RuntimeError("account_ledger_idempotency_resolution_failed")
    return str(existing)


async def append_account_ledger_entry(**kwargs: Any) -> str:
    async with get_session(label="trading_account_ledger.append", timeout_seconds=8.0) as session:
        entry_id = await _append_account_ledger_in_session(session, **kwargs)
        await session.commit()
        return entry_id


async def record_account_snapshot(
    *,
    user_id: int,
    connection_id: str,
    provider: str,
    source_event_id: str,
    currency: str = "USD",
    balance: Any = None,
    equity: Any = None,
    margin: Any = None,
    free_margin: Any = None,
    unrealized_pnl: Any = None,
    realized_pnl: Any = None,
    provider_timestamp: datetime | str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    return await append_account_ledger_entry(
        user_id=int(user_id),
        connection_id=str(connection_id),
        provider=provider,
        entry_type="equity_snapshot",
        source_event_id=source_event_id,
        currency=currency,
        balance=balance,
        equity=equity,
        margin=margin,
        free_margin=free_margin,
        unrealized_pnl=unrealized_pnl,
        realized_pnl=realized_pnl,
        provider_timestamp=provider_timestamp,
        metadata=metadata,
    )


async def list_account_ledger(
    user_id: int,
    connection_id: str,
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    count = max(1, min(int(limit), 500))
    async with get_session(label="trading_account_ledger.list", timeout_seconds=8.0) as session:
        await _owned_connection(session, int(user_id), str(connection_id))
        rows = (
            await session.execute(
                select(TradingAccountLedgerEntry)
                .where(
                    TradingAccountLedgerEntry.user_id == int(user_id),
                    TradingAccountLedgerEntry.connection_id == str(connection_id),
                )
                .order_by(TradingAccountLedgerEntry.created_at.desc())
                .limit(count)
            )
        ).scalars().all()
        await session.rollback()

    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "entry_id": row.entry_id,
                "connection_id": row.connection_id,
                "provider": row.provider,
                "entry_type": row.entry_type,
                "currency": row.currency,
                "source_event_id": row.source_event_id,
                "correlation_id": row.correlation_id,
                "order_ref": row.order_ref,
                "fill_ref": row.fill_ref,
                "position_ref": row.position_ref,
                "amount": str(row.amount) if row.amount is not None else None,
                "balance": str(row.balance) if row.balance is not None else None,
                "equity": str(row.equity) if row.equity is not None else None,
                "margin": str(row.margin) if row.margin is not None else None,
                "free_margin": str(row.free_margin) if row.free_margin is not None else None,
                "realized_pnl": (
                    str(row.realized_pnl) if row.realized_pnl is not None else None
                ),
                "unrealized_pnl": (
                    str(row.unrealized_pnl) if row.unrealized_pnl is not None else None
                ),
                "commission": str(row.commission) if row.commission is not None else None,
                "funding": str(row.funding) if row.funding is not None else None,
                "swap": str(row.swap) if row.swap is not None else None,
                "fees": str(row.fees) if row.fees is not None else None,
                "correction_of_entry_id": row.correction_of_entry_id,
                "provider_timestamp": (
                    row.provider_timestamp.isoformat()
                    if row.provider_timestamp is not None else None
                ),
                "metadata": dict(row.metadata_json or {}),
                "created_at": row.created_at.isoformat(),
            }
        )
    return result


__all__ = [
    "ACCOUNT_LEDGER_ENTRY_TYPES",
    "append_account_ledger_entry",
    "record_account_snapshot",
    "list_account_ledger",
]
