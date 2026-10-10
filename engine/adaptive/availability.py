"""Audit captured sequence timing without certifying feature or universe history.

Persistence time is deliberately not a substitute for source observation time.
Missing legacy metadata stays unverified. A proven temporal violation cannot be
made acceptable by omitting another field or another sequence's metadata.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence


def _instant(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc)


def _milliseconds(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        if not math.isfinite(value) or value < 0:
            return None
        return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=value)
    except (OverflowError, ValueError):
        return None


def canonical_sequence_provenance(value: Any) -> tuple[str, ...]:
    """Bound and freeze actual persisted references; do not silently truncate."""
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or len(value) > 8:
        raise ValueError("invalid_sequence_provenance_budget")
    encoded: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("invalid_sequence_provenance")
        summary = item.get("summary")
        summary = summary if isinstance(summary, Mapping) else {}
        # Whitelist scientific metadata; raw payloads or credentials are never
        # copied into the research manifest. Unknown required fields remain null.
        payload = {key: item.get(key) for key in (
            "asset", "timeframe", "sequence_hash", "candle_count", "start_time_ms",
            "end_time_ms", "provider", "evidence_stage",
        )}
        payload.update({key: summary.get(key) for key in (
            "captured_at", "timestamp_convention", "publication_vintage",
        )})
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(raw.encode()) > 4096:
            raise ValueError("sequence_provenance_too_large")
        encoded.append(raw)
    return tuple(sorted(encoded))


def audit_sequence_availability(
    references: Sequence[str], *, asset: str, decision_time: datetime,
    sequence_hashes: Sequence[str],
) -> dict[str, Any]:
    """A PASS covers captured closed-bar timing only, never survivorship/repainting."""
    if not references:
        return {"status": "UNVERIFIED", "reasons": ["sequence_provenance_unavailable"]}
    decision = _instant(decision_time)
    failures: set[str] = set()
    unknown: set[str] = set()
    hashes: list[str] = []
    if decision is None:
        failures.add("decision_timestamp_invalid")
    for raw in references:
        ref = json.loads(raw)
        digest = ref.get("sequence_hash")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            failures.add("sequence_hash_invalid")
        else:
            hashes.append(digest)
        if ref.get("asset") != asset or ref.get("evidence_stage") != "pre_signal":
            failures.add("sequence_scope_mismatch")
        count = ref.get("candle_count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            failures.add("sequence_count_invalid")
        opened = _milliseconds(ref.get("end_time_ms"))
        start = _milliseconds(ref.get("start_time_ms"))
        if opened is None or start is None or start > opened:
            failures.add("sequence_timestamps_invalid")
        match = re.fullmatch(r"([1-9][0-9]{0,4})(m|h|d|w)", str(ref.get("timeframe")))
        closed = None
        if match and ref.get("timestamp_convention") == "bar_open":
            try:
                closed = opened + timedelta(seconds=int(match[1]) * {"m": 60, "h": 3600, "d": 86400, "w": 604800}[match[2]]) if opened else None
            except OverflowError:
                failures.add("sequence_duration_overflow")
        elif not match:
            unknown.add("sequence_calendar_duration_unverified")
        captured = _instant(ref.get("captured_at"))
        if captured is None:
            unknown.add("sequence_capture_time_unavailable")
            if ref.get("captured_at") is not None:
                failures.add("sequence_capture_time_invalid")
        if ref.get("timestamp_convention") != "bar_open":
            unknown.add("sequence_timestamp_convention_unverified")
        if str(ref.get("provider") or "unknown").lower() in {"unknown", "none", ""}:
            unknown.add("sequence_provider_unavailable")
        if decision is not None:
            if opened is not None and opened > decision:
                failures.add("sequence_timestamp_after_decision")
            if captured is not None and captured > decision:
                failures.add("sequence_captured_after_decision")
            if closed is not None and closed > decision:
                failures.add("sequence_bar_unclosed_at_decision")
        if captured is not None and closed is not None and closed > captured:
            failures.add("sequence_bar_unclosed_at_capture")
    if len(hashes) != len(set(hashes)) or set(hashes) != set(sequence_hashes):
        failures.add("sequence_lineage_mismatch")
    return {"status": "FAIL" if failures else "UNVERIFIED" if unknown else "PASS",
            "reasons": sorted(failures | unknown), "scope": "captured_closed_bar_timing_only"}
