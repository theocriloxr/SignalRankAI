from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def compute_model_hash_from_b64(model_bytes_b64: str) -> str:
    raw = base64.b64decode(model_bytes_b64)
    return hashlib.sha256(raw).hexdigest()


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


def load_model_with_metadata(path: Path, xgb_module: Any) -> tuple[Any, List[str], Dict[str, Any], str | None]:
    payload = load_payload(path)
    ok, err = validate_payload(payload)
    if not ok:
        return None, [], extract_metadata(payload), err

    integrity_ok, integrity_err = verify_artifact_integrity(payload)
    if not integrity_ok:
        return None, [], extract_metadata(payload), integrity_err

    model_bytes_b64 = str(payload["model_bytes_b64"])
    raw_bytes = base64.b64decode(model_bytes_b64)
    booster = xgb_module.Booster()
    booster.load_model(bytearray(raw_bytes))
    feature_cols = [str(c) for c in payload.get("feature_cols", [])]
    return booster, feature_cols, extract_metadata(payload), None
