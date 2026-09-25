"""Opaque Telegram account-selection state for execution-capable callbacks.

Telegram callback data is user-controlled input and limited to 64 bytes. This
module stores a short random opaque handle in RuntimeState and binds it to the
canonical owner, Telegram identity, signal, and broker connection. Raw broker
connection IDs are never trusted from callback payloads.
"""
from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from db.models import BrokerConnection, RuntimeState, User
from db.session import get_session
from utils.timeutils import now_utc_naive


_TOKEN_PREFIX = "broker_select:"
_TTL_MINUTES = 10
_MAX_CHOICES = 12


def _display_label(row: BrokerConnection) -> str:
    label = str(row.account_label or row.broker_name or row.platform or "Trading account").strip()
    mode = str((row.meta or {}).get("account_classification") or row.environment or "").strip().upper()
    platform = str(row.platform or "").strip().upper()
    parts = [label[:24]]
    if platform and platform not in label.upper():
        parts.append(platform)
    if mode:
        parts.append(mode)
    return " · ".join(parts)[:52]


async def create_account_selection_choices(
    telegram_user_id: int,
    signal_id: str,
    *,
    preferred_provider: str | None = None,
) -> list[dict[str, str]]:
    """Create short-lived opaque choices for execution-enabled owned accounts."""
    signal_ref = str(signal_id or "").strip()[:64]
    if not signal_ref:
        return []
    provider = str(preferred_provider or "auto").strip().lower()

    async with get_session(label="broker.selection.create", timeout_seconds=8.0) as session:
        user = (
            await session.execute(
                select(User).where(
                    User.telegram_user_id == int(telegram_user_id)
                ).limit(1)
            )
        ).scalar_one_or_none()
        if user is None:
            return []

        query = select(BrokerConnection).where(
            BrokerConnection.user_id == int(user.id),
            BrokerConnection.execution_enabled.is_(True),
            BrokerConnection.status.in_(("linked", "ready", "verified")),
        )
        if provider not in {"", "auto"}:
            query = query.where(BrokerConnection.platform == provider)
        rows = (
            await session.execute(
                query.order_by(
                    BrokerConnection.is_default.desc(),
                    BrokerConnection.verified_at.desc().nullslast(),
                    BrokerConnection.created_at.asc(),
                ).limit(_MAX_CHOICES)
            )
        ).scalars().all()

        now = now_utc_naive()
        expires = now + timedelta(minutes=_TTL_MINUTES)
        choices: list[dict[str, str]] = []
        for row in rows:
            token = secrets.token_urlsafe(9).replace("-", "").replace("_", "")[:14]
            state = RuntimeState(
                key=f"{_TOKEN_PREFIX}{token}",
                value={
                    "canonical_user_id": int(user.id),
                    "telegram_user_id": int(telegram_user_id),
                    "signal_id": signal_ref,
                    "connection_id": str(row.connection_id),
                    "platform": str(row.platform or "").strip().lower(),
                },
                expires_at=expires,
                updated_at=now,
            )
            session.add(state)
            choices.append(
                {
                    "token": token,
                    "label": _display_label(row),
                    "platform": str(row.platform or "").strip().lower(),
                    "connection_id": str(row.connection_id),
                }
            )
        await session.commit()
        return choices


async def consume_account_selection(
    token: str,
    *,
    telegram_user_id: int,
) -> dict[str, Any]:
    """Consume one selection handle and revalidate ownership/account state."""
    opaque = str(token or "").strip()
    if not opaque or len(opaque) > 32:
        raise PermissionError("account_selection_invalid")

    async with get_session(label="broker.selection.consume", timeout_seconds=8.0) as session:
        row = await session.get(
            RuntimeState,
            f"{_TOKEN_PREFIX}{opaque}",
            with_for_update=True,
        )
        if row is None:
            raise PermissionError("account_selection_expired")
        now = now_utc_naive()
        if row.expires_at is None or row.expires_at <= now:
            await session.delete(row)
            await session.commit()
            raise PermissionError("account_selection_expired")

        value = dict(row.value or {})
        if int(value.get("telegram_user_id") or 0) != int(telegram_user_id):
            raise PermissionError("account_selection_owner_mismatch")
        canonical_user_id = int(value.get("canonical_user_id") or 0)
        connection_id = str(value.get("connection_id") or "").strip()
        signal_id = str(value.get("signal_id") or "").strip()
        platform = str(value.get("platform") or "").strip().lower()
        if canonical_user_id <= 0 or not connection_id or not signal_id or not platform:
            await session.delete(row)
            await session.commit()
            raise PermissionError("account_selection_invalid")

        connection = (
            await session.execute(
                select(BrokerConnection).where(
                    BrokerConnection.connection_id == connection_id,
                    BrokerConnection.user_id == canonical_user_id,
                    BrokerConnection.platform == platform,
                ).limit(1)
            )
        ).scalar_one_or_none()
        if connection is None or connection.execution_enabled is not True:
            await session.delete(row)
            await session.commit()
            raise PermissionError("account_selection_unavailable")
        if str(connection.status or "").lower() not in {"linked", "ready", "verified"}:
            await session.delete(row)
            await session.commit()
            raise PermissionError("account_selection_unavailable")

        # One-time handle prevents replaying a stale Telegram callback.
        await session.delete(row)
        await session.commit()
        return {
            "canonical_user_id": canonical_user_id,
            "telegram_user_id": int(telegram_user_id),
            "signal_id": signal_id,
            "connection_id": connection_id,
            "platform": platform,
            "label": _display_label(connection),
        }


__all__ = [
    "create_account_selection_choices",
    "consume_account_selection",
]
