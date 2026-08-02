"""Canonical proof-backed performance ledger and reconciliation formulas."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
from typing import Any, Iterable
from uuid import uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.delivery_state import CONFIRMED_DELIVERY_STATES
from db.models import (
    Outcome,
    PerformanceCorrectionAudit,
    PerformanceLedgerEntry,
    Signal,
    SignalDelivery,
    SignalLifecycle,
    MLPastTrainingData,
    User,
    UserSignalMonitoring,
)
from core.env import runtime_environment_name
from core.production_integrity import (
    evaluate_public_win_rate_claim,
    semantic_entries_equivalent,
    signal_thesis_fingerprint,
    signal_thesis_scope,
)
from core.partial_exit_accounting import result_from_signal
from utils.timeutils import now_utc_naive


PERFORMANCE_POLICY_VERSION = "proof-ledger-v2-partial-exit"
PERFORMANCE_DOMAIN = "live_user_delivery"
COMPLETED_BUCKETS = frozenset({"STOPPED_AT_TP1", "STOPPED_AT_TP2", "TP3", "SL", "BREAKEVEN", "TIME_STOP"})
NON_TRADE_BUCKETS = frozenset({
    "MISSED_ENTRY", "EXPIRED", "CANCELLED", "TRACKING_FAILED",
    "PROVIDER_UNAVAILABLE", "DUPLICATE_EXCLUDED",
})


@dataclass(frozen=True, slots=True)
class PerformanceReconciliationResult:
    users_examined: int = 0
    rows_changed: int = 0
    failed_users: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "users_examined": int(self.users_examined),
            "rows_changed": int(self.rows_changed),
            "failed_users": int(self.failed_users),
        }


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except Exception:
        return None
    return result if result.is_finite() else None


def _status(value: Any) -> str:
    return str(value or "").strip().lower()


def _classify(
    *,
    signal: Signal,
    outcome: Outcome | None,
    lifecycle: SignalLifecycle | None,
    monitoring: UserSignalMonitoring | None,
) -> tuple[str, Decimal | None, str, bool, str | None]:
    if monitoring is not None and _status(monitoring.status) == "stopped":
        stage = int(monitoring.stopped_at_stage or 0)
        final_r = _decimal(monitoring.realized_r)
        if stage in {1, 2} and final_r is not None:
            return f"STOPPED_AT_TP{stage}", final_r, "user_monitoring_stop", True, None

    raw_status = _status(getattr(outcome, "status", None))
    canonical_status = _status(getattr(outcome, "canonical_outcome", None))
    lifecycle_highest = int(getattr(lifecycle, "highest_tp_hit", 0) or 0)
    outcome_meta = dict(getattr(outcome, "meta", {}) or {}) if outcome is not None else {}
    highest_tp = max(lifecycle_highest, int(outcome_meta.get("tp_hit_index") or 0))
    terminal_event_type = _status(
        getattr(lifecycle, "terminal_event_type", None)
        or outcome_meta.get("terminal_event_type")
    )
    protected_exit_evidence = terminal_event_type == "breakeven_stop" and highest_tp > 0

    # A protected exit after TP1/TP2 is a partial result, not a full stop. Older
    # rows often contain r_multiple=-1 because the tracker persisted the original
    # SL price even though the lifecycle terminal event was breakeven_stop. Rebuild
    # the realized result from the immutable signal plan and highest TP evidence.
    if protected_exit_evidence or raw_status in {"partial_win_be", "partial_win"} or (
        canonical_status == "partial_win" and highest_tp > 0
    ):
        stage = 2 if highest_tp >= 2 else (1 if highest_tp >= 1 else 0)
        partial = result_from_signal(signal, stage, residual_exit_r=0.0) if stage else None
        final_r = _decimal(partial.realized_r if partial is not None else getattr(outcome, "r_multiple", None))
        if stage in {1, 2} and final_r is not None:
            return f"STOPPED_AT_TP{stage}", final_r, "lifecycle_partial_exit", True, None
        if final_r is not None:
            return "BREAKEVEN", final_r, "lifecycle_partial_exit", True, None
        return "BREAKEVEN", None, "lifecycle_partial_exit", False, "partial_exit_missing_realized_r"

    final_status = canonical_status or raw_status
    final_r = _decimal(getattr(outcome, "r_multiple", None))
    mappings = {
        "tp": "TP3", "tp3": "TP3", "win": "TP3",
        "sl": "SL", "loss": "SL", "stop": "SL", "stop_loss": "SL",
        "be": "BREAKEVEN", "breakeven": "BREAKEVEN", "break_even": "BREAKEVEN",
        "time_stop": "TIME_STOP",
        "missed": "MISSED_ENTRY", "missed_entry": "MISSED_ENTRY", "entry_missed": "MISSED_ENTRY",
        "expired": "EXPIRED",
        "cancelled": "CANCELLED", "canceled": "CANCELLED", "superseded": "CANCELLED",
        "tracking_failed": "TRACKING_FAILED", "provider_unavailable": "PROVIDER_UNAVAILABLE",
    }
    if final_status in mappings:
        bucket = mappings[final_status]
        if bucket in COMPLETED_BUCKETS and final_r is None:
            return bucket, None, "canonical_outcome", False, "terminal_outcome_missing_final_r"
        return bucket, final_r if bucket in COMPLETED_BUCKETS else None, "canonical_outcome", True, None

    lifecycle_state = _status(getattr(lifecycle, "state", None))
    signal_state = _status(getattr(signal, "status", None))
    if lifecycle_state in {"active_trade", "tp1_hit", "tp2_hit"} or signal_state in {"active", "open", "running"}:
        return "ACTIVE", None, "signal_lifecycle", True, None
    if lifecycle_state in {"tracking_failed", "outcome_failed"} or signal_state in {"tracking_failed", "outcome_failed"}:
        return "TRACKING_FAILED", None, "signal_lifecycle", True, None
    return "PENDING_ENTRY", None, "signal_lifecycle", True, None


def _snapshot_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


async def repair_partial_exit_outcomes(
    session,
    *,
    days: int | None = None,
    limit: int | None = None,
) -> int:
    """Repair historical TP1/TP2 protected exits and their ML labels.

    v1.3.6.6 correctly persisted lifecycle ``partial_win_be`` states but older
    accounting stored the original SL as -1R. This bounded, idempotent repair is
    run by the worker before performance reconciliation. Explicit human outcome
    corrections are never overwritten.
    """
    days = max(1, int(days or os.getenv("PARTIAL_EXIT_REPAIR_DAYS", "365") or 365))
    limit = max(1, min(10000, int(limit or os.getenv("PARTIAL_EXIT_REPAIR_LIMIT", "2000") or 2000)))
    cutoff = now_utc_naive() - timedelta(days=days)
    rows = (await session.execute(
        select(Outcome, Signal, SignalLifecycle)
        .join(Signal, Signal.signal_id == Outcome.signal_id)
        .outerjoin(SignalLifecycle, SignalLifecycle.signal_id == Outcome.signal_id)
        .where(
            Outcome.closed_at.is_not(None),
            Outcome.closed_at >= cutoff,
            Outcome.corrected_at.is_(None),
            (
                func.lower(Outcome.status).in_(("partial_win_be", "partial_win"))
                | (
                    (func.lower(Outcome.canonical_outcome) == "partial_win")
                    & (SignalLifecycle.highest_tp_hit > 0)
                )
                | (
                    (func.lower(SignalLifecycle.terminal_event_type) == "breakeven_stop")
                    & (SignalLifecycle.highest_tp_hit > 0)
                )
            ),
        )
        .order_by(Outcome.closed_at.asc(), Outcome.id.asc())
        .limit(limit)
    )).all()
    signal_ids = [str(signal.signal_id) for _outcome, signal, _lifecycle in rows]
    training_by_signal: dict[str, MLPastTrainingData] = {}
    if signal_ids:
        training_rows = list((await session.execute(
            select(MLPastTrainingData).where(MLPastTrainingData.signal_id.in_(signal_ids))
        )).scalars().all())
        training_by_signal = {str(row.signal_id): row for row in training_rows}

    changed = 0
    for outcome, signal, lifecycle in rows:
        meta = dict(getattr(outcome, "meta", {}) or {})
        highest_tp = max(
            int(getattr(lifecycle, "highest_tp_hit", 0) or 0),
            int(meta.get("tp_hit_index") or 0),
        )
        stage = 2 if highest_tp >= 2 else (1 if highest_tp >= 1 else 0)
        if stage <= 0:
            continue
        result = result_from_signal(signal, stage, residual_exit_r=0.0)
        if result is None:
            continue
        target_r = float(result.realized_r)
        target_pct = float(result.realized_percent)
        already_current = (
            str(getattr(outcome, "calculation_policy_version", "") or "") == result.policy_version
            and abs(float(getattr(outcome, "r_multiple", 0.0) or 0.0) - target_r) < 1e-9
        )
        if already_current:
            continue
        outcome.status = "partial_win_be"
        outcome.canonical_outcome = "partial_win"
        outcome.r_multiple = target_r
        outcome.percent = target_pct
        outcome.pnl_pct = target_pct
        outcome.calculation_policy_version = result.policy_version
        outcome.terminal_version = int(getattr(outcome, "terminal_version", 0) or 0) + 1
        meta.update({
            "tp_hit_index": stage,
            "tp1_hit": True,
            "tp2_hit": bool(stage >= 2),
            "reversed_after_tp": True,
            "partial_exit_policy": result.policy_version,
            "partial_exit_realized_r": target_r,
            "partial_exit_realized_percent": target_pct,
            "partial_exit_fractions": list(result.fractions),
            "partial_exit_tp_r_multiples": list(result.tp_r_multiples),
            "systemic_repair": "v1.3.6.7_partial_exit_accounting",
        })
        outcome.meta = meta
        training = training_by_signal.get(str(signal.signal_id))
        if training is not None:
            training.outcome_status = "win" if target_r > 0 else "breakeven"
            training.outcome_r_multiple = target_r
            training.outcome_percent = target_pct
            training_meta = dict(getattr(training, "outcome_meta", {}) or {})
            training_meta.update({
                "raw_r_multiple": target_r,
                "training_r_multiple": target_r,
                "partial_exit_policy": result.policy_version,
                "systemic_repair": "v1.3.6.7_partial_exit_accounting",
            })
            training.outcome_meta = training_meta
        changed += 1
    await session.flush()
    return changed


async def reconcile_user_performance_ledger(
    session,
    *,
    telegram_user_id: int,
    environment: str | None = None,
) -> int:
    """Reconcile canonical rows with a race-safe PostgreSQL upsert.

    Concurrent /performance requests previously selected an empty scope and
    then both inserted it, causing ``uq_performance_ledger_scope`` violations.
    The bulk ON CONFLICT statement makes the operation idempotent across
    replicas while preserving finalized rows.
    """
    user = (
        await session.execute(select(User).where(User.telegram_user_id == int(telegram_user_id)).limit(1))
    ).scalar_one_or_none()
    if user is None:
        return 0
    env = str(environment or runtime_environment_name("development") or "development").lower()
    states = tuple(CONFIRMED_DELIVERY_STATES)
    rows = (
        await session.execute(
            select(SignalDelivery, Signal, Outcome, SignalLifecycle, UserSignalMonitoring)
            .join(Signal, Signal.signal_id == SignalDelivery.signal_id)
            .outerjoin(Outcome, Outcome.signal_id == SignalDelivery.signal_id)
            .outerjoin(SignalLifecycle, SignalLifecycle.signal_id == SignalDelivery.signal_id)
            .outerjoin(
                UserSignalMonitoring,
                and_(
                    UserSignalMonitoring.user_id == SignalDelivery.user_id,
                    UserSignalMonitoring.signal_id == SignalDelivery.signal_id,
                ),
            )
            .where(
                SignalDelivery.user_id == int(user.id),
                SignalDelivery.sent_ok.is_(True),
                func.lower(SignalDelivery.delivery_state).in_(states),
                SignalDelivery.telegram_chat_id.is_not(None),
                SignalDelivery.telegram_message_id.is_not(None),
                SignalDelivery.delivery_confirmed_at.is_not(None),
            )
            .order_by(SignalDelivery.delivery_confirmed_at.asc(), SignalDelivery.id.asc())
        )
    ).all()
    signal_ids = {str(signal.signal_id) for _delivery, signal, *_rest in rows}
    existing_entries = []
    if signal_ids:
        existing_entries = list(
            (
                await session.execute(
                    select(PerformanceLedgerEntry).where(
                        PerformanceLedgerEntry.user_id == int(user.id),
                        PerformanceLedgerEntry.signal_id.in_(signal_ids),
                        PerformanceLedgerEntry.domain == PERFORMANCE_DOMAIN,
                        PerformanceLedgerEntry.environment == env,
                    )
                )
            ).scalars().all()
        )
    existing_by_signal = {str(entry.signal_id): entry for entry in existing_entries}
    upsert_by_signal: dict[str, dict[str, Any]] = {}
    try:
        duplicate_window = timedelta(hours=max(1, int(os.getenv("SIGNAL_THESIS_DEDUP_HOURS", "4") or 4)))
    except Exception:
        duplicate_window = timedelta(hours=4)
    canonical_thesis_deliveries: dict[str, list[tuple[float, datetime, str, str]]] = {}

    for delivery, signal, outcome, lifecycle, monitoring in rows:
        bucket, final_r, source, included, exclusion = _classify(
            signal=signal, outcome=outcome, lifecycle=lifecycle, monitoring=monitoring,
        )
        thesis_payload = {
            "asset": signal.asset,
            "direction": signal.direction,
            "strategy_name": signal.strategy_name,
            "regime": signal.regime,
            "entry": signal.entry,
            "timeframe": signal.timeframe,
        }
        current_thesis_fingerprint = signal_thesis_fingerprint(thesis_payload)
        delivery_time = delivery.delivery_confirmed_at or delivery.delivered_at
        semantic_key = signal_thesis_scope(thesis_payload)
        try:
            signal_entry = float(signal.entry or 0.0)
        except Exception:
            signal_entry = 0.0
        duplicate_of = None
        duplicate_fingerprint = None
        if delivery_time is not None and signal_entry > 0:
            for prior_entry, prior_time, prior_signal_id, prior_fingerprint in canonical_thesis_deliveries.get(semantic_key, []):
                delta = delivery_time - prior_time
                if delta.total_seconds() < 0 or delta > duplicate_window:
                    continue
                if semantic_entries_equivalent(prior_entry, signal_entry):
                    duplicate_of = prior_signal_id
                    duplicate_fingerprint = prior_fingerprint
                    break
        if duplicate_of is not None:
            bucket = "DUPLICATE_EXCLUDED"
            final_r = None
            source = "delivery_integrity"
            included = False
            exclusion = f"duplicate_thesis_delivery_within_cooldown:{duplicate_of}"
            current_thesis_fingerprint = duplicate_fingerprint or current_thesis_fingerprint
        elif delivery_time is not None and signal_entry > 0:
            canonical_thesis_deliveries.setdefault(semantic_key, []).append(
                (signal_entry, delivery_time, str(signal.signal_id), current_thesis_fingerprint)
            )

        payload = {
            "delivery_id": int(delivery.id),
            "bucket": bucket,
            "final_r": str(final_r) if final_r is not None else None,
            "outcome_id": getattr(outcome, "id", None),
            "monitoring_id": getattr(monitoring, "id", None),
            "policy": PERFORMANCE_POLICY_VERSION,
        }
        canonical_signal_id = str(signal.signal_id)
        existing = existing_by_signal.get(canonical_signal_id)
        # Finalized rows are immutable within one accounting policy, but a new
        # audited policy version must be allowed to repair historical systemic
        # misclassification. Explicit human corrections remain immutable.
        if (
            existing is not None
            and existing.finalized_at is not None
            and str(existing.calculation_policy_version or "") == PERFORMANCE_POLICY_VERSION
        ):
            continue
        if existing is not None and existing.corrected_at is not None:
            continue
        now = now_utc_naive()
        snapshot_hash = _snapshot_hash(payload)
        if existing is not None and existing.snapshot_hash == snapshot_hash:
            continue
        finalized_at = None
        outcome_completed_at = getattr(outcome, "closed_at", None) or getattr(monitoring, "stopped_at", None)
        if bucket in COMPLETED_BUCKETS and final_r is not None and included:
            finalized_at = outcome_completed_at or now
        upsert_by_signal[canonical_signal_id] = {
            "ledger_id": str(uuid4()),
            "user_id": int(user.id),
            "signal_id": canonical_signal_id,
            "domain": PERFORMANCE_DOMAIN,
            "environment": env,
            "delivery_id": int(delivery.id),
            "delivery_confirmed_at": delivery.delivery_confirmed_at,
            "asset": str(signal.asset),
            # Always recompute with the current semantic policy so legacy rows
            # whose stored fingerprint included volatile regime/timeframe values
            # are grouped correctly during historical repair.
            "thesis_fingerprint": current_thesis_fingerprint,
            "timeframe": str(signal.timeframe or ""),
            "direction": str(signal.direction or ""),
            "primary_bucket": bucket,
            "entry_status": "entered" if bucket not in {"PENDING_ENTRY", "MISSED_ENTRY", "EXPIRED"} else "not_entered",
            "highest_tp": int(getattr(lifecycle, "highest_tp_hit", 0) or 0),
            "global_outcome": _status(getattr(outcome, "canonical_outcome", None) or getattr(outcome, "status", None)) or None,
            "user_monitoring_outcome": _status(getattr(monitoring, "realized_outcome", None)) or None,
            "final_realized_r": float(final_r) if final_r is not None else None,
            "outcome_completed_at": outcome_completed_at,
            "outcome_source": source,
            "calculation_policy_version": PERFORMANCE_POLICY_VERSION,
            "signal_plan_version": str((getattr(signal, "meta", {}) or {}).get("signal_plan_version") or "legacy-plan-v1"),
            "included": bool(included),
            "exclusion_reason": exclusion,
            "snapshot_hash": snapshot_hash,
            "row_version": 1,
            "finalized_at": finalized_at,
            "created_at": now,
            "updated_at": now,
        }

    pending = list(upsert_by_signal.values())
    if not pending:
        return 0

    dialect_name = str(session.get_bind().dialect.name or "").lower()
    if dialect_name == "postgresql":
        insert_stmt = pg_insert(PerformanceLedgerEntry).values(pending)
        excluded = insert_stmt.excluded
        mutable_columns = (
            "delivery_id", "delivery_confirmed_at", "asset", "thesis_fingerprint", "timeframe", "direction",
            "primary_bucket", "entry_status", "highest_tp", "global_outcome",
            "user_monitoring_outcome", "final_realized_r", "outcome_completed_at",
            "outcome_source", "calculation_policy_version", "signal_plan_version",
            "included", "exclusion_reason", "snapshot_hash", "finalized_at", "updated_at",
        )
        statement = insert_stmt.on_conflict_do_update(
            constraint="uq_performance_ledger_scope",
            set_={
                **{name: getattr(excluded, name) for name in mutable_columns},
                "row_version": PerformanceLedgerEntry.row_version + 1,
            },
            where=and_(
                PerformanceLedgerEntry.corrected_at.is_(None),
                PerformanceLedgerEntry.snapshot_hash.is_distinct_from(excluded.snapshot_hash),
                (
                    PerformanceLedgerEntry.finalized_at.is_(None)
                    | (PerformanceLedgerEntry.calculation_policy_version != PERFORMANCE_POLICY_VERSION)
                ),
            ),
        )
        await session.execute(statement)
    else:
        # Test/development fallback for non-PostgreSQL databases.
        for values in pending:
            existing = existing_by_signal.get(str(values["signal_id"]))
            if existing is None:
                session.add(PerformanceLedgerEntry(**values))
            elif (
                existing.corrected_at is None
                and existing.snapshot_hash != values["snapshot_hash"]
                and (
                    existing.finalized_at is None
                    or str(existing.calculation_policy_version or "") != PERFORMANCE_POLICY_VERSION
                )
            ):
                for key, value in values.items():
                    if key not in {"ledger_id", "user_id", "signal_id", "domain", "environment", "created_at"}:
                        setattr(existing, key, value)
                existing.row_version = int(existing.row_version or 0) + 1
        await session.flush()
    return len(pending)


@dataclass(frozen=True, slots=True)
class PerformanceMetrics:
    net_r: Decimal
    average_r: Decimal | None
    median_r: Decimal | None
    standardized_simple_return_pct: Decimal
    average_standardized_return_pct: Decimal | None
    standardized_compounded_return_pct: Decimal
    completed_r_count: int
    positive_r_count: int


def calculate_performance_metrics(
    values: Iterable[Any], *, risk_fraction: Decimal = Decimal("0.01")
) -> PerformanceMetrics:
    r_values = [value for value in (_decimal(item) for item in values) if value is not None]
    net = sum(r_values, Decimal("0"))
    count = len(r_values)
    average = net / count if count else None
    med = Decimal(str(median(r_values))) if count else None
    compounded = Decimal("1")
    for value in r_values:
        compounded *= Decimal("1") + value * risk_fraction
    quant = Decimal("0.0001")
    return PerformanceMetrics(
        net_r=net.quantize(quant, rounding=ROUND_HALF_UP),
        average_r=average.quantize(quant, rounding=ROUND_HALF_UP) if average is not None else None,
        median_r=med.quantize(quant, rounding=ROUND_HALF_UP) if med is not None else None,
        standardized_simple_return_pct=(net * risk_fraction * Decimal("100")).quantize(quant, rounding=ROUND_HALF_UP),
        average_standardized_return_pct=(average * risk_fraction * Decimal("100")).quantize(quant, rounding=ROUND_HALF_UP) if average is not None else None,
        standardized_compounded_return_pct=((compounded - Decimal("1")) * Decimal("100")).quantize(quant, rounding=ROUND_HALF_UP),
        completed_r_count=count,
        positive_r_count=sum(1 for value in r_values if value > 0),
    )


async def reconcile_all_performance_ledgers(
    session,
    *,
    days: int | None = None,
    limit_users: int | None = None,
    environment: str | None = None,
) -> PerformanceReconciliationResult:
    """Continuously project proof-backed deliveries into every user's ledger.

    Performance truth must not depend on a user invoking ``/performance``. The
    worker calls this bounded sweep after outcome projection reconciliation.
    """
    days = max(1, int(days or os.getenv("PERFORMANCE_RECONCILIATION_DAYS", "30") or 30))
    limit_users = max(1, min(5000, int(
        limit_users or os.getenv("PERFORMANCE_RECONCILIATION_USER_LIMIT", "500") or 500
    )))
    cutoff = now_utc_naive() - timedelta(days=days)
    proof_time = func.coalesce(
        SignalDelivery.delivery_confirmed_at,
        SignalDelivery.delivered_at_utc,
        SignalDelivery.delivered_at,
    )
    telegram_ids = list((await session.execute(
        select(User.telegram_user_id)
        .join(SignalDelivery, SignalDelivery.user_id == User.id)
        .where(
            SignalDelivery.sent_ok.is_(True),
            func.lower(SignalDelivery.delivery_state).in_(tuple(CONFIRMED_DELIVERY_STATES)),
            SignalDelivery.telegram_chat_id.is_not(None),
            SignalDelivery.telegram_message_id.is_not(None),
            proof_time >= cutoff,
        )
        .distinct()
        .order_by(User.telegram_user_id.asc())
        .limit(limit_users)
    )).scalars().all())
    changed = failed = 0
    env = str(environment or runtime_environment_name("development") or "development").lower()
    for telegram_id in telegram_ids:
        try:
            changed += int(await reconcile_user_performance_ledger(
                session, telegram_user_id=int(telegram_id), environment=env
            ) or 0)
        except Exception:
            failed += 1
    await session.flush()
    return PerformanceReconciliationResult(len(telegram_ids), changed, failed)


async def performance_ledger_health(
    session,
    *,
    days: int = 30,
    environment: str | None = None,
) -> dict[str, Any]:
    """Return production-readiness invariants for the canonical ledger.

    This checks projection completeness and malformed terminal rows. It does not
    pretend that a fresh delivery cohort is already terminal; public claims use
    the stricter matured-cohort Wilson gate in ``evaluate_public_win_rate_claim``.
    """
    env = str(environment or runtime_environment_name("development") or "development").lower()
    cutoff = now_utc_naive() - timedelta(days=max(1, int(days)))
    proof_time = func.coalesce(
        SignalDelivery.delivery_confirmed_at,
        SignalDelivery.delivered_at_utc,
        SignalDelivery.delivered_at,
    )
    proof_deliveries = int((await session.execute(
        select(func.count(SignalDelivery.id)).where(
            SignalDelivery.sent_ok.is_(True),
            func.lower(SignalDelivery.delivery_state).in_(tuple(CONFIRMED_DELIVERY_STATES)),
            SignalDelivery.telegram_chat_id.is_not(None),
            SignalDelivery.telegram_message_id.is_not(None),
            proof_time >= cutoff,
        )
    )).scalar_one() or 0)
    ledger_rows = int((await session.execute(
        select(func.count(PerformanceLedgerEntry.ledger_id)).where(
            PerformanceLedgerEntry.domain == PERFORMANCE_DOMAIN,
            PerformanceLedgerEntry.environment == env,
            PerformanceLedgerEntry.delivery_confirmed_at >= cutoff,
        )
    )).scalar_one() or 0)
    malformed_terminal = int((await session.execute(
        select(func.count(PerformanceLedgerEntry.ledger_id)).where(
            PerformanceLedgerEntry.domain == PERFORMANCE_DOMAIN,
            PerformanceLedgerEntry.environment == env,
            PerformanceLedgerEntry.delivery_confirmed_at >= cutoff,
            PerformanceLedgerEntry.primary_bucket.in_(tuple(COMPLETED_BUCKETS)),
            PerformanceLedgerEntry.final_realized_r.is_(None),
        )
    )).scalar_one() or 0)
    projection_coverage = ledger_rows / proof_deliveries if proof_deliveries else 1.0
    min_coverage = max(0.0, min(1.0, float(os.getenv(
        "PERFORMANCE_LEDGER_MIN_PROJECTION_COVERAGE", "0.99"
    ) or 0.99)))
    ok = bool(projection_coverage >= min_coverage and malformed_terminal == 0)
    return {
        "ok": ok,
        "environment": env,
        "proof_backed_deliveries": proof_deliveries,
        "ledger_rows": ledger_rows,
        "missing_ledger_rows": max(0, proof_deliveries - ledger_rows),
        "projection_coverage": projection_coverage,
        "minimum_projection_coverage": min_coverage,
        "malformed_terminal_rows": malformed_terminal,
    }


async def get_user_performance_report(
    session,
    *,
    telegram_user_id: int,
    days: int = 30,
    report_end: datetime | None = None,
    environment: str | None = None,
) -> dict[str, Any]:
    end = report_end or now_utc_naive()
    start = end - timedelta(days=max(1, min(3650, int(days))))
    env = str(environment or runtime_environment_name("development") or "development").lower()
    await reconcile_user_performance_ledger(
        session, telegram_user_id=int(telegram_user_id), environment=env,
    )
    user = (
        await session.execute(select(User).where(User.telegram_user_id == int(telegram_user_id)).limit(1))
    ).scalar_one_or_none()
    if user is None:
        snapshot_id = _snapshot_hash({
            "user": int(telegram_user_id), "start": start, "end": end, "rows": [],
            "policy": PERFORMANCE_POLICY_VERSION,
        })[:16]
        return {
            "basis": "delivery_cohort",
            "basis_label": f"Confirmed signals delivered during the last {int(days)} days",
            "start": start,
            "end": end,
            "snapshot_generated_at": end,
            "snapshot_id": snapshot_id,
            "reconciliation_id": snapshot_id,
            "window_days": int(days),
            "risk_fraction_pct": 1.0,
            "environment": env,
            "delivered": 0,
            "total": 0,
            "buckets": {},
            "completed_r_count": 0,
            "net_r": 0.0,
            "avg_r": None,
            "median_r": None,
            "standardized_simple_return_pct": 0.0,
            "standardized_compounded_return_pct": 0.0,
            "strict_win_rate": 0.0,
            "terminal_coverage": 0.0,
            "invariant_ok": True,
            "rows": [],
        }
    rows = list((await session.execute(
        select(PerformanceLedgerEntry).where(
            PerformanceLedgerEntry.user_id == int(user.id),
            PerformanceLedgerEntry.domain == PERFORMANCE_DOMAIN,
            PerformanceLedgerEntry.environment == env,
            PerformanceLedgerEntry.delivery_confirmed_at >= start,
            PerformanceLedgerEntry.delivery_confirmed_at < end,
        ).order_by(PerformanceLedgerEntry.delivery_confirmed_at.asc())
    )).scalars().all())
    buckets: dict[str, int] = {}
    for row in rows:
        buckets[row.primary_bucket] = buckets.get(row.primary_bucket, 0) + 1
    included_r = [row.final_realized_r for row in rows if row.included and row.final_realized_r is not None]
    metrics = calculate_performance_metrics(included_r)
    delivered = len(rows)
    bucket_sum = sum(buckets.values())
    invariant_ok = bucket_sum == delivered
    tp3 = buckets.get("TP3", 0)
    losses = buckets.get("SL", 0)
    strict_denominator = tp3 + losses
    resolved = sum(buckets.get(name, 0) for name in COMPLETED_BUCKETS | NON_TRADE_BUCKETS)
    # Public claims are based on independent thesis groups, not every repriced
    # delivery. Repeated BTC/SOL signals from the same move must not inflate the
    # sample size or win rate.
    thesis_terminal: dict[str, set[str]] = {}
    for row in rows:
        if row.primary_bucket not in {"TP3", "SL"}:
            continue
        key = str(row.thesis_fingerprint or row.signal_id)
        thesis_terminal.setdefault(key, set()).add(str(row.primary_bucket))
    thesis_wins = sum(1 for values in thesis_terminal.values() if "TP3" in values and "SL" not in values)
    thesis_losses = sum(1 for values in thesis_terminal.values() if "SL" in values)
    claim = evaluate_public_win_rate_claim(
        wins=thesis_wins,
        losses=thesis_losses,
        delivered=delivered,
        resolved=resolved,
        unique_theses=len(thesis_terminal),
    )
    unresolved_or_invalid = sum(
        1 for row in rows
        if row.primary_bucket in COMPLETED_BUCKETS and row.final_realized_r is None
    )
    snapshot_id = _snapshot_hash({
        "user": user.id,
        "start": start,
        "end": end,
        "policy": PERFORMANCE_POLICY_VERSION,
        "rows": [row.snapshot_hash for row in rows],
    })[:16]
    terminal_coverage = resolved / delivered if delivered else 0.0
    min_certified_coverage = max(0.0, min(1.0, float(os.getenv(
        "PERFORMANCE_CERTIFIED_MIN_TERMINAL_COVERAGE", "0.95"
    ) or 0.95)))
    performance_certified = bool(
        invariant_ok
        and unresolved_or_invalid == 0
        and terminal_coverage >= min_certified_coverage
        and delivered > 0
    )
    return {
        "basis": "delivery_cohort",
        "basis_label": f"Confirmed signals delivered during the last {int(days)} days",
        "start": start,
        "end": end,
        "snapshot_generated_at": end,
        "snapshot_id": snapshot_id,
        "window_days": int(days),
        "risk_fraction_pct": 1.0,
        "environment": env,
        "delivered": delivered,
        "total": delivered,
        "buckets": buckets,
        "completed_r_count": metrics.completed_r_count,
        "completed_outcomes": metrics.completed_r_count,
        "resolved_trades": metrics.completed_r_count,
        "terminal_wins": tp3,
        "wins": tp3,
        "losses": losses,
        "partial_wins": buckets.get("STOPPED_AT_TP1", 0) + buckets.get("STOPPED_AT_TP2", 0),
        "breakeven": buckets.get("BREAKEVEN", 0),
        "active": buckets.get("ACTIVE", 0),
        "outcome_pending": buckets.get("PENDING_ENTRY", 0),
        "expired": buckets.get("EXPIRED", 0),
        "missed_entry": buckets.get("MISSED_ENTRY", 0),
        "cancelled": buckets.get("CANCELLED", 0),
        "tracking_failed": buckets.get("TRACKING_FAILED", 0),
        "provider_unavailable": buckets.get("PROVIDER_UNAVAILABLE", 0),
        "duplicate_deliveries_excluded": buckets.get("DUPLICATE_EXCLUDED", 0),
        "stopped_at_tp1": buckets.get("STOPPED_AT_TP1", 0),
        "stopped_at_tp2": buckets.get("STOPPED_AT_TP2", 0),
        "net_r": float(metrics.net_r),
        "avg_r": float(metrics.average_r) if metrics.average_r is not None else None,
        "median_r": float(metrics.median_r) if metrics.median_r is not None else None,
        "standardized_simple_return_pct": float(metrics.standardized_simple_return_pct),
        "average_standardized_return_pct": float(metrics.average_standardized_return_pct) if metrics.average_standardized_return_pct is not None else None,
        "standardized_compounded_return_pct": float(metrics.standardized_compounded_return_pct),
        "profit_loss_pct": float(metrics.standardized_simple_return_pct),
        "strict_win_rate": tp3 / strict_denominator if strict_denominator else 0.0,
        "win_rate": tp3 / strict_denominator if strict_denominator else 0.0,
        "profitable_result_rate": metrics.positive_r_count / metrics.completed_r_count if metrics.completed_r_count else 0.0,
        "terminal_coverage": terminal_coverage,
        "outcome_coverage": terminal_coverage,
        "performance_certified": performance_certified,
        "performance_certification_reason": (
            "certified" if performance_certified
            else "terminal_coverage_below_threshold" if terminal_coverage < min_certified_coverage
            else "ledger_invariant_or_realized_r_incomplete"
        ),
        "performance_certified_min_terminal_coverage": min_certified_coverage,
        "tracking_failure_rate": buckets.get("TRACKING_FAILED", 0) / delivered if delivered else 0.0,
        "tracked_outcomes": resolved,
        "invariant_ok": invariant_ok,
        "report_verified": bool(invariant_ok and unresolved_or_invalid == 0),
        "invalid_terminal_rows": unresolved_or_invalid,
        "independent_thesis_wins": thesis_wins,
        "independent_thesis_losses": thesis_losses,
        "independent_thesis_count": len(thesis_terminal),
        "public_claim_allowed": claim.allowed,
        "public_claim_reason": claim.reason,
        "public_claim_observed_win_rate": claim.observed_win_rate,
        "public_claim_wilson_lower_bound": claim.lower_bound,
        "public_claim_sample_size": claim.sample_size,
        "reconciliation_id": snapshot_id,
        "rows": rows,
    }


async def correct_performance_ledger_entry(
    session,
    *,
    ledger_id: str,
    actor: str,
    reason: str,
    primary_bucket: str,
    final_realized_r: Any = None,
    included: bool = True,
    exclusion_reason: str | None = None,
) -> PerformanceLedgerEntry:
    """Apply one attributed correction and append an immutable audit record."""
    actor_s = str(actor or "").strip()
    reason_s = str(reason or "").strip()
    if not actor_s or not reason_s:
        raise ValueError("performance correction requires actor and reason")
    bucket = str(primary_bucket or "").strip().upper()
    allowed = COMPLETED_BUCKETS | NON_TRADE_BUCKETS | {"PENDING_ENTRY", "ACTIVE"}
    if bucket not in allowed:
        raise ValueError(f"unsupported performance bucket: {bucket}")
    r_value = _decimal(final_realized_r)
    if final_realized_r is not None and r_value is None:
        raise ValueError("final_realized_r must be finite")
    row = (
        await session.execute(
            select(PerformanceLedgerEntry)
            .where(PerformanceLedgerEntry.ledger_id == str(ledger_id))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise LookupError("performance ledger row not found")
    before = {
        "primary_bucket": row.primary_bucket,
        "final_realized_r": row.final_realized_r,
        "included": row.included,
        "exclusion_reason": row.exclusion_reason,
        "snapshot_hash": row.snapshot_hash,
        "row_version": row.row_version,
    }
    now = now_utc_naive()
    row.primary_bucket = bucket
    row.final_realized_r = float(r_value) if r_value is not None else None
    row.included = bool(included)
    row.exclusion_reason = str(exclusion_reason)[:128] if exclusion_reason else None
    row.corrected_at = now
    row.corrected_by = actor_s[:128]
    row.correction_reason = reason_s
    row.row_version = int(row.row_version or 0) + 1
    after = {
        "primary_bucket": row.primary_bucket,
        "final_realized_r": row.final_realized_r,
        "included": row.included,
        "exclusion_reason": row.exclusion_reason,
        "row_version": row.row_version,
    }
    row.snapshot_hash = _snapshot_hash({
        "ledger_id": row.ledger_id, "correction": after, "actor": actor_s,
        "reason": reason_s, "at": now,
    })
    after["snapshot_hash"] = row.snapshot_hash
    session.add(PerformanceCorrectionAudit(
        ledger_id=row.ledger_id,
        actor=actor_s[:128],
        reason=reason_s,
        before_values=before,
        after_values=after,
        tool_version="performance-correction-v1",
        created_at=now,
    ))
    await session.flush()
    return row

async def audit_user_performance(
    session,
    *,
    telegram_user_id: int,
    days: int = 30,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit the exact canonical snapshot already shown to the user when supplied."""
    report = snapshot or await get_user_performance_report(
        session, telegram_user_id=telegram_user_id, days=days,
    )
    invalid_r = [row.signal_id for row in report.get("rows", []) if row.final_realized_r is not None and not math.isfinite(float(row.final_realized_r))]
    return {
        "snapshot_id": report.get("snapshot_id"),
        "snapshot_generated_at": report.get("snapshot_generated_at"),
        "window_days": report.get("window_days"),
        "reconciliation_id": report.get("reconciliation_id"),
        "confirmed_delivery_count": report.get("delivered", 0),
        "bucket_sum": sum(report.get("buckets", {}).values()),
        "invariant_ok": bool(report.get("invariant_ok")),
        "invalid_r_signal_ids": invalid_r,
        "invalid_final_r": invalid_r,
        "excluded": [
            {"signal_id": row.signal_id, "reason": row.exclusion_reason}
            for row in report.get("rows", []) if not row.included
        ],
    }


__all__ = [
    "COMPLETED_BUCKETS",
    "PERFORMANCE_POLICY_VERSION",
    "audit_user_performance",
    "calculate_performance_metrics",
    "correct_performance_ledger_entry",
    "get_user_performance_report",
    "reconcile_user_performance_ledger",
    "reconcile_all_performance_ledgers",
    "repair_partial_exit_outcomes",
    "performance_ledger_health",
    "PerformanceReconciliationResult",
]
