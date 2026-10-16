"""Conservative account destination admission before invoking legacy provider routers.

A provider preference is never sufficient to choose a trading *account*.
No broker order, payment or policy mutation occurs in this module.
"""

from __future__ import annotations

from sqlalchemy import select

from db.models import BrokerConnection, User
from db.session import get_session


def destination_choice_allowed(*, explicit_connection: bool, canonical_eligible_accounts: int | None) -> tuple[bool, str]:
    """A missing or ambiguous canonical destination must never be auto-guessed.

    The complete multi-broker routing policy (priority, instrument tradability,
    prop rules, risk-splitting and mirror plans) is handled separately; this
    guard only stops legacy fallback from making an ambiguous choice.
    """
    if explicit_connection:
        return True, "explicit_connection_selected"
    if canonical_eligible_accounts is None:
        return False, "canonical_account_ownership_unresolved"
    if canonical_eligible_accounts <= 0:
        return False, "no_verified_execution_eligible_account"
    if canonical_eligible_accounts != 1:
        return False, "explicit_connection_required_multi_account"
    return True, "one_canonical_execution_eligible_account"


async def enforce_canonical_destination(telegram_user_id: int, connection_id: str | None) -> tuple[bool, str]:
    """Read-only owner-scoped inventory. Database uncertainty fails closed.

    A set of two eligible accounts is enough to prove ambiguity. Provider
    adapters still perform their existing, stricter policy/asset/fill checks.
    """
    if str(connection_id or "").strip():
        return destination_choice_allowed(explicit_connection=True, canonical_eligible_accounts=None)
    try:
        async with get_session(label="broker.canonical_destination_admission", timeout_seconds=6.0) as session:
            user_id = (
                await session.execute(
                    select(User.id).where(User.telegram_user_id == int(telegram_user_id)).limit(1)
                )
            ).scalar_one_or_none()
            if user_id is None:
                return destination_choice_allowed(explicit_connection=False, canonical_eligible_accounts=None)
            matching = (
                await session.execute(
                    select(BrokerConnection.connection_id).where(
                        BrokerConnection.user_id == int(user_id),
                        BrokerConnection.execution_enabled.is_(True),
                        BrokerConnection.status.in_(("linked", "ready", "verified")),
                    ).limit(2)
                )
            ).scalars().all()
            await session.rollback()
    except Exception:
        return False, "canonical_destination_admission_unavailable"
    return destination_choice_allowed(explicit_connection=False, canonical_eligible_accounts=len(matching))


__all__ = ["destination_choice_allowed", "enforce_canonical_destination"]
