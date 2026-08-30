from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _payload_hash(payload: dict[str, Any]) -> str:
    expected = str(payload.get("artifact_hash_sha256") or "").strip().lower()
    if expected:
        return expected
    import base64

    raw = base64.b64decode(str(payload.get("model_bytes_b64") or ""))
    return hashlib.sha256(raw).hexdigest()


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
            priority=str(os.getenv("ML_TRAINING_DB_PRIORITY") or "background"),
            label="ml_model_artifact_persist",
            timeout_seconds=float(os.getenv("ML_TRAINING_DB_TIMEOUT_SECONDS", "30") or 30),
            drop_if_busy=False,
        ) as session:
            await session.execute(
                update(MLModelArtifact)
                .where(
                    MLModelArtifact.model_name == normalized_model_name,
                    MLModelArtifact.is_active.is_(True),
                )
                .values(is_active=False)
            )
            session.add(
                MLModelArtifact(
                    model_name=normalized_model_name,
                    model_version=str(payload.get("version") or "unknown"),
                    feature_schema_version=str(
                        payload.get("feature_schema_version")
                        or meta.get("feature_schema_version")
                        or "1"
                    ),
                    artifact_hash_sha256=_payload_hash(payload),
                    payload=payload,
                    metrics=dict(meta.get("metrics") or {}),
                    source_counts=dict(meta.get("source_counts") or {}),
                    is_active=True,
                    trained_at=now_utc_naive(),
                )
            )
            await session.commit()
        # A candidate artifact is NOT the active champion: make the role
        # explicit so logs can never imply promotion happened.
        role = (
            "champion"
            if str(normalized_model_name).lower() in {"champion", "active", "primary", "production"}
            else "candidate"
        )
        logger.info(
            "[ml_artifact] persisted model artifact name=%s version=%s hash=%s role=%s "
            "champion_unchanged=%s",
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
                """
                ,
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
        fd, temp_name = tempfile.mkstemp(
            prefix="model.restore.", suffix=".json.tmp", dir=str(target.parent)
        )
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
