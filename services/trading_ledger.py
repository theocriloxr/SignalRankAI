from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AdminEvent

logger = logging.getLogger(__name__)


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "NONE": {"CANDIDATE"},
    "CANDIDATE": {"ACTIVE", "EXPIRED", "CANCELLED", "SUPERSEDED"},
    "ACTIVE": {"TP1", "TP2", "TP3", "STOPPED", "EXPIRED", "CANCELLED", "SUPERSEDED"},
    "TP1": {"TP2", "TP3", "STOPPED", "EXPIRED", "CANCELLED", "SUPERSEDED"},
    "TP2": {"TP3", "STOPPED", "EXPIRED", "CANCELLED", "SUPERSEDED"},
    "TP3": set(),
    "STOPPED": set(),
    "EXPIRED": set(),
    "CANCELLED": set(),
    "SUPERSEDED": set(),
}


def normalize_position_state(value: Any) -> str:
    state = str(value or "NONE").strip().upper()
    return state if state in ALLOWED_TRANSITIONS else "NONE"


def assert_valid_transition(previous_state: str, next_state: str) -> None:
    prev = normalize_position_state(previous_state)
    nxt = normalize_position_state(next_state)
    if nxt not in ALLOWED_TRANSITIONS.get(prev, set()):
        raise ValueError(f"illegal_position_transition:{prev}->{nxt}")


async def record_trading_event(
    session: AsyncSession,
    *,
    event_type: str,
    signal_id: str | None = None,
    asset: str | None = None,
    telegram_user_id: int | None = None,
    previous_state: str | None = None,
    next_state: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Append an immutable trading event using the existing admin event ledger.

    This intentionally avoids a migration in this pass while giving the platform
    replayable SignalGenerated/Delivered/Opened/TP/Closed breadcrumbs now.
    """
    if previous_state and next_state:
        assert_valid_transition(previous_state, next_state)
    payload = dict(details or {})
    payload.update(
        {
            "event_type": str(event_type or "unknown"),
            "signal_id": str(signal_id or "") or None,
            "asset": str(asset or "").upper().strip() or None,
            "previous_state": normalize_position_state(previous_state) if previous_state else None,
            "next_state": normalize_position_state(next_state) if next_state else None,
            "recorded_at": datetime.utcnow().isoformat(),
        }
    )
    session.add(
        AdminEvent(
            event_type=f"trading:{str(event_type or 'unknown')[:50]}",
            actor_telegram_user_id=int(telegram_user_id) if telegram_user_id is not None else None,
            details=payload,
        )
    )
    await session.flush()


async def record_signal_generated_event(session: AsyncSession, signal: dict[str, Any], signal_id: str | None = None) -> None:
    await record_trading_event(
        session,
        event_type="SignalGenerated",
        signal_id=signal_id or signal.get("signal_id") or signal.get("id"),
        asset=signal.get("asset") or signal.get("symbol"),
        previous_state="NONE",
        next_state="CANDIDATE",
        details={
            "timeframe": signal.get("timeframe"),
            "direction": signal.get("direction"),
            "score": signal.get("score"),
            "trade_profile": signal.get("trade_profile"),
            "time_to_target_score": signal.get("time_to_target_score"),
        },
    )

