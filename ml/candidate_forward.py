"""Forward-proof governance for ML challenger models.

This module never changes serving decisions while collecting evidence. It reads
outcome-tracked candidate_shadow observations and decides whether the active
candidate has enough live-forward evidence to be considered for promotion.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from utils.timeutils import now_utc_naive


def _candidate_db_priority():
    from db.priority import DBPriority

    role = str(
        os.getenv("DB_ROLE")
        or os.getenv("RUN_MODE")
        or os.getenv("SERVICE_ROLE")
        or ""
    ).strip().lower()
    return (
        DBPriority.ANALYTICS
        if role == "analytics" or role.startswith("analytics-")
        else DBPriority.BACKGROUND
    )


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "y"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, str(default)) or default))
    except (TypeError, ValueError):
        return int(default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        return float(default)


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _outcome_class(value: Any) -> str | None:
    raw = str(value or "").strip().lower()
    if raw in {"win", "tp", "tp1", "tp2", "tp3", "partial_tp"} or raw.startswith("tp"):
        return "win"
    if raw in {"loss", "sl", "stop", "stop_loss"}:
        return "loss"
    return None


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "pass", "passed"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
        return numeric if math.isfinite(numeric) else float(default)
    except Exception:
        return float(default)


def _row_r_multiple(row: Any, outcome: str) -> float:
    entry = _safe_float(getattr(row, "entry", 0.0))
    stop = _safe_float(getattr(row, "stop_loss", 0.0))
    raw_tp = getattr(row, "take_profit", None)
    try:
        target = float(raw_tp)
    except Exception:
        target = 0.0
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk <= 0.0 or reward <= 0.0:
        return 0.0
    return reward / risk if outcome == "win" else -1.0


def _decision_stats(rows: list[tuple[Any, dict[str, Any], str]], key: str) -> dict[str, Any]:
    selected = [
        (row, features, outcome)
        for row, features, outcome in rows
        if _boolish(features.get(key))
    ]
    r_values = [_row_r_multiple(row, outcome) for row, _, outcome in selected]
    usable = [value for value in r_values if value != 0.0]
    wins = sum(1 for _, _, outcome in selected if outcome == "win")
    losses = sum(1 for _, _, outcome in selected if outcome == "loss")
    resolved = wins + losses
    gross_profit = sum(value for value in usable if value > 0.0)
    gross_loss = abs(sum(value for value in usable if value < 0.0))
    expectancy = (sum(usable) / len(usable)) if usable else 0.0
    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0.0
        else (999.0 if gross_profit > 0.0 else 0.0)
    )
    return {
        "resolved": resolved,
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / resolved) if resolved else 0.0,
        "expected_r": expectancy,
        "profit_factor": profit_factor,
    }


async def load_active_candidate() -> dict[str, Any] | None:
    from db.models import MLModelArtifact
    from db.priority import DBPriority
    from db.session import get_session
    from sqlalchemy import desc, select

    async with get_session(
        priority=_candidate_db_priority(),
        label="ml_candidate_forward_active_artifact",
        timeout_seconds=_env_float("ML_TRAINING_DB_TIMEOUT_SECONDS", 30.0),
        drop_if_busy=False,
    ) as session:
        row = (
            await session.execute(
                select(MLModelArtifact)
                .where(
                    MLModelArtifact.model_name == "candidate",
                    MLModelArtifact.is_active.is_(True),
                )
                .order_by(desc(MLModelArtifact.created_at), desc(MLModelArtifact.id))
                .limit(1)
            )
        ).scalars().first()
        await session.rollback()
    if row is None:
        return None
    payload = dict(getattr(row, "payload", {}) or {})
    return {
        "id": int(getattr(row, "id", 0) or 0),
        "artifact_hash_sha256": str(getattr(row, "artifact_hash_sha256", "") or ""),
        "model_version": str(getattr(row, "model_version", "") or ""),
        "feature_schema_version": str(getattr(row, "feature_schema_version", "") or ""),
        "schema_version": int(payload.get("schema_version") or 1),
        "feature_schema_hash_sha256": str(payload.get("feature_schema_hash_sha256") or ""),
        "training_run_id": str(payload.get("training_run_id") or ""),
        "trained_at": getattr(row, "trained_at", None) or _parse_dt(payload.get("trained_at")),
        "created_at": getattr(row, "created_at", None),
        "metrics": dict(getattr(row, "metrics", {}) or payload.get("metrics") or {}),
        "payload": payload,
    }


async def load_active_primary() -> dict[str, Any] | None:
    from db.models import MLModelArtifact
    from db.priority import DBPriority
    from db.session import get_session
    from sqlalchemy import desc, select

    async with get_session(
        priority=_candidate_db_priority(),
        label="ml_candidate_forward_active_primary",
        timeout_seconds=_env_float("ML_TRAINING_DB_TIMEOUT_SECONDS", 30.0),
        drop_if_busy=False,
    ) as session:
        row = (
            await session.execute(
                select(MLModelArtifact)
                .where(
                    MLModelArtifact.model_name == "primary",
                    MLModelArtifact.is_active.is_(True),
                )
                .order_by(desc(MLModelArtifact.created_at), desc(MLModelArtifact.id))
                .limit(1)
            )
        ).scalars().first()
        await session.rollback()
    if row is None:
        return None
    payload = dict(getattr(row, "payload", {}) or {})
    return {
        "id": int(getattr(row, "id", 0) or 0),
        "artifact_hash_sha256": str(
            getattr(row, "artifact_hash_sha256", "") or ""
        ),
        "model_version": str(getattr(row, "model_version", "") or ""),
        "feature_schema_version": str(
            getattr(row, "feature_schema_version", "") or ""
        ),
        "schema_version": int(payload.get("schema_version") or 1),
        "trained_at": getattr(row, "trained_at", None),
        "metrics": dict(getattr(row, "metrics", {}) or payload.get("metrics") or {}),
    }


async def evaluate_candidate_forward_evidence(
    candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from db.models import MLRejectedSignal
    from db.priority import DBPriority
    from db.session import get_session
    from sqlalchemy import select

    candidate = dict(candidate or (await load_active_candidate()) or {})
    artifact_hash = str(candidate.get("artifact_hash_sha256") or "").strip().lower()
    if not artifact_hash:
        return {
            "eligible": False,
            "status": "no_candidate",
            "reasons": ["active_candidate_missing"],
            "candidate": candidate,
        }

    trained_at = _parse_dt(candidate.get("trained_at")) or now_utc_naive()
    max_age_hours = max(1.0, _env_float("ML_CANDIDATE_FORWARD_MAX_AGE_HOURS", 48.0))
    cutoff = trained_at - timedelta(minutes=1)
    max_rows = max(100, min(20000, _env_int("ML_CANDIDATE_FORWARD_MAX_ROWS", 5000)))

    async with get_session(
        priority=_candidate_db_priority(),
        label="ml_candidate_forward_evidence",
        timeout_seconds=_env_float("ML_TRAINING_DB_TIMEOUT_SECONDS", 30.0),
        drop_if_busy=False,
    ) as session:
        rows = list(
            (
                await session.execute(
                    select(MLRejectedSignal)
                    .where(
                        MLRejectedSignal.created_at >= cutoff,
                        MLRejectedSignal.outcome_tracked_at.is_not(None),
                    )
                    .order_by(MLRejectedSignal.created_at.asc())
                    .limit(max_rows)
                )
            ).scalars().all()
        )
        await session.rollback()

    unique: dict[str, Any] = {}
    for row in rows:
        features = dict(getattr(row, "features", {}) or {})
        if str(features.get("rejection_type") or "").strip().lower() != "candidate_shadow":
            continue
        if str(features.get("candidate_artifact_hash_sha256") or "").strip().lower() != artifact_hash:
            continue
        key = str(features.get("candidate_observation_key") or "").strip()
        if not key:
            key = f"row:{getattr(row, 'id', 0)}"
        unique.setdefault(key, row)

    all_rows = list(unique.values())
    resolved_rows: list[tuple[Any, dict[str, Any], str]] = []
    asset_classes: set[str] = set()
    for row in all_rows:
        features = dict(getattr(row, "features", {}) or {})
        outcome = _outcome_class(getattr(row, "actual_outcome", None))
        asset_class = str(features.get("asset_class_enc") or "").strip()
        if asset_class:
            asset_classes.add(asset_class)
        if outcome is not None:
            resolved_rows.append((row, features, outcome))

    candidate_stats = _decision_stats(resolved_rows, "candidate_passed")
    champion_stats = _decision_stats(resolved_rows, "champion_passed")
    candidate_passed_all = sum(
        1
        for row in all_rows
        if _boolish((getattr(row, "features", {}) or {}).get("candidate_passed"))
    )
    champion_passed_all = sum(
        1
        for row in all_rows
        if _boolish((getattr(row, "features", {}) or {}).get("champion_passed"))
    )
    candidate_pass_rate = candidate_passed_all / len(all_rows) if all_rows else 0.0
    champion_pass_rate = champion_passed_all / len(all_rows) if all_rows else 0.0

    observation_times = [
        getattr(row, "created_at", None)
        for row in all_rows
        if isinstance(getattr(row, "created_at", None), datetime)
    ]
    if observation_times:
        first_at = min(observation_times)
        last_at = max(observation_times)
        forward_span_hours = max(
            0.0,
            (last_at - first_at).total_seconds() / 3600.0,
        )
    else:
        first_at = None
        last_at = None
        forward_span_hours = 0.0

    min_observations = max(10, _env_int("ML_CANDIDATE_FORWARD_MIN_OBSERVATIONS", 100))
    min_resolved = max(10, _env_int("ML_CANDIDATE_FORWARD_MIN_RESOLVED", 50))
    min_passed_resolved = max(5, _env_int("ML_CANDIDATE_FORWARD_MIN_PASSED_RESOLVED", 20))
    min_span_hours = max(0.0, _env_float("ML_CANDIDATE_FORWARD_MIN_SPAN_HOURS", 2.0))
    min_asset_classes = max(1, _env_int("ML_CANDIDATE_FORWARD_MIN_ASSET_CLASSES", 3))
    min_pass_rate = max(0.0, _env_float("ML_CANDIDATE_FORWARD_MIN_PASS_RATE", 0.01))
    max_pass_rate = min(1.0, _env_float("ML_CANDIDATE_FORWARD_MAX_PASS_RATE", 0.50))
    min_expected_r = _env_float("ML_CANDIDATE_FORWARD_MIN_EXPECTED_R", 0.05)
    min_profit_factor = max(0.0, _env_float("ML_CANDIDATE_FORWARD_MIN_PROFIT_FACTOR", 1.10))
    champion_min_compare = max(5, _env_int("ML_CANDIDATE_FORWARD_CHAMPION_COMPARE_MIN", 20))
    max_expected_r_regression = max(
        0.0,
        _env_float("ML_CANDIDATE_FORWARD_MAX_EXPECTED_R_REGRESSION", 0.10),
    )

    reasons: list[str] = []
    if len(all_rows) < min_observations:
        reasons.append("insufficient_observations")
    if len(resolved_rows) < min_resolved:
        reasons.append("insufficient_resolved_outcomes")
    if candidate_stats["resolved"] < min_passed_resolved:
        reasons.append("insufficient_candidate_passed_outcomes")
    if forward_span_hours < min_span_hours:
        reasons.append("insufficient_forward_span")
    if len(asset_classes) < min_asset_classes:
        reasons.append("insufficient_asset_class_coverage")
    if candidate_pass_rate < min_pass_rate:
        reasons.append("candidate_pass_rate_too_low")
    if candidate_pass_rate > max_pass_rate:
        reasons.append("candidate_pass_rate_too_high")
    if candidate_stats["resolved"] >= min_passed_resolved:
        if float(candidate_stats["expected_r"]) < min_expected_r:
            reasons.append("candidate_expected_r_below_floor")
        if float(candidate_stats["profit_factor"]) < min_profit_factor:
            reasons.append("candidate_profit_factor_below_floor")
    if champion_stats["resolved"] >= champion_min_compare:
        if float(candidate_stats["expected_r"]) < (
            float(champion_stats["expected_r"]) - max_expected_r_regression
        ):
            reasons.append("candidate_expected_r_materially_below_champion")

    age_hours = max(
        0.0,
        (now_utc_naive() - trained_at).total_seconds() / 3600.0,
    )
    eligible = not reasons
    status = "eligible" if eligible else "collecting"
    if (
        not eligible
        and age_hours >= max_age_hours
        and (
            len(all_rows) < min_observations
            or len(resolved_rows) < min_resolved
            or candidate_stats["resolved"] < min_passed_resolved
        )
    ):
        status = "expired"
    elif (
        not eligible
        and len(all_rows) >= min_observations
        and len(resolved_rows) >= min_resolved
        and candidate_stats["resolved"] >= min_passed_resolved
    ):
        status = "failed"

    return {
        "eligible": eligible,
        "status": status,
        "reasons": reasons,
        "observations": len(all_rows),
        "resolved": len(resolved_rows),
        "candidate_pass_rate": candidate_pass_rate,
        "champion_pass_rate": champion_pass_rate,
        "candidate": {
            **{
                key: value
                for key, value in candidate.items()
                if key != "payload"
            },
            "decision_stats": candidate_stats,
        },
        "champion": {
            "decision_stats": champion_stats,
        },
        "asset_class_count": len(asset_classes),
        "asset_classes": sorted(asset_classes),
        "forward_span_hours": forward_span_hours,
        "candidate_age_hours": age_hours,
        "first_observation_at": first_at.isoformat() if first_at else None,
        "last_observation_at": last_at.isoformat() if last_at else None,
        "requirements": {
            "min_observations": min_observations,
            "min_resolved": min_resolved,
            "min_passed_resolved": min_passed_resolved,
            "min_span_hours": min_span_hours,
            "min_asset_classes": min_asset_classes,
            "min_pass_rate": min_pass_rate,
            "max_pass_rate": max_pass_rate,
            "min_expected_r": min_expected_r,
            "min_profit_factor": min_profit_factor,
            "champion_compare_min": champion_min_compare,
            "max_expected_r_regression": max_expected_r_regression,
            "max_age_hours": max_age_hours,
        },
    }

async def promote_candidate_from_forward_proof(
    *,
    authorization_id: str | None = None,
) -> dict[str, Any]:
    """Promote only an eligible forward-tested candidate.

    Automatic promotion is disabled by default. A caller can provide an
    explicit authorization ID (for example from an owner approval workflow).
    Feature-schema changes additionally retain the dedicated schema migration
    authorization and certification gate.
    """
    candidate = await load_active_candidate()
    if not candidate:
        return {"ok": False, "reason": "active_candidate_missing"}

    primary = await load_active_primary()
    candidate_hash = str(candidate.get("artifact_hash_sha256") or "").strip()
    primary_hash = str((primary or {}).get("artifact_hash_sha256") or "").strip()
    if candidate_hash and candidate_hash == primary_hash:
        return {
            "ok": True,
            "reason": "candidate_already_primary",
            "artifact_hash_sha256": candidate_hash,
        }

    evidence = await evaluate_candidate_forward_evidence(candidate)
    if not bool(evidence.get("eligible")):
        return {
            "ok": False,
            "reason": "forward_proof_not_eligible",
            "evidence": evidence,
        }

    explicit_authorization = str(authorization_id or "").strip()
    auto_enabled = _env_bool(
        "ML_CANDIDATE_FORWARD_AUTO_PROMOTION_ENABLED",
        False,
    )
    if not auto_enabled and not explicit_authorization:
        return {
            "ok": False,
            "reason": "promotion_authorization_required",
            "evidence": evidence,
        }

    candidate_schema = int(candidate.get("schema_version") or 1)
    primary_schema = int((primary or {}).get("schema_version") or 1)
    if primary and candidate_schema != primary_schema:
        schema_allowed = _env_bool(
            "ML_ALLOW_SCHEMA_VERSION_PROMOTION",
            False,
        )
        schema_certification = str(
            os.getenv("ML_SCHEMA_PROMOTION_CERTIFICATION_ID") or ""
        ).strip()
        if not (schema_allowed and schema_certification):
            return {
                "ok": False,
                "reason": "schema_migration_requires_authorization",
                "candidate_schema_version": candidate_schema,
                "primary_schema_version": primary_schema,
                "schema_authorized": schema_allowed,
                "schema_certification_present": bool(schema_certification),
                "evidence": evidence,
            }

    from ml.artifact_store import (
        promote_active_candidate_artifact,
        restore_active_model_artifact_from_database_sync,
    )

    promoted = await promote_active_candidate_artifact(
        expected_artifact_hash_sha256=candidate_hash,
    )
    if not promoted.get("ok"):
        return {
            "ok": False,
            "reason": "durable_promotion_failed",
            "promotion": promoted,
            "evidence": evidence,
        }

    # Refresh the local primary artifact in the promoting role. Other serving
    # roles consume the durable primary through their bounded hot-sync path.
    try:
        from pathlib import Path
        import asyncio
        from engine import ml as engine_ml

        primary_path = Path(
            os.getenv("ML_MODEL_PATH")
            or (Path(__file__).parent / "model.json")
        )
        restored = await asyncio.to_thread(
            restore_active_model_artifact_from_database_sync,
            primary_path,
            model_name="primary",
            connect_timeout_seconds=int(
                os.getenv(
                    "ML_DURABLE_ARTIFACT_DB_CONNECT_TIMEOUT_SECONDS",
                    "5",
                )
                or 5
            ),
        )
        reload_status = (
            await asyncio.to_thread(
                engine_ml.reload_model,
                sync_durable=False,
            )
            if restored
            else {"loaded": False, "error": "primary_restore_failed"}
        )
    except Exception as exc:
        reload_status = {
            "loaded": False,
            "error": type(exc).__name__,
        }

    return {
        "ok": True,
        "reason": "candidate_promoted",
        "authorization_id": (
            explicit_authorization or "automatic_forward_proof"
        ),
        "promotion": promoted,
        "reload": reload_status,
        "evidence": evidence,
    }

