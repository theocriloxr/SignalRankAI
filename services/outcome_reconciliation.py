"""Canonical reconciliation for proof-backed delivery outcome projections."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select

from core.signal_lifecycle import outcome_status_for_lifecycle
from db.models import Outcome, Signal, SignalDelivery, SignalLifecycle
from db.pg_features import upsert_outcome

_PROOF_STATES = ("sent", "delivered", "confirmed", "updated")


@dataclass(frozen=True, slots=True)
class OutcomeReconciliationResult:
    examined: int = 0
    created_pending: int = 0
    projected_from_lifecycle: int = 0
    unchanged: int = 0
    failed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "examined": self.examined,
            "created_pending": self.created_pending,
            "projected_from_lifecycle": self.projected_from_lifecycle,
            "unchanged": self.unchanged,
            "failed": self.failed,
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


def build_outcome_reconciliation_query(*, cutoff: datetime, limit: int):
    """Build deterministic one-row-per-signal reconciliation SQL.

    PostgreSQL ``DISTINCT ON`` requires its expressions to lead ``ORDER BY``.
    Delivery proofs need chronological ordering instead, so aggregate proof rows
    first and join the canonical signal/lifecycle/outcome records afterwards.
    This helper is intentionally public enough for dialect-compilation tests.
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
    return (
        select(Signal, SignalLifecycle, Outcome)
        .join(proof_candidates, proof_candidates.c.signal_id == Signal.signal_id)
        .outerjoin(SignalLifecycle, SignalLifecycle.signal_id == Signal.signal_id)
        .outerjoin(Outcome, Outcome.signal_id == Signal.signal_id)
        .where(Outcome.id.is_(None))
        .order_by(proof_candidates.c.first_proof_time.asc(), Signal.signal_id.asc())
        .limit(max(1, min(5000, int(limit))))
    )


async def ensure_outcome_projections(
    session,
    *,
    days: int | None = None,
    limit: int | None = None,
) -> OutcomeReconciliationResult:
    """Ensure each Telegram-proof delivery has one canonical Outcome row.

    Active/pending signals receive a non-terminal ``pending`` projection. Durable
    lifecycle states are projected into the outcome table without inventing
    prices. Terminal performance remains excluded until a verified R value exists.
    """
    days = max(1, int(days or os.getenv("OUTCOME_RECONCILIATION_DAYS", "30") or 30))
    limit = max(1, min(5000, int(limit or os.getenv("OUTCOME_RECONCILIATION_LIMIT", "1000") or 1000)))
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    proof_time = func.coalesce(
        SignalDelivery.delivery_confirmed_at,
        SignalDelivery.delivered_at_utc,
        SignalDelivery.delivered_at,
    )
    # PostgreSQL requires every ``DISTINCT ON`` expression to be the leading
    # ORDER BY expression.  The previous ORM query ordered by proof time first
    # and then called ``distinct(Signal.signal_id)``, which compiled to invalid
    # SQL and stopped both outcome and performance reconciliation.  Aggregate
    # delivery proof into one row per signal first, then join the canonical
    # signal/lifecycle/outcome rows in proof-time order.
    query = build_outcome_reconciliation_query(cutoff=cutoff, limit=limit)
    rows = (await session.execute(query)).all()

    examined = created = projected = unchanged = failed = 0
    for signal, lifecycle, outcome in rows:
        examined += 1
        if outcome is not None:
            unchanged += 1
            continue
        try:
            lifecycle_status = outcome_status_for_lifecycle(getattr(lifecycle, "state", None)) if lifecycle else None
            status = str(lifecycle_status or "pending")
            terminal_price = _terminal_price(lifecycle, signal)
            meta = {
                "provenance": "delivery_projection_reconciliation",
                "calculation_policy_version": "outcome-projection-v2",
                "projection_only": True,
                "lifecycle_state": str(getattr(lifecycle, "state", "") or ""),
                "terminal_price": terminal_price,
            }
            await upsert_outcome(
                session,
                str(signal.signal_id),
                status,
                opened_at=getattr(lifecycle, "entry_touched_at", None) if lifecycle else None,
                closed_at=getattr(lifecycle, "closed_at", None) if lifecycle_status else None,
                meta=meta,
                queue_notifications=False,
            )
            if lifecycle_status:
                projected += 1
            else:
                created += 1
        except Exception:
            failed += 1
    await session.flush()
    return OutcomeReconciliationResult(examined, created, projected, unchanged, failed)


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


__all__ = ["OutcomeReconciliationResult", "build_outcome_reconciliation_query", "ensure_outcome_projections", "outcome_projection_health"]
