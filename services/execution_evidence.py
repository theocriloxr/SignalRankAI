"""Canonical delivery-to-position evidence used before broker execution claims."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, text

from core.delivery_state import CONFIRMED_DELIVERY_STATES
from db.models import BrokerExecution, MT5Execution, PaperPosition, SignalDelivery, User


async def _positions_for_user(
    session,
    user_id: int,
    signal_id: str,
    *,
    connection_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return execution evidence, optionally scoped to one broker account."""
    positions: list[dict[str, Any]] = []
    if connection_id is None:
        paper_rows = list((await session.execute(select(PaperPosition).where(
            PaperPosition.user_id == int(user_id),
            PaperPosition.signal_id == str(signal_id),
            func.lower(PaperPosition.status).in_(("open", "closed")),
        ))).scalars().all())
        positions.extend({
            "destination": "paper",
            "account_scope": f"paper:{int(user_id)}",
            "reference": str(row.position_id),
            "status": str(row.status),
            "record_id": str(row.position_id),
        } for row in paper_rows)

    mt5_filters = [
        MT5Execution.user_id == int(user_id),
        MT5Execution.signal_id == str(signal_id),
        MT5Execution.order_id.is_not(None),
        func.lower(MT5Execution.status).notin_(("failed", "rejected", "cancelled")),
    ]
    if connection_id is not None:
        mt5_filters.append(MT5Execution.connection_id == str(connection_id))
    mt5_rows = list((await session.execute(
        select(MT5Execution).where(*mt5_filters)
    )).scalars().all())
    positions.extend({
        "destination": "broker",
        "provider": "mt5",
        "connection_id": row.connection_id,
        "reference": str(row.order_id),
        "status": str(row.status),
        "record_id": str(row.id),
    } for row in mt5_rows)

    broker_filters = [
        BrokerExecution.user_id == int(user_id),
        BrokerExecution.signal_id == str(signal_id),
        BrokerExecution.provider_order_id.is_not(None),
        func.lower(BrokerExecution.status).notin_(("failed", "rejected", "cancelled", "blocked")),
    ]
    if connection_id is not None:
        broker_filters.append(BrokerExecution.connection_id == str(connection_id))
    broker_rows = list((await session.execute(
        select(BrokerExecution).where(*broker_filters)
    )).scalars().all())
    positions.extend({
        "destination": "broker",
        "provider": str(row.provider),
        "connection_id": row.connection_id,
        "reference": str(row.provider_order_id),
        "status": str(row.status),
        "record_id": str(row.id),
    } for row in broker_rows)
    return positions


async def _telegram_delivery_count(session, user_id: int, signal_id: str) -> int:
    return int((await session.execute(
        select(func.count(SignalDelivery.id)).where(
            SignalDelivery.user_id == int(user_id),
            SignalDelivery.signal_id == str(signal_id),
            SignalDelivery.sent_ok.is_(True),
            func.lower(SignalDelivery.delivery_state).in_(tuple(CONFIRMED_DELIVERY_STATES)),
            SignalDelivery.telegram_chat_id.is_not(None),
            SignalDelivery.telegram_message_id.is_not(None),
            SignalDelivery.delivery_confirmed_at.is_not(None),
        )
    )).scalar() or 0)


async def _web_receipt_count(session, user_id: int, signal_id: str) -> int:
    return int((await session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM notification_events
            WHERE user_id=:uid
              AND event_type='signal'
              AND channel_data->>'signal_id'=:sid
              AND channel_data->>'channel'='web'
            """
        ),
        {"uid": int(user_id), "sid": str(signal_id)},
    )).scalar() or 0)


def _evidence_payload(
    *,
    telegram_delivery_count: int,
    web_receipt_count: int,
    positions: list[dict[str, Any]],
    expected_reference: str | None,
) -> dict[str, Any]:
    expected = str(expected_reference or "").strip()
    matching = [row for row in positions if not expected or row["reference"] == expected]
    telegram_proven = int(telegram_delivery_count) == 1
    web_proven = int(web_receipt_count) >= 1
    access_proven = telegram_proven or web_proven
    exactly_one = access_proven and len(positions) == 1 and len(matching) == 1
    return {
        "delivery_proven": telegram_proven,
        "web_receipt_proven": web_proven,
        "access_proven": access_proven,
        "delivery_count": int(telegram_delivery_count),
        "web_receipt_count": int(web_receipt_count),
        "position_count": len(positions),
        "exactly_one": exactly_one,
        "position": matching[0] if exactly_one else None,
        "positions": positions,
    }


async def get_platform_execution_evidence(
    session,
    *,
    user_id: int,
    signal_id: str,
    expected_reference: str | None = None,
    connection_id: str | None = None,
) -> dict[str, Any]:
    """Evidence for an authenticated canonical account across web/Telegram channels."""
    canonical_id = int(user_id)
    exists = (await session.execute(
        select(User.id).where(User.id == canonical_id).limit(1)
    )).scalar_one_or_none()
    if exists is None:
        return {
            "delivery_proven": False,
            "web_receipt_proven": False,
            "access_proven": False,
            "position_count": 0,
            "exactly_one": False,
            "positions": [],
        }
    telegram_count = await _telegram_delivery_count(session, canonical_id, signal_id)
    web_count = await _web_receipt_count(session, canonical_id, signal_id)
    positions = await _positions_for_user(
        session,
        canonical_id,
        signal_id,
        connection_id=connection_id,
    )
    return _evidence_payload(
        telegram_delivery_count=telegram_count,
        web_receipt_count=web_count,
        positions=positions,
        expected_reference=expected_reference,
    )


async def get_execution_evidence(
    session,
    *,
    telegram_user_id: int,
    signal_id: str,
    expected_reference: str | None = None,
) -> dict[str, Any]:
    """Telegram compatibility path; Telegram proof semantics remain strict."""
    user = (await session.execute(
        select(User).where(User.telegram_user_id == int(telegram_user_id)).limit(1)
    )).scalar_one_or_none()
    if user is None:
        return {
            "delivery_proven": False,
            "web_receipt_proven": False,
            "access_proven": False,
            "position_count": 0,
            "exactly_one": False,
            "positions": [],
        }
    telegram_count = await _telegram_delivery_count(session, int(user.id), signal_id)
    positions = await _positions_for_user(
        session,
        int(user.id),
        signal_id,
        connection_id=connection_id,
    )
    # Telegram-originated execution requires Telegram proof, even if a web
    # receipt also exists. This preserves the existing callback security model.
    return _evidence_payload(
        telegram_delivery_count=telegram_count,
        web_receipt_count=0,
        positions=positions,
        expected_reference=expected_reference,
    )


__all__ = ["get_execution_evidence", "get_platform_execution_evidence"]
