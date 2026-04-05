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
