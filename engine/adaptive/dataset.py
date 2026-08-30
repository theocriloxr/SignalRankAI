from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence


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

    def canonical(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["decision_time"] = self.decision_time.isoformat()
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


def build_dataset(rows: Iterable[Mapping[str, Any]], *, dataset_namespace: str = "adaptive-v1") -> tuple[tuple[AdaptiveDatasetRow, ...], DatasetManifest]:
    parsed: list[AdaptiveDatasetRow] = []
    for row in rows:
        dt = row.get("decision_time") or row.get("created_at")
        if not isinstance(dt, datetime):
            continue
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
                r_multiple=float(row.get("r_multiple") or 0.0),
                evidence_category=normalise_evidence_category(row.get("evidence_category") or row.get("status"), delivered=delivered, executed=executed),
                sequence_hashes=sequence_hashes,
                data_quality_score=max(0.0, min(1.0, float(row.get("data_quality_score") or 0.0))),
                profile_id=str(row.get("profile_id")) if row.get("profile_id") else None,
            )
        )
    parsed.sort(key=lambda item: (item.decision_time, item.signal_id))
    canonical = [item.canonical() for item in parsed]
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
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
