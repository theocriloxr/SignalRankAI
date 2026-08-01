"""Per-recipient monitoring state and idempotent Continue/Stop actions."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.signal_lifecycle import TERMINAL_SIGNAL_STATES, normalize_lifecycle_state
from db.models import (
    SignalDelivery,
    SignalTrackingEvent,
    SignalLifecycle,
    User,
    UserSignalMonitoring,
    UserSignalMonitoringAction,
)
from utils.timeutils import now_utc_naive


ACTIVE_MONITORING_STATES = frozenset({"auto_continue", "continued"})
STOPPED_MONITORING_STATE = "stopped"


@dataclass(frozen=True, slots=True)
class MonitoringActionResult:
    result: str
    signal_id: str
    status: str
    stage: int
    duplicate: bool = False


async def ensure_monitoring_for_delivery(
    session: AsyncSession,
    *,
    delivery: SignalDelivery,
) -> UserSignalMonitoring | None:
    """Create default auto-continue state only from confirmed Telegram proof."""
    proof_ok = bool(
        delivery.sent_ok
        and delivery.telegram_chat_id is not None
        and delivery.telegram_message_id is not None
        and str(delivery.delivery_state or "").lower() in {"sent", "confirmed", "delivered", "reconciled"}
    )
    if not proof_ok:
        return None
    row = (
        await session.execute(
            select(UserSignalMonitoring).where(
                UserSignalMonitoring.user_id == int(delivery.user_id),
                UserSignalMonitoring.signal_id == str(delivery.signal_id),
            ).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        row = UserSignalMonitoring(
            user_id=int(delivery.user_id),
            signal_id=str(delivery.signal_id),
            delivery_id=int(delivery.id),
            status="auto_continue",
        )
        session.add(row)
        await session.flush()
    return row


async def apply_monitoring_action(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    signal_id: str,
    action: str,
    stage: int,
    idempotency_key: str,
) -> MonitoringActionResult:
    """Atomically apply one recipient action without touching global lifecycle."""
    action_l = str(action or "").strip().lower()
    if action_l not in {"continue", "stop"} or int(stage) not in {1, 2}:
        raise ValueError("invalid monitoring action")
    key = str(idempotency_key or "").strip()[:128]
    if not key:
        raise ValueError("idempotency key is required")

    prior = (
        await session.execute(
            select(UserSignalMonitoringAction).where(
                UserSignalMonitoringAction.idempotency_key == key
            ).limit(1)
        )
    ).scalar_one_or_none()
    if prior is not None:
        monitoring = await session.get(UserSignalMonitoring, int(prior.monitoring_id))
        return MonitoringActionResult(
            str(prior.result), str(prior.signal_id), str(getattr(monitoring, "status", "")),
            int(prior.stage), duplicate=True,
        )

    user = (
        await session.execute(
            select(User).where(User.telegram_user_id == int(telegram_user_id)).limit(1)
        )
    ).scalar_one_or_none()
    if user is None:
        raise PermissionError("recipient not found")
    delivery = (
        await session.execute(
            select(SignalDelivery).where(
                SignalDelivery.user_id == int(user.id),
                SignalDelivery.signal_id == str(signal_id),
                SignalDelivery.sent_ok.is_(True),
                SignalDelivery.telegram_chat_id.is_not(None),
                SignalDelivery.telegram_message_id.is_not(None),
            ).limit(1).with_for_update()
        )
    ).scalar_one_or_none()
    if delivery is None:
        raise PermissionError("confirmed delivery proof is required")

    monitoring = await ensure_monitoring_for_delivery(session, delivery=delivery)
    if monitoring is None:
        raise PermissionError("confirmed delivery proof is required")
    # Recheck after locking the delivery/monitoring rows. A concurrent worker
    # may have committed the same callback while this transaction waited.
    prior = (
        await session.execute(
            select(UserSignalMonitoringAction).where(
                UserSignalMonitoringAction.idempotency_key == key
            ).limit(1)
        )
    ).scalar_one_or_none()
    if prior is not None:
        return MonitoringActionResult(
            str(prior.result), str(prior.signal_id), str(monitoring.status),
            int(prior.stage), duplicate=True,
        )
    lifecycle = await session.get(SignalLifecycle, str(signal_id))
    is_terminal = bool(
        lifecycle is not None
        and normalize_lifecycle_state(lifecycle.state) in TERMINAL_SIGNAL_STATES
    )
    now = now_utc_naive()
    if is_terminal:
        result = "already_closed"
    elif action_l == "stop":
        if monitoring.status == STOPPED_MONITORING_STATE:
            result = "already_stopped"
        else:
            monitoring.status = STOPPED_MONITORING_STATE
            monitoring.stopped_at_stage = max(int(stage), int(monitoring.stopped_at_stage or 0))
            monitoring.stopped_at = now
            result = "stopped"
            stage_event = (
                await session.execute(
                    select(SignalTrackingEvent).where(
                        SignalTrackingEvent.signal_id == str(signal_id),
                        SignalTrackingEvent.event_type == f"tp{int(stage)}_hit",
                    ).limit(1)
                )
            ).scalar_one_or_none()
            monitoring.realized_r = getattr(stage_event, "r_multiple", None)
            monitoring.realized_outcome = f"stopped_tp{int(stage)}"
    else:
        if monitoring.status in ACTIVE_MONITORING_STATES:
            result = "already_continuing"
        else:
            monitoring.status = "continued"
            monitoring.continued_at = now
            monitoring.stopped_at = None
            monitoring.stopped_at_stage = None
            monitoring.realized_r = None
            monitoring.realized_outcome = None
            result = "continued"
    monitoring.updated_at = now
    session.add(UserSignalMonitoringAction(
        monitoring_id=int(monitoring.id),
        user_id=int(user.id),
        signal_id=str(signal_id),
        action=action_l,
        stage=int(stage),
        idempotency_key=key,
        result=result,
    ))
    await session.flush()
    return MonitoringActionResult(result, str(signal_id), str(monitoring.status), int(stage))


async def monitoring_allows_event(
    session: AsyncSession,
    *,
    user_id: int,
    signal_id: str,
    event_type: str,
) -> bool:
    """Suppress later recipient events after Stop; terminal truth remains queryable."""
    row = (
        await session.execute(
            select(UserSignalMonitoring).where(
                UserSignalMonitoring.user_id == int(user_id),
                UserSignalMonitoring.signal_id == str(signal_id),
            ).limit(1)
        )
    ).scalar_one_or_none()
    if row is None or row.status in ACTIVE_MONITORING_STATES:
        return True
    if row.status in {"stopped", "access_revoked"}:
        return False
    return True


__all__ = [
    "ACTIVE_MONITORING_STATES",
    "MonitoringActionResult",
    "STOPPED_MONITORING_STATE",
    "apply_monitoring_action",
    "ensure_monitoring_for_delivery",
    "monitoring_allows_event",
]
