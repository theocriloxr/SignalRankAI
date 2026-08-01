"""Canonical delivery-to-position evidence used before execution claims are shown."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from core.delivery_state import CONFIRMED_DELIVERY_STATES
from db.models import BrokerExecution, MT5Execution, PaperPosition, SignalDelivery, User


async def get_execution_evidence(
    session,
    *,
    telegram_user_id: int,
    signal_id: str,
    expected_reference: str | None = None,
) -> dict[str, Any]:
    user = (await session.execute(
        select(User).where(User.telegram_user_id == int(telegram_user_id)).limit(1)
    )).scalar_one_or_none()
    if user is None:
        return {"delivery_proven": False, "position_count": 0, "exactly_one": False, "positions": []}
    delivery_count = int((await session.execute(
        select(func.count(SignalDelivery.id)).where(
            SignalDelivery.user_id == int(user.id),
            SignalDelivery.signal_id == str(signal_id),
            SignalDelivery.sent_ok.is_(True),
            func.lower(SignalDelivery.delivery_state).in_(tuple(CONFIRMED_DELIVERY_STATES)),
            SignalDelivery.telegram_chat_id.is_not(None),
            SignalDelivery.telegram_message_id.is_not(None),
            SignalDelivery.delivery_confirmed_at.is_not(None),
        )
    )).scalar() or 0)
    positions: list[dict[str, Any]] = []
    paper_rows = list((await session.execute(select(PaperPosition).where(
        PaperPosition.user_id == int(user.id),
        PaperPosition.signal_id == str(signal_id),
        func.lower(PaperPosition.status).in_(("open", "closed")),
    ))).scalars().all())
    positions.extend({
        "destination": "paper", "reference": str(row.position_id),
        "status": str(row.status), "record_id": str(row.position_id),
    } for row in paper_rows)
    mt5_rows = list((await session.execute(select(MT5Execution).where(
        MT5Execution.user_id == int(user.id),
        MT5Execution.signal_id == str(signal_id),
        MT5Execution.order_id.is_not(None),
        func.lower(MT5Execution.status).notin_(("failed", "rejected", "cancelled")),
    ))).scalars().all())
    positions.extend({
        "destination": "broker", "provider": "mt5", "reference": str(row.order_id),
        "status": str(row.status), "record_id": str(row.id),
    } for row in mt5_rows)
    broker_rows = list((await session.execute(select(BrokerExecution).where(
        BrokerExecution.user_id == int(user.id),
        BrokerExecution.signal_id == str(signal_id),
        BrokerExecution.provider_order_id.is_not(None),
        func.lower(BrokerExecution.status).notin_(("failed", "rejected", "cancelled", "blocked")),
    ))).scalars().all())
    positions.extend({
        "destination": "broker", "provider": str(row.provider),
        "reference": str(row.provider_order_id), "status": str(row.status),
        "record_id": str(row.id),
    } for row in broker_rows)
    expected = str(expected_reference or "").strip()
    matching = [row for row in positions if not expected or row["reference"] == expected]
    exactly_one = delivery_count == 1 and len(positions) == 1 and len(matching) == 1
    return {
        "delivery_proven": delivery_count == 1,
        "delivery_count": delivery_count,
        "position_count": len(positions),
        "exactly_one": exactly_one,
        "position": matching[0] if exactly_one else None,
        "positions": positions,
    }
