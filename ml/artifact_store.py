from __future__ import annotations

import asyncio

import hashlib
import json
import logging
import math
import os
import re
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def _artifact_db_priority() -> str:
    explicit = str(os.getenv("ML_TRAINING_DB_PRIORITY") or "").strip().lower()
    role = str(os.getenv("DB_ROLE") or os.getenv("RUN_MODE") or os.getenv("SERVICE_ROLE") or "").strip().lower()
    # Model persistence is part of the analytics-owned training transaction.
    # A dedicated analytics service must not fall back to the generic
    # background lane, whose foreground reservation can reject this durable
    # write after a successful fit.
    if role == "analytics" or role.startswith("analytics-"):
        if explicit in {"interactive", "critical", "analytics"}:
            return explicit
        return "analytics"
    if explicit in {"interactive", "critical", "background", "analytics"}:
        return explicit
    return "background"


def _artifact_query_timeout() -> float:
    try:
        value = float(os.getenv("ML_ARTIFACT_DB_TIMEOUT_SECONDS", "20") or 20)
        return min(120.0, max(5.0, value)) if math.isfinite(value) else 20.0
    except Exception:
        return 20.0


def _payload_hash(payload: dict[str, Any]) -> str:
    expected = str(payload.get("artifact_hash_sha256") or "").strip().lower()
    if expected:
        return expected
    import base64

    raw = base64.b64decode(str(payload.get("model_bytes_b64") or ""))
    return hashlib.sha256(raw).hexdigest()


def artifact_review_hash(row: Any) -> str:
    """Bind qualification metadata and registry clocks, separately from model bytes.

    The model bytes have their own verified artifact digest. No raw model or
    metadata is returned/logged by this identity function.
    """
    if row is None:
        return ""
    metadata = dict(getattr(row, "payload", {}) or {})
    metadata.pop("model_bytes_b64", None)
    review = {key: getattr(row, key, None) for key in (
        "id", "model_name", "model_version", "feature_schema_version",
        "artifact_hash_sha256", "metrics", "source_counts", "is_active",
    )}
    review["payload_metadata"] = metadata
    for key in ("trained_at", "created_at"):
        instant = getattr(row, key, None)
        review[key] = instant.isoformat() if isinstance(instant, datetime) else instant
    encoded = json.dumps(review, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


async def persist_active_model_artifact(
    model_path: str | Path,
    *,
    training_meta: dict[str, Any] | None = None,
    model_name: str = "primary",
) -> bool:
    """Persist the promoted model payload in Postgres for restart recovery."""
    path = Path(model_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    from ml.model_registry import validate_payload, verify_artifact_integrity

    valid, error = validate_payload(payload)
    if not valid:
        logger.error("[ml_artifact] invalid payload error=%s", error)
        return False
    integrity_ok, integrity_error = verify_artifact_integrity(payload)
    if not integrity_ok:
        logger.error("[ml_artifact] integrity failure error=%s", integrity_error)
        return False

    from sqlalchemy import update
    from db.models import MLModelArtifact
    from db.session import get_session
    from utils.timeutils import now_utc_naive

    meta = dict(training_meta or {})
    normalized_model_name = str(model_name or "primary").strip().lower() or "primary"
    try:
        async with get_session(
            priority=_artifact_db_priority(),
            label="ml_model_artifact_persist",
            timeout_seconds=float(os.getenv("ML_TRAINING_DB_TIMEOUT_SECONDS", "30") or 30),
            drop_if_busy=False,
        ) as session:
            await asyncio.wait_for(
                session.execute(
                    update(MLModelArtifact)
                    .where(
                        MLModelArtifact.model_name == normalized_model_name,
                        MLModelArtifact.is_active.is_(True),
                    )
                    .values(is_active=False)
                ),
                timeout=_artifact_query_timeout(),
            )
            session.add(
                MLModelArtifact(
                    model_name=normalized_model_name,
                    model_version=str(payload.get("version") or "unknown"),
                    feature_schema_version=str(
                        payload.get("feature_schema_version") or meta.get("feature_schema_version") or "1"
                    ),
                    artifact_hash_sha256=_payload_hash(payload),
                    payload=payload,
                    metrics=dict(meta.get("metrics") or {}),
                    source_counts=dict(meta.get("source_counts") or {}),
                    is_active=True,
                    trained_at=now_utc_naive(),
                )
            )
            await asyncio.wait_for(session.commit(), timeout=_artifact_query_timeout())
        # A candidate artifact is NOT the active champion: make the role
        # explicit so logs can never imply promotion happened.
        role = (
            "champion"
            if str(normalized_model_name).lower() in {"champion", "active", "primary", "production"}
            else "candidate"
        )
        logger.info(
            "[ml_artifact] persisted model artifact name=%s version=%s hash=%s role=%s champion_unchanged=%s",
            normalized_model_name,
            payload.get("version"),
            _payload_hash(payload),
            role,
            str(role != "champion").lower(),
        )
        return True
    except Exception as exc:
        logger.exception("[ml_artifact] persistence failed: %s", exc)
        return False


async def promote_active_candidate_artifact(
    *,
    expected_artifact_hash_sha256: str,
    expected_candidate_id: int | None,
    expected_primary_hash_sha256: str,
    expected_primary_id: int | None,
    expected_candidate_review_hash: str | None,
    expected_primary_review_hash: str | None,
) -> dict[str, Any]:
    """Commit only against the candidate and primary snapshots actually reviewed.

    The caller owns forward qualification and authorization. Row identities also
    bind metadata: a replacement with identical model bytes cannot borrow the
    previous row's review. Both comparisons occur while the active rows are locked.
    """
    from sqlalchemy import desc, select, update
    from db.models import MLModelArtifact
    from db.session import get_session
    from ml.model_registry import (
        validate_payload,
        verify_artifact_integrity,
        verify_feature_schema_integrity,
    )
    from utils.timeutils import now_utc_naive

    expected = str(expected_artifact_hash_sha256 or "").strip().lower()
    if not expected:
        return {"ok": False, "reason": "expected_candidate_hash_missing"}
    expected_primary = str(expected_primary_hash_sha256 or "").strip().lower()
    if (not re.fullmatch(r"[0-9a-f]{64}", expected)
            or type(expected_candidate_id) is not int or expected_candidate_id <= 0
            or (expected_primary and not re.fullmatch(r"[0-9a-f]{64}", expected_primary))
            or (expected_primary and (type(expected_primary_id) is not int or expected_primary_id <= 0))
            or (not expected_primary and expected_primary_id is not None)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_candidate_review_hash or "")
            or (expected_primary and not re.fullmatch(r"[0-9a-f]{64}", expected_primary_review_hash or ""))
            or (not expected_primary and expected_primary_review_hash != "")):
        return {"ok": False, "reason": "promotion_snapshot_invalid"}

    try:
        async with get_session(
            priority=_artifact_db_priority(),
            label="ml_candidate_promote",
            timeout_seconds=float(os.getenv("ML_TRAINING_DB_TIMEOUT_SECONDS", "30") or 30),
            drop_if_busy=False,
        ) as session:
            candidate = (
                (
                    await asyncio.wait_for(
                        session.execute(
                            select(MLModelArtifact)
                            .where(
                                MLModelArtifact.model_name == "candidate",
                                MLModelArtifact.is_active.is_(True),
                            )
                            .order_by(
                                desc(MLModelArtifact.created_at),
                                desc(MLModelArtifact.id),
                            )
                            .limit(1)
                            .with_for_update()
                        ),
                        timeout=_artifact_query_timeout(),
                    )
                )
                .scalars()
                .first()
            )
            if candidate is None:
                await session.rollback()
                return {"ok": False, "reason": "active_candidate_missing"}

            candidate_hash = str(getattr(candidate, "artifact_hash_sha256", "") or "").strip().lower()
            if candidate_hash != expected:
                await session.rollback()
                return {
                    "ok": False,
                    "reason": "candidate_hash_changed",
                    "expected": expected,
                    "actual": candidate_hash,
                }
            if candidate.id != expected_candidate_id or artifact_review_hash(candidate) != expected_candidate_review_hash:
                await session.rollback()
                return {"ok": False, "reason": "candidate_snapshot_changed"}

            payload = dict(getattr(candidate, "payload", {}) or {})
            valid, validation_error = validate_payload(payload)
            integrity_ok, integrity_error = verify_artifact_integrity(payload)
            schema_ok, schema_error = verify_feature_schema_integrity(payload)
            payload_identity_ok = _payload_hash(payload) == candidate_hash
            if not (valid and integrity_ok and schema_ok and payload_identity_ok):
                await session.rollback()
                return {
                    "ok": False,
                    "reason": "candidate_integrity_failed",
                    "validation_error": validation_error,
                    "integrity_error": integrity_error,
                    "schema_error": schema_error,
                    "payload_identity_matches_registry": payload_identity_ok,
                }

            current_primary = (
                (
                    await asyncio.wait_for(
                        session.execute(
                            select(MLModelArtifact)
                            .where(
                                MLModelArtifact.model_name == "primary",
                                MLModelArtifact.is_active.is_(True),
                            )
                            .order_by(
                                desc(MLModelArtifact.created_at),
                                desc(MLModelArtifact.id),
                            )
                            .limit(1)
                            .with_for_update()
                        ),
                        timeout=_artifact_query_timeout(),
                    )
                )
                .scalars()
                .first()
            )
            previous_hash = str(getattr(current_primary, "artifact_hash_sha256", "") or "").strip().lower()
            primary_id = current_primary.id if current_primary is not None else None
            if (previous_hash != expected_primary or primary_id != expected_primary_id
                    or artifact_review_hash(current_primary) != expected_primary_review_hash):
                await session.rollback()
                return {"ok": False, "reason": "primary_snapshot_changed"}

            if previous_hash == candidate_hash:
                await session.rollback()
                return {
                    "ok": True,
                    "reason": "candidate_already_primary",
                    "artifact_hash_sha256": candidate_hash,
                    "previous_primary_hash_sha256": previous_hash,
                }

            metadata = payload.get("training_meta") or {}
            parent_hash = str(payload.get("parent_model_hash_sha256")
                              or metadata.get("parent_model_hash_sha256") or "").strip().lower()
            if parent_hash != previous_hash:
                await session.rollback()
                return {"ok": False, "reason": "candidate_parent_champion_changed"}

            await asyncio.wait_for(
                session.execute(
                    update(MLModelArtifact)
                    .where(
                        MLModelArtifact.model_name == "primary",
                        MLModelArtifact.is_active.is_(True),
                    )
                    .values(is_active=False)
                ),
                timeout=_artifact_query_timeout(),
            )
            session.add(
                MLModelArtifact(
                    model_name="primary",
                    model_version=str(getattr(candidate, "model_version", "") or "unknown"),
                    feature_schema_version=str(getattr(candidate, "feature_schema_version", "") or "1"),
                    artifact_hash_sha256=candidate_hash,
                    payload=payload,
                    metrics=dict(getattr(candidate, "metrics", {}) or {}),
                    source_counts=dict(getattr(candidate, "source_counts", {}) or {}),
                    is_active=True,
                    trained_at=(getattr(candidate, "trained_at", None) or now_utc_naive()),
                )
            )
            await asyncio.wait_for(
                session.commit(),
                timeout=_artifact_query_timeout(),
            )

        logger.warning(
            "[ml_artifact] candidate promoted hash=%s previous_primary=%s",
            candidate_hash[:12],
            previous_hash[:12] if previous_hash else "none",
        )
        return {
            "ok": True,
            "reason": "candidate_promoted",
            "artifact_hash_sha256": candidate_hash,
            "previous_primary_hash_sha256": previous_hash,
        }
    except Exception as exc:
        logger.exception(
            "[ml_artifact] candidate promotion failed error=%s",
            type(exc).__name__,
        )
        return {
            "ok": False,
            "reason": "candidate_promotion_exception",
            "error": type(exc).__name__,
        }


def restore_active_model_artifact_sync(
    connection: Any,
    target_path: str | Path,
    *,
    model_name: str = "primary",
) -> bool:
    """Restore the latest active model using an existing psycopg connection."""
    target = Path(target_path)
    normalized_model_name = str(model_name or "primary").strip().lower() or "primary"
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT payload
                FROM ml_model_artifacts
                WHERE model_name = %s AND is_active = TRUE
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (normalized_model_name,),
            )
            row = cursor.fetchone()
        if not row:
            return False
        payload = row[0]
        if isinstance(payload, str):
            payload = json.loads(payload)
        payload = dict(payload or {})
        from ml.model_registry import validate_payload, verify_artifact_integrity

        valid, error = validate_payload(payload)
        integrity_ok, integrity_error = verify_artifact_integrity(payload)
        if not valid or not integrity_ok:
            logger.error(
                "[ml_artifact] restore rejected validation=%s integrity=%s",
                error,
                integrity_error,
            )
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix="model.restore.", suffix=".json.tmp", dir=str(target.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        logger.info(
            "[ml_artifact] restored active model name=%s version=%s trained_at=%s",
            normalized_model_name,
            payload.get("version"),
            payload.get("trained_at"),
        )
        return True
    except Exception as exc:
        # Missing table is expected before migration 0033 or on a fresh local DB.
        logger.warning("[ml_artifact] restore skipped: %s", exc)
        return False


def restore_active_model_artifact_from_database_sync(
    target_path: str | Path,
    *,
    model_name: str = "primary",
    connect_timeout_seconds: int = 5,
) -> bool:
    """Restore an active artifact without relying on monolith startup ops.

    Dedicated Railway roles skip db.auto_ops, so serving roles need a small,
    bounded recovery path of their own to consume analytics-owned promotions.
    """
    try:
        from config import resolve_database_url
        import psycopg2

        dsn = resolve_database_url(async_driver=False) or ""
        if not dsn:
            return False
        connection = psycopg2.connect(
            dsn,
            connect_timeout=max(1, min(10, int(connect_timeout_seconds or 5))),
        )
        connection.autocommit = True
        try:
            return restore_active_model_artifact_sync(
                connection,
                target_path,
                model_name=model_name,
            )
        finally:
            connection.close()
    except Exception as exc:
        logger.warning(
            "[ml_artifact] direct restore skipped name=%s error=%s",
            model_name,
            type(exc).__name__,
        )
        return False
