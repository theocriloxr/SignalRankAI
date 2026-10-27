from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from collections.abc import Sized
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from .availability import canonical_sequence_provenance

MAX_DATASET_ROWS = 100_000


_ALLOWED_EVIDENCE_CATEGORIES = {
    "generated",
    "stored",
    "rejected",
    "paper",
    "shadow",
    "backtest",
    "walk_forward",
    "forward_test",
    "canary",
    "owner_beta",
    "live_delivered",
    "live_executed",
}


@dataclass(frozen=True, slots=True)
class AdaptiveDatasetRow:
    signal_id: str
    decision_time: datetime
    asset: str
    asset_class: str
    timeframe: str
    family: str
    regime: str
    direction: str
    r_multiple: float
    evidence_category: str
    sequence_hashes: tuple[str, ...] = ()
    data_quality_score: float = 0.0
    profile_id: str | None = None
    outcome_known_at: datetime | None = None
    sequence_provenance: tuple[str, ...] = ()

    def canonical(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["decision_time"] = self.decision_time.isoformat()
        payload["outcome_known_at"] = self.outcome_known_at.isoformat() if self.outcome_known_at else None
        return payload


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    dataset_version: str
    row_count: int
    first_decision_time: datetime | None
    last_decision_time: datetime | None
    evidence_categories: tuple[str, ...]
    assets: tuple[str, ...]
    sequence_coverage: float
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["first_decision_time"] = self.first_decision_time.isoformat() if self.first_decision_time else None
        payload["last_decision_time"] = self.last_decision_time.isoformat() if self.last_decision_time else None
        return payload


def normalise_evidence_category(value: Any, *, delivered: bool = False, executed: bool = False) -> str:
    raw = str(value or "stored").strip().lower().replace("-", "_")
    aliases = {
        "issued": "stored",
        "active": "stored",
        "confirmed": "live_delivered",
        "delivered": "live_delivered",
        "paper_trade": "paper",
        "shadow_signal": "shadow",
        "wfo": "walk_forward",
        "limited_live": "canary",
    }
    category = aliases.get(raw, raw)
    if executed:
        category = "live_executed"
    elif delivered and category in {"generated", "stored", "rejected"}:
        category = "live_delivered"
    return category if category in _ALLOWED_EVIDENCE_CATEGORIES else "stored"


def build_dataset(
    rows: Iterable[Mapping[str, Any]], *, dataset_namespace: str = "adaptive-v2",
    as_of: datetime | None = None,
) -> tuple[tuple[AdaptiveDatasetRow, ...], DatasetManifest]:
    if as_of is not None:
        if not isinstance(as_of, datetime) or as_of.tzinfo is None:
            raise ValueError("dataset_as_of_must_be_aware")
        as_of = as_of.astimezone(timezone.utc)
    parsed: list[AdaptiveDatasetRow] = []
    if isinstance(rows, Sized) and len(rows) > MAX_DATASET_ROWS:
        raise ValueError("adaptive_dataset_row_budget_exceeded")
    for ordinal, row in enumerate(rows):
        if ordinal >= MAX_DATASET_ROWS:
            raise ValueError("adaptive_dataset_row_budget_exceeded")
        dt = row.get("decision_time") or row.get("created_at")
        if not isinstance(dt, datetime):
            continue
        # Legacy DB timestamps are UTC-naive. Canonical datasets use UTC-aware
        # timestamps so mixed providers cannot silently change chronology.
        dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        known_at = row.get("outcome_known_at")
        if isinstance(known_at, datetime):
            known_at = known_at.replace(tzinfo=timezone.utc) if known_at.tzinfo is None else known_at.astimezone(timezone.utc)
        else:
            known_at = None
        if as_of is not None and (dt > as_of or known_at is None or known_at > as_of):
            continue  # Future or unavailable labels cannot enter this snapshot.
        if row.get("r_multiple") is None:
            continue  # An unresolved outcome is not a break-even trade.
        result_r = float(row["r_multiple"])
        quality = float(row.get("data_quality_score") or 0.0)
        if not math.isfinite(result_r) or not math.isfinite(quality):
            raise ValueError("non_finite_adaptive_dataset_value")
        if known_at is not None and known_at < dt:
            raise ValueError("outcome_precedes_decision")
        sequence_hashes = tuple(sorted({str(x) for x in (row.get("sequence_hashes") or ()) if x}))
        delivered = bool(row.get("delivered"))
        executed = bool(row.get("executed"))
        parsed.append(
            AdaptiveDatasetRow(
                signal_id=str(row.get("signal_id") or ""),
                decision_time=dt,
                asset=str(row.get("asset") or "UNKNOWN").upper(),
                asset_class=str(row.get("asset_class") or "unknown").lower(),
                timeframe=str(row.get("timeframe") or "unknown").lower(),
                family=str(row.get("family") or row.get("strategy_group") or "unknown").lower(),
                regime=str(row.get("regime") or "unknown").lower(),
                direction=str(row.get("direction") or "UNKNOWN").upper(),
                r_multiple=result_r,
                evidence_category=normalise_evidence_category(
                    row.get("evidence_category") or row.get("status"), delivered=delivered, executed=executed
                ),
                sequence_hashes=sequence_hashes,
                data_quality_score=max(0.0, min(1.0, quality)),
                profile_id=str(row.get("profile_id")) if row.get("profile_id") else None,
                outcome_known_at=known_at,
                sequence_provenance=canonical_sequence_provenance(row.get("sequence_provenance")),
            )
        )
    parsed.sort(key=lambda item: (item.decision_time, item.signal_id))
    canonical = [item.canonical() for item in parsed]
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    categories = tuple(sorted({item.evidence_category for item in parsed}))
    assets = tuple(sorted({item.asset for item in parsed}))
    with_sequences = sum(1 for item in parsed if item.sequence_hashes)
    sequence_coverage = with_sequences / len(parsed) if parsed else 0.0
    manifest = DatasetManifest(
        dataset_version=f"{dataset_namespace}:{digest[:20]}",
        row_count=len(parsed),
        first_decision_time=parsed[0].decision_time if parsed else None,
        last_decision_time=parsed[-1].decision_time if parsed else None,
        evidence_categories=categories,
        assets=assets,
        sequence_coverage=round(sequence_coverage, 6),
        content_hash=digest,
    )
    return tuple(parsed), manifest


def dataset_payload(rows: Sequence[AdaptiveDatasetRow], manifest: DatasetManifest) -> dict[str, Any]:
    return {"manifest": manifest.to_dict(), "rows": [row.canonical() for row in rows]}
