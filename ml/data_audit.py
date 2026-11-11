"""Training-data audit recorded with every run (owner request, 11 Nov 2026).

Each check targets a known way a trading model looks good offline and fails live:

* **leakage** - a single feature that separates wins from losses almost perfectly
  (single-feature AUC >= ``ML_LEAK_SUSPECT_AUC``, 0.90) is far more likely a
  future value or the label itself than a real edge; such a run is not promoted;
* **label noise** - identical feature rows with opposite outcomes; above
  ``ML_MAX_LABEL_CONFLICT_SHARE`` (0.50 of duplicated rows: a coin flip) labels are
  not usable and the run is not promoted;
* **collinearity / dead features** - near-duplicate (|r| >= 0.98) and constant
  columns, reported so feature changes can drop them;
* **class balance and size** - positive rate and rows per feature (curse of
  dimensionality);
* **reproducibility** - dataset hash and code commit, so a model can be traced to
  exactly what produced it.

The audit only reads the frame; it never changes rows, labels or features.
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


def audit(X: Any, y: Any, feature_cols: list[str]) -> dict[str, Any]:
    import numpy as np
    import pandas as pd

    out: dict[str, Any] = {}
    try:
        frame = pd.DataFrame(X)[list(feature_cols)].astype(float)
        labels = np.asarray(y, dtype=int)
        n, k = frame.shape
        out["rows"] = int(n)
        out["features"] = int(k)
        out["rows_per_feature"] = round(n / max(1, k), 1)
        out["positive_rate"] = round(float(labels.mean()) if n else 0.0, 4)

        constant = [c for c in frame.columns if frame[c].nunique(dropna=False) <= 1]
        out["constant_features"] = constant[:20]

        live = frame.drop(columns=constant)
        if live.shape[1] >= 2 and n >= 50:
            corr = live.corr().abs().to_numpy()
            cols = list(live.columns)
            pairs = []
            for i in range(len(cols)):
                for j in range(i + 1, len(cols)):
                    if np.isfinite(corr[i, j]) and corr[i, j] >= 0.98:
                        pairs.append([cols[i], cols[j], round(float(corr[i, j]), 4)])
            out["collinear_pairs"] = sorted(pairs, key=lambda p: -p[2])[:10]
        else:
            out["collinear_pairs"] = []

        leak_auc = _env_float("ML_LEAK_SUSPECT_AUC", 0.90)
        suspects = []
        if n >= 200 and 0 < labels.sum() < n:
            from sklearn.metrics import roc_auc_score

            for col in live.columns:
                values = live[col].to_numpy()
                if not np.isfinite(values).all():
                    values = np.nan_to_num(values)
                try:
                    score = roc_auc_score(labels, values)
                except ValueError:
                    continue
                score = max(score, 1.0 - score)
                if score >= leak_auc:
                    suspects.append([col, round(float(score), 4)])
        out["leak_suspects"] = sorted(suspects, key=lambda p: -p[1])[:10]

        rounded = frame.round(6)
        keys = pd.util.hash_pandas_object(rounded, index=False).to_numpy()
        df = pd.DataFrame({"k": keys, "y": labels})
        groups = df.groupby("k")["y"].agg(["size", "nunique"])
        duplicated = groups[groups["size"] > 1]
        dup_rows = int(duplicated["size"].sum())
        conflict_rows = int(duplicated[duplicated["nunique"] > 1]["size"].sum())
        out["duplicate_rows"] = dup_rows
        out["label_conflict_rows"] = conflict_rows
        out["label_conflict_share"] = round(conflict_rows / dup_rows, 4) if dup_rows else 0.0

        digest = hashlib.sha256(np.ascontiguousarray(keys).tobytes() + labels.tobytes()).hexdigest()
        out["dataset_hash"] = digest[:16]
    except Exception as exc:  # the audit must never fail a training run
        out["error"] = type(exc).__name__
    try:
        from core.version import GIT_COMMIT_SHA

        out["code_commit"] = str(GIT_COMMIT_SHA or "unknown")[:12]
    except Exception:
        out["code_commit"] = "unknown"
    return out


def blocks_promotion(data_audit: dict[str, Any] | None) -> list[str]:
    """Reasons this run's data must not produce a serving model (empty: none)."""
    if not data_audit:
        return []
    reasons = []
    if data_audit.get("leak_suspects"):
        reasons.append("leak_suspects:" + ",".join(str(p[0]) for p in data_audit["leak_suspects"][:3]))
    if float(data_audit.get("label_conflict_share") or 0.0) > _env_float("ML_MAX_LABEL_CONFLICT_SHARE", 0.50) \
            and int(data_audit.get("duplicate_rows") or 0) >= 100:
        reasons.append(f"label_conflict_share:{data_audit['label_conflict_share']}")
    return reasons
