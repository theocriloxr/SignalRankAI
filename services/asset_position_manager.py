from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Outcome, Signal, SignalDelivery, User

TERMINAL_OUTCOMES = {
    "tp",
    "tp3",
    "win",
    "sl",
    "loss",
    "stop_loss",
    "invalid",
    "invalidated",
    "expired",
    "time_stop",
    "cancel",
    "cancelled",
}

PROGRESS_OUTCOMES = {"tp1", "tp2", "partial_tp", "breakeven", "risk_free", "pending"}


@dataclass(slots=True)
class AssetPositionState:
    user_id: int
    telegram_user_id: int
    asset: str
    state: str
    signal_id: str | None = None
    direction: str | None = None
    timeframe: str | None = None
    delivered_at: datetime | None = None
    outcome_status: str | None = None
    age_hours: float | None = None
    reason: str = ""

    @property
    def is_locked(self) -> bool:
        return self.state not in {"NONE", "STOPPED", "TP3", "EXPIRED", "CANCELLED", "SUPERSEDED"}


def _utcnow() -> datetime:
    return datetime.utcnow()


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return float(default)


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _state_from_status(status: str | None) -> str:
    s = _normalize_status(status)
    if s in {"tp3", "tp", "win"}:
        return "TP3"
    if s in {"sl", "loss", "stop_loss"}:
        return "STOPPED"
    if s in {"expired", "time_stop"}:
        return "EXPIRED"
    if s in {"cancel", "cancelled", "invalid", "invalidated"}:
        return "CANCELLED"
    if s == "tp2":
        return "TP2"
    if s in {"tp1", "partial_tp", "breakeven", "risk_free"}:
        return "TP1"
    return "ACTIVE"


async def get_user_asset_position_state(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    asset: str,
    cooldown_hours: float | None = None,
    unresolved_block_hours: float | None = None,
) -> AssetPositionState:
    symbol = str(asset or "").upper().strip()
    user = (
        await session.execute(
            select(User).where(User.telegram_user_id == int(telegram_user_id)).limit(1)
        )
    ).scalar_one_or_none()
    if user is None or not symbol:
        return AssetPositionState(0, int(telegram_user_id), symbol, "NONE", reason="no_user_or_asset")

    cooldown_h = max(0.0, float(cooldown_hours if cooldown_hours is not None else _env_float("ASSET_REPEAT_LOCK_HOURS", 12.0)))
    unresolved_h = max(
        cooldown_h,
        float(unresolved_block_hours if unresolved_block_hours is not None else _env_float("DELIVERY_UNRESOLVED_BLOCK_HOURS", 168.0)),
    )
    cutoff = _utcnow() - timedelta(hours=max(cooldown_h, unresolved_h))

    row = (
        await session.execute(
            select(
                SignalDelivery.signal_id,
                SignalDelivery.delivered_at,
                Signal.direction,
                Signal.timeframe,
                Outcome.status,
                Outcome.canonical_outcome,
            )
            .select_from(SignalDelivery)
            .join(Signal, Signal.signal_id == SignalDelivery.signal_id)
            .outerjoin(Outcome, Outcome.signal_id == SignalDelivery.signal_id)
            .where(
                SignalDelivery.user_id == user.id,
                SignalDelivery.delivered_at >= cutoff,
                Signal.asset == symbol,
                or_(
                    SignalDelivery.sent_ok.is_(True),
                    and_(SignalDelivery.sent_ok.is_(False), SignalDelivery.last_error.is_(None)),
                ),
            )
            .order_by(SignalDelivery.delivered_at.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return AssetPositionState(int(user.id), int(telegram_user_id), symbol, "NONE", reason="no_recent_position")

    signal_id, delivered_at, direction, timeframe, status, canonical = row
    outcome_status = _normalize_status(canonical or status)
    state = _state_from_status(outcome_status)
    age_hours = None
    if delivered_at is not None:
        try:
            age_hours = max(0.0, (_utcnow() - delivered_at).total_seconds() / 3600.0)
        except Exception:
            age_hours = None

    if state in {"STOPPED", "TP3", "EXPIRED", "CANCELLED", "SUPERSEDED"} and (age_hours is None or age_hours < cooldown_h):
        state = "ACTIVE"
        reason = "terminal_but_cooldown_active"
    elif state not in {"STOPPED", "TP3", "EXPIRED", "CANCELLED", "SUPERSEDED"} and (age_hours is None or age_hours < unresolved_h):
        reason = "unresolved_position_active"
    else:
        reason = "terminal_or_old_position"

    return AssetPositionState(
        user_id=int(user.id),
        telegram_user_id=int(telegram_user_id),
        asset=symbol,
        state=state,
        signal_id=str(signal_id or "") or None,
        direction=str(direction or "") or None,
        timeframe=str(timeframe or "") or None,
        delivered_at=delivered_at,
        outcome_status=outcome_status or None,
        age_hours=age_hours,
        reason=reason,
    )

