from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class ModelEntry:
    name: str
    path: str
    version: str
    feature_schema_version: str
    checksum_sha256: Optional[str] = None


@dataclass
class ModelRegistry:
    primary: ModelEntry
    candidate: Optional[ModelEntry]
    strict_schema: bool


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(65536)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def load_registry(manifest_path: str | Path) -> ModelRegistry:
    p = Path(manifest_path)
    payload: Dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    primary_data = payload.get("primary") or {}
    candidate_data = payload.get("candidate") or None
    strict_schema = bool(payload.get("strict_schema", False))

    primary = ModelEntry(
        name=str(primary_data.get("name") or "primary"),
        path=str(primary_data.get("path") or "ml/model.json"),
        version=str(primary_data.get("version") or "0.0.0"),
        feature_schema_version=str(primary_data.get("feature_schema_version") or "1"),
        checksum_sha256=(str(primary_data.get("checksum_sha256")) if primary_data.get("checksum_sha256") else None),
    )
    candidate = None
    if isinstance(candidate_data, dict):
        candidate = ModelEntry(
            name=str(candidate_data.get("name") or "candidate"),
            path=str(candidate_data.get("path") or "ml/model_candidate.json"),
            version=str(candidate_data.get("version") or "0.0.0"),
            feature_schema_version=str(candidate_data.get("feature_schema_version") or "1"),
            checksum_sha256=(str(candidate_data.get("checksum_sha256")) if candidate_data.get("checksum_sha256") else None),
        )

    for entry in [primary, candidate]:
        if entry is None:
            continue
        csum = entry.checksum_sha256
        if csum:
            fp = _sha256_file(Path(entry.path))
            if fp.lower() != csum.lower():
                raise RuntimeError(
                    f"model checksum mismatch for {entry.name}: expected={csum} actual={fp}"
                )

    return ModelRegistry(primary=primary, candidate=candidate, strict_schema=strict_schema)
import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def compute_model_hash_from_b64(model_bytes_b64: str) -> str:
    raw = base64.b64decode(model_bytes_b64)
    return hashlib.sha256(raw).hexdigest()


def compute_feature_schema_hash(feature_cols: List[str]) -> str:
    """Hash the ordered inference feature contract.

    Feature order is part of the XGBoost input contract, so the hash must be
    order-sensitive and deterministic across platforms.
    """
    canonical = json.dumps(
        [str(col).strip() for col in feature_cols],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_payload(payload: Dict[str, Any]) -> tuple[bool, str | None]:
    feature_cols = payload.get("feature_cols")
    model_bytes_b64 = payload.get("model_bytes_b64")
    if not isinstance(feature_cols, list) or not feature_cols:
        return False, "feature_cols_missing"
    if not all(isinstance(col, str) and col.strip() for col in feature_cols):
        return False, "feature_cols_invalid"
    if not isinstance(model_bytes_b64, str) or not model_bytes_b64.strip():
        return False, "model_bytes_missing"
    return True, None


def load_payload(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return dict(payload or {})


def extract_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "version": str(payload.get("version") or ""),
        "trained_at": str(payload.get("trained_at") or ""),
        "xgboost_version": str(payload.get("xgboost_version") or ""),
        "artifact_hash_sha256": str(payload.get("artifact_hash_sha256") or ""),
        "feature_schema_hash_sha256": str(payload.get("feature_schema_hash_sha256") or ""),
        "dataset_version": str(payload.get("dataset_version") or ""),
        "training_run_id": str(payload.get("training_run_id") or ""),
        "parent_model_hash_sha256": str(payload.get("parent_model_hash_sha256") or ""),
        "calibration_kind": str(payload.get("calibration_kind") or "none"),
        "calibration_x": list(payload.get("calibration_x") or []),
        "calibration_y": list(payload.get("calibration_y") or []),
        "metrics": dict(payload.get("metrics") or (payload.get("training_meta") or {}).get("metrics") or {}),
        "calibration_metrics": dict(
            payload.get("calibration_metrics")
            or (payload.get("metrics") or {}).get("calibration")
            or (payload.get("training_meta") or {}).get("calibration_metrics")
            or ((payload.get("training_meta") or {}).get("metrics") or {}).get("calibration")
            or {}
        ),
        "training_meta": dict(payload.get("training_meta") or {}),
    }


def verify_artifact_integrity(payload: Dict[str, Any]) -> tuple[bool, str | None]:
    expected = str(payload.get("artifact_hash_sha256") or "").strip().lower()
    model_b64 = str(payload.get("model_bytes_b64") or "")
    if not model_b64:
        return False, "model_bytes_missing"
    actual = compute_model_hash_from_b64(model_b64)
    if not expected:
        return True, None
    if actual != expected:
        return False, "artifact_hash_mismatch"
    return True, None


def verify_feature_schema_integrity(payload: Dict[str, Any]) -> tuple[bool, str | None]:
    """Verify the ordered feature contract when a schema hash is present.

    Legacy artifacts without the field remain readable; every newly persisted
    artifact writes the hash, allowing a gradual fail-safe migration.
    """
    feature_cols = payload.get("feature_cols")
    if not isinstance(feature_cols, list) or not feature_cols:
        return False, "feature_cols_missing"
    expected = str(payload.get("feature_schema_hash_sha256") or "").strip().lower()
    if not expected:
        return True, None
    actual = compute_feature_schema_hash([str(col) for col in feature_cols])
    if actual != expected:
        return False, "feature_schema_hash_mismatch"
    return True, None


def load_model_with_metadata(path: Path, xgb_module: Any) -> tuple[Any, List[str], Dict[str, Any], str | None]:
    payload = load_payload(path)
    ok, err = validate_payload(payload)
    if not ok:
        return None, [], extract_metadata(payload), err

    integrity_ok, integrity_err = verify_artifact_integrity(payload)
    if not integrity_ok:
        return None, [], extract_metadata(payload), integrity_err

    schema_ok, schema_err = verify_feature_schema_integrity(payload)
    if not schema_ok:
        return None, [], extract_metadata(payload), schema_err

    model_bytes_b64 = str(payload["model_bytes_b64"])
    raw_bytes = base64.b64decode(model_bytes_b64)
    booster = xgb_module.Booster()
    booster.load_model(bytearray(raw_bytes))
    feature_cols = [str(c) for c in payload.get("feature_cols", [])]
    return booster, feature_cols, extract_metadata(payload), None


def save_model_payload(path: Path, booster: Any, feature_cols: List[str], metadata: Dict[str, Any]) -> bool:
    """Persist a model booster and feature schema into a JSON payload compatible with load_model_with_metadata.

    Returns True on success.
    """
    import base64
    try:
        # booster.save_raw() returns bytes for xgboost Booster
        raw = booster.save_raw() if hasattr(booster, 'save_raw') else booster.save_model()
        if raw is None:
            # fallback: try saving to temporary buffer
            from io import BytesIO
            buf = BytesIO()
            booster.save_model(buf)
            raw = buf.getvalue()
        model_b64 = base64.b64encode(raw).decode('ascii')
        ordered_features = [str(col).strip() for col in (feature_cols or [])]
        artifact_hash = hashlib.sha256(raw).hexdigest()
        feature_schema_hash = compute_feature_schema_hash(ordered_features)
        payload = {
            'feature_cols': ordered_features,
            'model_bytes_b64': model_b64,
            'version': str(metadata.get('version') or ''),
            'trained_at': str(metadata.get('trained_at') or ''),
            'xgboost_version': str(metadata.get('xgboost_version') or ''),
            # Never trust a caller-supplied checksum for newly persisted bytes.
            'artifact_hash_sha256': artifact_hash,
            'feature_schema_hash_sha256': feature_schema_hash,
            'dataset_version': str(metadata.get('dataset_version') or ''),
            'training_run_id': str(metadata.get('training_run_id') or ''),
            'parent_model_hash_sha256': str(metadata.get('parent_model_hash_sha256') or ''),
            'calibration_kind': str(metadata.get('calibration_kind') or 'none'),
            'calibration_x': list(metadata.get('calibration_x') or []),
            'calibration_y': list(metadata.get('calibration_y') or []),
            'metrics': dict(metadata.get('metrics') or {}),
            'calibration_metrics': dict(metadata.get('calibration_metrics') or {}),
            'training_meta': dict(metadata.get('training_meta') or {}),
        }
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False)
        return True
    except Exception:
        return False
