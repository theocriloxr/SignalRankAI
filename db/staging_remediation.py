"""DB helpers for staging-certification remediation (v1.4.0).

Idempotent, auditable persistence for:
* terminal Telegram reachability state (users.telegram_reachable)
* outcome corrections (outcome_corrections) with compensating-record design
* terminal duplicate-thesis notification suppression (notification_suppressions)

All functions tolerate an unavailable database (return False/None) so they can
never break the delivery or reconciliation loops.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)


def _session():
    from db.session import session_scope

    return session_scope()


def _now_sql() -> str:
    return "NOW()"


def mark_telegram_unreachable(
    telegram_user_id: int,
    reason: str,
    *,
    session: Any = None,
) -> bool:
    """Mark a user terminally unreachable (chat not found / blocked / deactivated).

    A permanent Telegram error is a terminal reachability event: the resend and
    fanout loops must stop retrying this user every cycle.  Reactivation
    happens only via a fresh inbound update or an owner command.
    """
    try:
        from db.session import get_session

        if session is None:
            with get_session() as sess:
                return _apply(sess, telegram_user_id, reason)
        return _apply(session, telegram_user_id, reason)
    except Exception as exc:  # noqa: BLE001
        logger.debug("mark_telegram_unreachable failed user=%s: %s", telegram_user_id, exc)
        return False


def _apply(session: Any, telegram_user_id: int, reason: str) -> bool:
    safe_reason = str(reason or "unknown")[:128]
    from sqlalchemy import text

    session.execute(
        text(
            f"UPDATE users SET telegram_reachable = FALSE, "
            f"telegram_unreachable_reason = :reason, "
            f"telegram_unreachable_at = {_now_sql()}, "
            f"notification_suppressed = TRUE "
            f"WHERE telegram_user_id = :uid"
        ),
        {"uid": int(telegram_user_id), "reason": safe_reason},
    )
    session.commit()
    return True


def is_telegram_reachable(telegram_user_id: int, *, session: Any = None) -> bool:
    """True when the user has no terminal unreachable marker (default: reachable)."""
    try:
        from sqlalchemy import text

        if session is None:
            from db.session import get_session

            with get_session() as sess:
                return _query_reachable(sess, telegram_user_id)
        return _query_reachable(session, telegram_user_id)
    except Exception as exc:  # noqa: BLE001
        logger.debug("is_telegram_reachable failed user=%s: %s", telegram_user_id, exc)
        return True


def _query_reachable(session: Any, telegram_user_id: int) -> bool:
    from sqlalchemy import text

    row = session.execute(
        text("SELECT telegram_reachable FROM users WHERE telegram_user_id = :uid"),
        {"uid": int(telegram_user_id)},
    ).fetchone()
    if row is None:
        return True
    return bool(row[0])


def record_outcome_correction(
    *,
    signal_id: str,
    original_outcome: str,
    corrected_outcome: str,
    reason: str,
    evidence: Optional[Mapping[str, Any]] = None,
    source: str = "system_reconciliation",
    session: Any = None,
) -> bool:
    """Insert an idempotent outcome-correction record.

    The unique constraint (signal_id, corrected_outcome, correction_version)
    makes re-application a no-op, so corrections cannot double-count.
    """
    try:
        from sqlalchemy import text

        if session is None:
            from db.session import get_session

            with get_session() as sess:
                return _insert_correction(sess, signal_id, original_outcome, corrected_outcome, reason, evidence, source)
        return _insert_correction(session, signal_id, original_outcome, corrected_outcome, reason, evidence, source)
    except Exception as exc:  # noqa: BLE001 - unique-violation conflicts are expected
        logger.debug("record_outcome_correction skipped signal=%s: %s", signal_id, exc)
        return False


def _insert_correction(session, signal_id, original, corrected, reason, evidence, source) -> bool:
    from sqlalchemy import text

    session.execute(
        text(
            f"INSERT INTO outcome_corrections ("
            f" signal_id, original_outcome, corrected_outcome, correction_reason, "
            f" correction_evidence, correction_version, correction_source, created_at"
            f") VALUES (:signal_id, :original, :corrected, :reason, :evidence, 1, :source, {_now_sql()})"
            f" ON CONFLICT (signal_id, corrected_outcome, correction_version) DO NOTHING"
        ),
        {
            "signal_id": str(signal_id),
            "original": str(original or "")[:32],
            "corrected": str(corrected or "")[:32],
            "reason": str(reason or "reconciliation")[:255],
            "evidence": evidence,
            "source": str(source or "system_reconciliation")[:64],
        },
    )
    session.commit()
    return True


def upsert_terminal_suppression(
    notification_key: str,
    *,
    canonical_notification_id: Optional[int] = None,
    reason: str = "duplicate_thesis",
    session: Any = None,
) -> bool:
    """Mark a duplicate-thesis notification terminally suppressed.

    Pending-query loops exclude terminally suppressed keys so the worker never
    rescans the same suppressed duplicate every cycle.
    """
    try:
        from sqlalchemy import text

        if session is None:
            from db.session import get_session

            with get_session() as sess:
                return _insert_suppression(sess, notification_key, canonical_notification_id, reason)
        return _insert_suppression(session, notification_key, canonical_notification_id, reason)
    except Exception as exc:  # noqa: BLE001
        logger.debug("upsert_terminal_suppression skipped key=%s: %s", notification_key, exc)
        return False


def _insert_suppression(session, notification_key, canonical_id, reason) -> bool:
    from sqlalchemy import text

    session.execute(
        text(
            f"INSERT INTO notification_suppressions ("
            f" notification_key, canonical_notification_id, reason, terminal, created_at"
            f") VALUES (:key, :canonical, :reason, TRUE, {_now_sql()})"
            f" ON CONFLICT (notification_key) DO NOTHING"
        ),
        {
            "key": str(notification_key or "")[:255],
            "canonical": canonical_id,
            "reason": str(reason or "duplicate_thesis")[:128],
        },
    )
    session.commit()
    return True


def suppression_keys(
    *,
    terminal_only: bool = True,
    session: Any = None,
) -> set[str]:
    """Set of terminally suppressed notification keys for pending-query exclusion."""
    try:
        from sqlalchemy import text

        if session is None:
            from db.session import get_session

            with get_session() as sess:
                return _query_suppressions(sess, terminal_only)
        return _query_suppressions(session, terminal_only)
    except Exception as exc:  # noqa: BLE001
        logger.debug("suppression_keys unavailable: %s", exc)
        return set()


def _query_suppressions(session, terminal_only: bool) -> set[str]:
    from sqlalchemy import text

    where = "WHERE terminal = TRUE" if terminal_only else ""
    rows = session.execute(text(f"SELECT notification_key FROM notification_suppressions {where}")).fetchall()
    return {str(row[0]) for row in rows}


__all__ = [
    "is_telegram_reachable",
    "mark_telegram_unreachable",
    "record_outcome_correction",
    "suppression_keys",
    "upsert_terminal_suppression",
]
