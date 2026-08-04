"""Canonical reconciliation for proof-backed delivery outcome projections."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, case, func, or_, select

from core.signal_lifecycle import (
    BREAKEVEN_STOP,
    EXPIRED,
    MISSED_ENTRY,
    SL_HIT,
    TP1_HIT,
    TP2_HIT,
    TP3_HIT,
    is_terminal_signal_state,
    outcome_status_for_lifecycle,
)
from db.models import Outcome, Signal, SignalDelivery, SignalLifecycle
from db.pg_features import queue_outcome_notifications_for_outcome, upsert_outcome

_PROOF_STATES = ("sent", "delivered", "confirmed", "reconciled", "updated")
logger = logging.getLogger(__name__)

_SYSTEM_CORRECTION_ACTORS = {
    "system",
    "worker",
    "migration",
    "backfill",
    "reconciliation",
    "outcome_reconciliation",
    "outcome_tracker",
    "auto_repair",
}


def _is_human_corrected(outcome: Outcome | None) -> bool:
    """Return True only for corrections that require human protection."""

    if outcome is None:
        return False

    meta = dict(getattr(outcome, "meta", {}) or {})

    # Explicit metadata always wins.
    if bool(meta.get("human_correction")):
        return True

    actor = str(
        getattr(outcome, "corrected_by", "") or ""
    ).strip().lower()

    # Current system repairs use actors such as:
    # system:v1.3.6.9-outcome-reconciliation
    if actor.startswith("system:"):
        return False

    if actor in _SYSTEM_CORRECTION_ACTORS:
        return False

    # Preserve explicitly identified owner/admin/manual corrections.
    if actor.startswith(("owner:", "admin:", "human:", "manual:")):
        return True

    if actor in {"owner", "admin", "human", "manual"}:
        return True

    # Numeric actors are normally Telegram user IDs.
    if actor.isdigit():
        return True

    provenance = str(
        getattr(outcome, "provenance", "") or ""
    ).strip().lower()

    corrected_at = getattr(outcome, "corrected_at", None)

    # Unknown old audited corrections should fail safely and remain protected.
    return bool(
        actor
        or corrected_at is not None
        or provenance == "audited_correction"
    )

@dataclass(frozen=True, slots=True)
class OutcomeReconciliationResult:
    examined: int = 0
    created_pending: int = 0
    projected_from_lifecycle: int = 0
    repaired_existing: int = 0
    unchanged: int = 0
    failed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "examined": self.examined,
            "created_pending": self.created_pending,
            "projected_from_lifecycle": self.projected_from_lifecycle,
            "repaired_existing": self.repaired_existing,
            "unchanged": self.unchanged,
            "failed": self.failed,
        }


@dataclass(frozen=True, slots=True)
class OutcomeOutboxRepairResult:
    examined_outcomes: int = 0
    queued_notifications: int = 0
    failed_outcomes: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "examined_outcomes": self.examined_outcomes,
            "queued_notifications": self.queued_notifications,
            "failed_outcomes": self.failed_outcomes,
        }


def _terminal_price(lifecycle: SignalLifecycle | None, signal: Signal) -> float | None:
    for value in (
        getattr(lifecycle, "terminal_price", None) if lifecycle is not None else None,
        getattr(lifecycle, "last_price", None) if lifecycle is not None else None,
        getattr(signal, "entry", None),
    ):
        try:
            number = float(value)
            if number > 0:
                return number
        except Exception:
            continue
    return None


def _expected_status_expression():
    state = func.upper(func.coalesce(SignalLifecycle.state, ""))
    return case(
        (state == TP1_HIT, "tp1"),
        (state == TP2_HIT, "tp2"),
        (state == TP3_HIT, "tp3"),
        (state == SL_HIT, "sl"),
        (state == BREAKEVEN_STOP, "partial_win_be"),
        (state == MISSED_ENTRY, "missed_entry"),
        (state == EXPIRED, "expired"),
        else_=None,
    )


def _canonical_outcome(status: str, highest_tp: int) -> str:
    status_l = str(status or "").lower()
    if status_l in {"tp", "tp3"}:
        return "win"
    if status_l in {"tp1", "tp2", "partial_win_be"} or (
        status_l == "sl" and int(highest_tp or 0) > 0
    ):
        return "partial_win"
    if status_l == "sl":
        return "loss"
    if status_l == "time_stop":
        return "time_stop"
    if status_l in {"missed_entry", "expired"}:
        return status_l
    return "pending"


def _projection_metrics(
    signal: Signal,
    lifecycle: SignalLifecycle | None,
    status: str,
    price: float | None,
) -> tuple[float | None, float | None, dict[str, Any]]:
    status_l = str(status or "").lower()
    highest_tp = max(0, min(3, int(getattr(lifecycle, "highest_tp_hit", 0) or 0)))
    if status_l.startswith("tp") and status_l != "tp":
        try:
            highest_tp = max(highest_tp, int(status_l[2:]))
        except Exception:
            pass
    elif status_l == "tp":
        highest_tp = max(highest_tp, 3)

    r_multiple: float | None = None
    percent: float | None = None
    entry = float(getattr(signal, "entry", 0) or 0)
    stop = float(getattr(signal, "stop_loss", 0) or 0)
    price_f = float(price or 0)
    direction = str(getattr(signal, "direction", "") or "").strip().lower()
    if entry > 0 and price_f > 0:
        signed_move = (entry - price_f) if direction in {"short", "sell", "bearish"} else (price_f - entry)
        percent = (signed_move / entry) * 100.0
        risk_distance = abs(entry - stop) if stop > 0 else 0.0
        r_multiple = signed_move / risk_distance if risk_distance > 0 else None
        if status_l == "sl" and r_multiple is not None:
            r_multiple = -abs(r_multiple)
            percent = -abs(percent)
        elif status_l in {"tp", "tp1", "tp2", "tp3"} and r_multiple is not None:
            r_multiple = abs(r_multiple)
            percent = abs(percent)

    partial = None
    if highest_tp > 0 and status_l in {"partial_win_be", "sl"}:
        try:
            from core.partial_exit_accounting import result_from_signal

            # SignalRank's public plan moves the residual stop to breakeven after
            # TP1.  Historical policy and performance reconciliation therefore
            # use a zero-R residual for protected TP1/TP2 exits.
            partial = result_from_signal(signal, min(2, highest_tp), residual_exit_r=0.0)
        except Exception:
            partial = None
        if partial is not None:
            r_multiple = float(partial.realized_r)
            percent = float(partial.realized_percent)
            status_l = "partial_win_be"

    evidence = dict(getattr(lifecycle, "terminal_evidence", {}) or {}) if lifecycle else {}
    meta: dict[str, Any] = {
        "provenance": "delivery_projection_reconciliation",
        "calculation_policy_version": getattr(partial, "policy_version", "outcome-projection-v3"),
        "projection_only": False,
        "recovered_after_persistence_failure": True,
        "lifecycle_state": str(getattr(lifecycle, "state", "") or ""),
        "terminal_price": price,
        "tp_hit_index": highest_tp,
        "tp1_hit": bool(highest_tp >= 1),
        "tp2_hit": bool(highest_tp >= 2),
        "tp3_hit": bool(highest_tp >= 3),
        "terminal_event_type": getattr(lifecycle, "terminal_event_type", None) if lifecycle else None,
        "observation_provider": evidence.get("observation_provider"),
        "observation_high": evidence.get("observation_high"),
        "observation_low": evidence.get("observation_low"),
        "observation_range_time": evidence.get("observation_range_time"),
        "partial_exit_policy": getattr(partial, "policy_version", None),
        "partial_exit_realized_r": getattr(partial, "realized_r", None),
        "partial_exit_realized_percent": getattr(partial, "realized_percent", None),
        "partial_exit_fractions": list(getattr(partial, "fractions", ()) or ()),
        "partial_exit_tp_r_multiples": list(getattr(partial, "tp_r_multiples", ()) or ()),
    }
    return r_multiple, percent, meta


def build_outcome_reconciliation_query(*, cutoff: datetime, limit: int):
    """Build deterministic one-row-per-signal recovery SQL.

    The v1.3.6.8 query only selected signals with no Outcome row.  When the
    tracker had already created a pending projection and then failed while
    promoting it, a terminal lifecycle could never be repaired.  This query also
    selects lifecycle/outcome disagreements and terminal rows missing closed_at.
    """
    proof_time = func.coalesce(
        SignalDelivery.delivery_confirmed_at,
        SignalDelivery.delivered_at_utc,
        SignalDelivery.delivered_at,
    )
    first_proof_time = func.min(proof_time)
    proof_candidates = (
        select(
            SignalDelivery.signal_id.label("signal_id"),
            first_proof_time.label("first_proof_time"),
        )
        .where(
            SignalDelivery.sent_ok.is_(True),
            SignalDelivery.telegram_chat_id.is_not(None),
            SignalDelivery.telegram_message_id.is_not(None),
            func.lower(SignalDelivery.delivery_state).in_(_PROOF_STATES),
            proof_time >= cutoff,
        )
        .group_by(SignalDelivery.signal_id)
        .subquery("proof_delivery_candidates")
    )
    expected_status = _expected_status_expression()
    lifecycle_terminal = func.upper(func.coalesce(SignalLifecycle.state, "")).in_(
        (TP3_HIT, SL_HIT, BREAKEVEN_STOP, MISSED_ENTRY, EXPIRED)
    )
    return (
        select(Signal, SignalLifecycle, Outcome)
        .join(proof_candidates, proof_candidates.c.signal_id == Signal.signal_id)
        .outerjoin(SignalLifecycle, SignalLifecycle.signal_id == Signal.signal_id)
        .outerjoin(Outcome, Outcome.signal_id == Signal.signal_id)
        .where(
            or_(
                Outcome.id.is_(None),
                and_(
                    expected_status.is_not(None),
                    or_(
                        func.lower(func.coalesce(Outcome.status, "")) != expected_status,
                        and_(lifecycle_terminal, Outcome.closed_at.is_(None)),
                    ),
                ),
            )
        )
        .order_by(proof_candidates.c.first_proof_time.asc(), Signal.signal_id.asc())
        .limit(max(1, min(5000, int(limit))))
    )


async def ensure_outcome_projections(
    session,
    *,
    days: int | None = None,
    limit: int | None = None,
    queue_notifications: bool = True,
) -> OutcomeReconciliationResult:
    """Create missing projections and repair lifecycle/outcome disagreements."""
    days = max(1, int(days or os.getenv("OUTCOME_RECONCILIATION_DAYS", "30") or 30))
    limit = max(1, min(5000, int(limit or os.getenv("OUTCOME_RECONCILIATION_LIMIT", "1000") or 1000)))
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    rows = (await session.execute(build_outcome_reconciliation_query(cutoff=cutoff, limit=limit))).all()

    examined = created = projected = repaired = unchanged = failed = 0
    terminal_statuses = {
        "tp", "tp3", "win", "sl", "loss", "stop", "stop_loss",
        "be", "breakeven", "break_even", "partial_win", "partial_win_be",
        "time_stop", "expired", "missed_entry", "cancel", "cancelled",
        "tracking_failed", "invalid", "invalidated",
    }
    for signal, lifecycle, outcome in rows:
        examined += 1

        # Capture primitive values before opening the savepoint. ORM objects may be
        # expired after a savepoint rollback and must not be accessed in the except
        # handler.
        signal_id = str(getattr(signal, "signal_id", "") or "")
        lifecycle_state_for_log = (
            str(getattr(lifecycle, "state", "") or "")
            if lifecycle is not None
            else ""
        )
        existing_status_for_log = (
            str(getattr(outcome, "status", "") or "")
            if outcome is not None
            else ""
        )

        try:
            # A savepoint keeps a malformed historical row from aborting every
            # remaining signal in the recovery batch.
            async with session.begin_nested():
                lifecycle_status = outcome_status_for_lifecycle(getattr(lifecycle, "state", None)) if lifecycle else None
                status = str(lifecycle_status or "pending")
                terminal = bool(lifecycle and is_terminal_signal_state(getattr(lifecycle, "state", None)))
                current_status = str(getattr(outcome, "status", "") or "").lower() if outcome is not None else ""
                current_closed = getattr(outcome, "closed_at", None) if outcome is not None else None
                if outcome is not None and current_status == status and (not terminal or current_closed is not None):
                    unchanged += 1
                    continue

                # Never overwrite an explicit human/audited correction during an
                # automated replay.  Those rows require operator review instead.
                human_corrected = _is_human_corrected(outcome)
                if human_corrected:
                    unchanged += 1
                    logger.warning(
                        "[outcome_reconciliation] skipped human-corrected row "
                        "signal=%s existing=%s expected=%s corrected_by=%s",
                        signal_id,
                        current_status,
                        status,
                        getattr(outcome, "corrected_by", None),
                    )
                    continue

                terminal_price = _terminal_price(lifecycle, signal)
                r_multiple, percent, meta = _projection_metrics(signal, lifecycle, status, terminal_price)
                highest_tp = int(meta.get("tp_hit_index") or 0)
                canonical = _canonical_outcome(status, highest_tp)
                if status == "sl" and highest_tp > 0 and meta.get("partial_exit_policy"):
                    status = "partial_win_be"
                    canonical = "partial_win"

                # Existing finalized rows are immutable by design.  Recovery is
                # therefore an attributed system correction, not a silent edit.
                if outcome is not None and current_status in terminal_statuses:
                    meta.update({
                        "audited_correction": True,
                        "corrected_by": "system:v1.3.6.9-outcome-reconciliation",
                        "correction_reason": (
                            "repair lifecycle/outcome disagreement or missing terminal timestamp "
                            "after v1.3.6.8 outcome persistence failure"
                        ),
                    })

                projected_outcome = await upsert_outcome(
                    session,
                    signal_id,
                    status,
                    r_multiple=r_multiple,
                    percent=percent,
                    opened_at=getattr(lifecycle, "entry_touched_at", None) if lifecycle else None,
                    closed_at=getattr(lifecycle, "closed_at", None) if terminal else None,
                    canonical_outcome=canonical,
                    vip_fill_outcome="pending",
                    sentiment_outcome="pending",
                    meta=meta,
                    queue_notifications=queue_notifications,
                )
                if outcome is None:
                    if lifecycle_status:
                        projected += 1
                    else:
                        created += 1
                else:
                    repaired += 1

                # ``upsert_outcome`` only queues when it detects a changed row.
                # This idempotent call also repairs terminal rows that predate the
                # outbox or were closed during the v1.3.6.8 persistence outage.
                if (
                    queue_notifications
                    and terminal
                    and getattr(projected_outcome, "closed_at", None) is not None
                ):
                    await queue_outcome_notifications_for_outcome(
                        session,
                        int(getattr(projected_outcome, "id")),
                        signal_id,
                        status,
                    )
        except Exception as exc:
            failed += 1
            logger.exception(
                "[outcome_reconciliation] signal repair failed "
                "signal=%s lifecycle=%s existing=%s error=%s",
                signal_id,
                lifecycle_state_for_log,
                existing_status_for_log,
                exc,
            )
    await session.flush()
    return OutcomeReconciliationResult(examined, created, projected, repaired, unchanged, failed)


def build_outbox_repair_query(*, cutoff: datetime, limit: int, after_id: int = 0, after_closed_at=None):
    """Set-based repair candidate query using NOT EXISTS.

    Excludes outcomes that already have a notification row for the same
    (outcome_id, outcome_status), permanently suppressed duplicate theses, and
    signals with no delivered qualifying recipient. Uses a stable keyset cursor
    (closed_at, id) so bounded batches never re-scan the same rows.
    """
    from db.models import OutcomeNotification, SignalDelivery

    # An outcome already has outbox coverage for its current status when any
    # notification row exists with the same outcome_id and status. Pending rows
    # are also coverage: duplicates are invalid and must not be re-created.
    existing_notification = (
        select(OutcomeNotification.id)
        .where(
            OutcomeNotification.outcome_id == Outcome.id,
            OutcomeNotification.outcome_status == func.lower(func.coalesce(Outcome.status, "")),
        )
        .limit(1)
    )

    # Signals with zero proof-backed delivery rows cannot have recipients.
    has_delivery_recipient = (
        select(SignalDelivery.id)
        .where(
            SignalDelivery.signal_id == Outcome.signal_id,
            SignalDelivery.sent_ok.is_(True),
        )
        .limit(1)
    )

    cursor = [Outcome.closed_at.is_not(None), Outcome.closed_at >= cutoff]
    if after_id > 0:
        if after_closed_at is not None:
            cursor.append(
                or_(
                    Outcome.closed_at > after_closed_at,
                    and_(Outcome.closed_at == after_closed_at, Outcome.id > after_id),
                )
            )
        else:
            cursor.append(Outcome.id > after_id)

    return (
        select(Outcome)
        .where(
            *cursor,
            ~existing_notification.exists(),
            has_delivery_recipient.exists(),
        )
        .order_by(Outcome.closed_at.asc(), Outcome.id.asc())
        .limit(max(1, min(10000, int(limit))))
    )


async def repair_outcome_notification_outbox(
    session,
    *,
    days: int | None = None,
    limit: int | None = None,
) -> OutcomeOutboxRepairResult:
    """Idempotently recreate missing recipient outbox rows for closed outcomes.

    The candidate query is set-based (NOT EXISTS + keyset cursor): outcomes that
    already have coverage for their current status, or whose signals have no
    delivered recipients, are excluded in SQL instead of being scanned row by
    row and discovered as already-processed.
    """
    days = max(1, int(days or os.getenv("OUTCOME_OUTBOX_REPAIR_DAYS", "30") or 30))
    limit = max(1, min(10000, int(limit or os.getenv("OUTCOME_OUTBOX_REPAIR_LIMIT", "2000") or 2000)))
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    outcomes: list[Outcome] = []
    after_id = 0
    after_closed_at = None
    while len(outcomes) < limit:
        page = list((await session.execute(
            build_outbox_repair_query(
                cutoff=cutoff,
                limit=min(limit - len(outcomes), 500),
                after_id=after_id,
                after_closed_at=after_closed_at,
            )
        )).scalars().all())
        if not page:
            break
        outcomes.extend(page)
        last = page[-1]
        after_id = int(getattr(last, "id") or 0)
        after_closed_at = getattr(last, "closed_at", None)
    queued = failed = 0
    
    for outcome in outcomes:
        outcome_id = int(getattr(outcome, "id"))
        outcome_signal_id = str(getattr(outcome, "signal_id", "") or "")
        outcome_status = str(getattr(outcome, "status", "") or "")

        try:
            async with session.begin_nested():
                queued += await queue_outcome_notifications_for_outcome(
                    session,
                    outcome_id,
                    outcome_signal_id,
                    outcome_status,
                )
        except Exception as exc:
            failed += 1
            logger.exception(
                "[outcome_outbox_repair] failed "
                "outcome_id=%s signal=%s status=%s error=%s",
                outcome_id,
                outcome_signal_id,
                outcome_status,
                exc,
            )
    await session.flush()
    return OutcomeOutboxRepairResult(len(outcomes), queued, failed)


async def outcome_projection_health(session, *, days: int = 30) -> dict[str, float | int | bool]:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(1, int(days)))
    proof_time = func.coalesce(
        SignalDelivery.delivery_confirmed_at,
        SignalDelivery.delivered_at_utc,
        SignalDelivery.delivered_at,
    )
    delivered = int((await session.execute(
        select(func.count(func.distinct(SignalDelivery.signal_id))).where(
            SignalDelivery.sent_ok.is_(True),
            SignalDelivery.telegram_chat_id.is_not(None),
            SignalDelivery.telegram_message_id.is_not(None),
            func.lower(SignalDelivery.delivery_state).in_(_PROOF_STATES),
            proof_time >= cutoff,
        )
    )).scalar_one() or 0)
    with_outcome = int((await session.execute(
        select(func.count(func.distinct(SignalDelivery.signal_id)))
        .join(Outcome, Outcome.signal_id == SignalDelivery.signal_id)
        .where(
            SignalDelivery.sent_ok.is_(True),
            SignalDelivery.telegram_chat_id.is_not(None),
            SignalDelivery.telegram_message_id.is_not(None),
            func.lower(SignalDelivery.delivery_state).in_(_PROOF_STATES),
            proof_time >= cutoff,
        )
    )).scalar_one() or 0)
    coverage = with_outcome / delivered if delivered else 1.0
    return {
        "ok": coverage >= float(os.getenv("OUTCOME_PROJECTION_MIN_COVERAGE", "0.99") or 0.99),
        "delivered_signals": delivered,
        "with_outcome_projection": with_outcome,
        "missing_outcome_projection": max(0, delivered - with_outcome),
        "coverage": coverage,
    }


__all__ = [
    "OutcomeOutboxRepairResult",
    "OutcomeReconciliationResult",
    "build_outcome_reconciliation_query",
    "ensure_outcome_projections",
    "outcome_projection_health",
    "repair_outcome_notification_outbox",
]
