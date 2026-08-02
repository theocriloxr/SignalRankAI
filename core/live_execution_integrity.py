"""Fail-closed admission policy for real-money auto and copy execution."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

from core.production_integrity import evaluate_signal_freshness
from core.signal_quality_gate import evaluate_signal_quality


def _enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class LiveAdmissionDecision:
    allowed: bool
    reasons: tuple[str, ...]


def evaluate_live_signal_admission(
    signal: Mapping[str, Any],
    *,
    require_production_certification: bool = True,
    require_provider_provenance: bool | None = None,
) -> LiveAdmissionDecision:
    reasons: list[str] = []
    if require_production_certification:
        if not _enabled("PRODUCTION_INTEGRITY_CERTIFIED", False):
            reasons.append("production_integrity_not_certified")
        if not str(os.getenv("LIVE_RUNTIME_CERTIFICATION_ID") or "").strip():
            reasons.append("live_runtime_certification_id_missing")
    quality = evaluate_signal_quality(signal, execution=True)
    reasons.extend(quality.reasons)
    freshness = evaluate_signal_freshness(
        timeframe=signal.get("timeframe"),
        generated_at=signal.get("generated_at") or signal.get("created_at"),
        explicit_age_seconds=signal.get("signal_age_seconds"),
        purpose="live",
    )
    if not freshness.ok:
        reasons.append(freshness.reason)
    if not str(signal.get("thesis_fingerprint") or quality.thesis_fingerprint).strip():
        reasons.append("thesis_fingerprint_missing")
    provider_required = (
        _enabled("LIVE_EXECUTION_REQUIRES_PROVIDER_DISCOVERY", True)
        if require_provider_provenance is None
        else bool(require_provider_provenance)
    )
    if provider_required:
        provenance = str(signal.get("asset_discovery_provider") or signal.get("provider_provenance") or "").strip()
        if not provenance:
            reasons.append("asset_provider_provenance_missing")
    return LiveAdmissionDecision(not reasons, tuple(dict.fromkeys(reasons)))
