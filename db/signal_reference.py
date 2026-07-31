"""One ambiguity-safe resolver for signal commands and callbacks."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.signal_identity import normalize_signal_reference
from db.models import Signal, SignalDelivery, User


class SignalReferenceError(ValueError):
    """Base class for safe user-facing reference failures."""


class SignalReferenceNotFound(SignalReferenceError):
    pass


class AmbiguousSignalReference(SignalReferenceError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedSignalReference:
    signal: Signal
    matched_by: str


_TME_LINK = re.compile(r"(?:https?://)?t\.me/c/(?P<chat>\d+)/(?P<message>\d+)", re.I)
_TG_LINK = re.compile(r"tg://openmessage\?chat_id=(?P<chat>-?\d+)&message_id=(?P<message>\d+)", re.I)


def _message_coordinates(raw: str) -> tuple[int | None, int] | None:
    match = _TME_LINK.search(raw) or _TG_LINK.search(raw)
    if not match:
        return None
    chat_raw = match.group("chat")
    chat_id = int(chat_raw)
    if match.re is _TME_LINK:
        chat_id = int(f"-100{chat_raw}")
    return chat_id, int(match.group("message"))


async def resolve_signal_reference(
    session: AsyncSession,
    reference: object,
    *,
    telegram_user_id: int | None = None,
    require_delivery_proof: bool = False,
) -> ResolvedSignalReference:
    """Resolve UUID, public display ID, legacy prefix, or Telegram message link.

    Any query yielding more than one signal is rejected.  When a recipient is
    supplied, delivery proof is joined into the lookup so forwarded callbacks
    cannot expose another user's signal.
    """
    raw = str(reference or "").strip()
    if not raw:
        raise SignalReferenceNotFound("signal reference is required")

    user_id: int | None = None
    if telegram_user_id is not None:
        user_id = (
            await session.execute(
                select(User.id).where(User.telegram_user_id == int(telegram_user_id)).limit(1)
            )
        ).scalar_one_or_none()
        if require_delivery_proof and user_id is None:
            raise SignalReferenceNotFound("signal was not delivered to this user")

    coordinates = _message_coordinates(raw)
    if coordinates is not None:
        chat_id, message_id = coordinates
        query = (
            select(Signal)
            .join(SignalDelivery, SignalDelivery.signal_id == Signal.signal_id)
            .where(
                SignalDelivery.telegram_message_id == int(message_id),
                SignalDelivery.sent_ok.is_(True),
            )
        )
        if chat_id is not None:
            query = query.where(SignalDelivery.telegram_chat_id == int(chat_id))
        if user_id is not None:
            query = query.where(SignalDelivery.user_id == int(user_id))
        matches = list((await session.execute(query.limit(2))).scalars().all())
        matched_by = "message_link"
    else:
        ref = normalize_signal_reference(raw)
        if not ref:
            raise SignalReferenceNotFound("invalid signal reference")
        query = select(Signal).where(
            or_(Signal.signal_id == ref, Signal.display_id == ref)
        )
        exact = list((await session.execute(query.limit(2))).scalars().all())
        if exact:
            matches = exact
            matched_by = "uuid" if any(str(row.signal_id).lower() == ref for row in exact) else "display_id"
        else:
            # Backward compatibility for old 8+ character UUID-prefix buttons.
            matches = list((await session.execute(
                select(Signal).where(Signal.signal_id.like(f"{ref}%")).limit(2)
            )).scalars().all())
            matched_by = "legacy_prefix"

        if require_delivery_proof and matches:
            permitted: list[Signal] = []
            for row in matches:
                proof = (
                    await session.execute(
                        select(SignalDelivery.id).where(
                            SignalDelivery.user_id == int(user_id),
                            SignalDelivery.signal_id == str(row.signal_id),
                            SignalDelivery.sent_ok.is_(True),
                            SignalDelivery.telegram_chat_id.is_not(None),
                            SignalDelivery.telegram_message_id.is_not(None),
                        ).limit(1)
                    )
                ).scalar_one_or_none()
                if proof is not None:
                    permitted.append(row)
            matches = permitted

    unique = {str(row.signal_id): row for row in matches}
    if not unique:
        raise SignalReferenceNotFound("signal not found")
    if len(unique) != 1:
        raise AmbiguousSignalReference("signal reference is ambiguous; use the full Signal ID")
    return ResolvedSignalReference(next(iter(unique.values())), matched_by)


__all__ = [
    "AmbiguousSignalReference",
    "ResolvedSignalReference",
    "SignalReferenceError",
    "SignalReferenceNotFound",
    "resolve_signal_reference",
]
