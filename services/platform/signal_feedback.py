"""Delivery-scoped signal feedback shared by the web app and Telegram /feedback.

Feedback is accepted only for a signal the person actually received (a
successful Telegram delivery or a web signal notification) and is written to
the canonical account event ledger in the caller's transaction. Telegram shows
short references such as ``SIG-1a2b3c4d``; those resolve only against the
person's own receipts and must match exactly one signal.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text

ALLOWED_ISSUES = frozenset({
    "stale",
    "bad_setup",
    "wrong_levels",
    "wrong_outcome",
    "late_delivery",
    "duplicate",
    "unclear",
    "other",
})
MIN_SHORT_REF = 6
MAX_COMMENT = 4000


class FeedbackRejected(ValueError):
    """Feedback that cannot be recorded; ``status`` maps to the HTTP status."""

    def __init__(self, message: str, *, status: int = 422) -> None:
        super().__init__(message)
        self.status = status
        # Every message raised here is written for the user; channels show this, never str(exc).
        self.public_message = message


def normalize_feedback(rating: Any, issue: Any, comment: Any) -> tuple[int | None, str | None, str | None]:
    if rating is not None:
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            raise FeedbackRejected("Rating must be a whole number from 1 to 5") from None
        if not 1 <= rating <= 5:
            raise FeedbackRejected("Rating must be a whole number from 1 to 5")
    issue_value = str(issue or "").strip().lower() or None
    comment_value = (str(comment or "").strip() or None)
    if comment_value is not None:
        comment_value = comment_value[:MAX_COMMENT]
    if rating is None and issue_value is None:
        raise FeedbackRejected("Provide a rating or issue")
    if issue_value is not None and issue_value not in ALLOWED_ISSUES:
        raise FeedbackRejected("Unsupported feedback issue")
    return rating, issue_value, comment_value


def _clean_ref(signal_ref: Any) -> str:
    ref = str(signal_ref or "").strip()
    if ref[:4].upper() == "SIG-":
        ref = ref[4:]
    if not ref or len(ref) > 64:
        raise FeedbackRejected("Invalid signal reference")
    return ref


_RECEIPTS_SQL = """
    SELECT DISTINCT receipt.signal_id FROM (
        SELECT sd.signal_id::text AS signal_id
        FROM signal_deliveries sd
        WHERE sd.user_id=:uid AND sd.sent_ok=TRUE
        UNION ALL
        SELECT ne.channel_data->>'signal_id' AS signal_id
        FROM notification_events ne
        WHERE ne.user_id=:uid AND ne.event_type='signal'
    ) receipt
    WHERE receipt.signal_id {match}
    LIMIT 2
"""


async def resolve_delivered_signal(session: Any, *, user_id: int, signal_ref: Any) -> str:
    """Return the full id of a signal this user received, or refuse."""
    ref = _clean_ref(signal_ref)
    params = {"uid": int(user_id), "sid": ref}
    exact = (await session.execute(text(_RECEIPTS_SQL.format(match="= :sid")), params)).scalars().all()
    if exact:
        return str(exact[0])
    if len(ref) < MIN_SHORT_REF:
        raise FeedbackRejected("Signal not found in your delivery history", status=404)
    escaped = ref.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    candidates = (
        await session.execute(
            text(_RECEIPTS_SQL.format(match="LIKE :prefix ESCAPE '\\'")),
            {"uid": int(user_id), "prefix": escaped + "%"},
        )
    ).scalars().all()
    if not candidates:
        raise FeedbackRejected("Signal not found in your delivery history", status=404)
    if len(candidates) > 1:
        raise FeedbackRejected("That reference matches more than one of your signals; use the full reference",
                               status=409)
    return str(candidates[0])


async def record_signal_feedback(
    session: Any,
    *,
    user_id: int,
    signal_ref: Any,
    rating: Any = None,
    issue: Any = None,
    comment: Any = None,
    source: str,
) -> dict[str, Any]:
    """Validate, scope to the user's receipts and record one feedback event."""
    rating_value, issue_value, comment_value = normalize_feedback(rating, issue, comment)
    signal_id = await resolve_delivered_signal(session, user_id=int(user_id), signal_ref=signal_ref)
    from db.pg_features import record_user_event

    await record_user_event(
        session,
        user_id=int(user_id),
        event_type="feedback",
        meta={
            "source": str(source),
            "signal_id": signal_id,
            "rating": rating_value,
            "issue": issue_value,
            "comment": comment_value,
            "submitted_at": datetime.utcnow().isoformat(),
        },
    )
    return {"recorded": True, "signal_id": signal_id}


__all__ = [
    "ALLOWED_ISSUES", "FeedbackRejected", "normalize_feedback",
    "record_signal_feedback", "resolve_delivered_signal",
]
