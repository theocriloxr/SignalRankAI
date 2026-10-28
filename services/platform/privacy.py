"""Account privacy constants and read-only status shared by web and Telegram.

The web Privacy center opens deletion reviews and produces exports; Telegram
/privacy only reads the review status and points to the web, because opening a
review needs a recent sign-in and a typed confirmation, and an export file
should not be delivered through a third-party chat service.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

ACCOUNT_DELETION_PHRASE = "DELETE MY ACCOUNT"
ACCOUNT_DELETION_CATEGORY = "privacy_deletion"
# Records kept after a deletion request because reconciliation, tax or security
# obligations require them; the review explains each one to the account owner.
ACCOUNT_RETAINED_RECORDS = (
    "payment receipts and subscription history",
    "security and audit events",
    "signal delivery records needed for outcome reconciliation",
)


async def latest_deletion_request(session: Any, *, user_id: int) -> dict[str, Any] | None:
    """The person's most recent deletion review, open or closed, or None."""
    row = (
        await session.execute(
            text(
                "SELECT ticket_id,status,created_at,updated_at FROM support_tickets "
                "WHERE user_id=:uid AND category=:category ORDER BY created_at DESC LIMIT 1"
            ),
            {"uid": int(user_id), "category": ACCOUNT_DELETION_CATEGORY},
        )
    ).mappings().first()
    return dict(row) if row else None


__all__ = [
    "ACCOUNT_DELETION_CATEGORY", "ACCOUNT_DELETION_PHRASE", "ACCOUNT_RETAINED_RECORDS",
    "latest_deletion_request",
]
