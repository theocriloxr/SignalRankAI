"""Capture actual prospective engine selection, without inventing past listings.

The observation is embedded in immutable component input records. Its scope is
the candidates seen by this engine cycle, not the entire investable market.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

MAX_MEMBERS = 2000
MAX_BYTES = 256 * 1024
STAGES = ("candidates", "profile_filtered", "market_open", "eligible", "scheduled", "selected")
SOURCES = ("managed", "pinned", "discovered")
HISTORY = {"prior_membership": "UNVERIFIED", "listing_and_delisting": "UNVERIFIED",
           "corporate_actions": "UNVERIFIED", "calendar_rules": "UNVERIFIED"}


def _json(value: Any) -> str:
    chunks: list[str] = []
    size = 0
    for chunk in json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False).iterencode(value):
        size += len(chunk.encode())
        if size > MAX_BYTES:
            raise ValueError("universe_observation_byte_budget_exceeded")
        chunks.append(chunk)
    return "".join(chunks)


def _instant(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            raise ValueError("universe_observation_timestamp_invalid") from None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("universe_observation_timestamp_must_be_aware")
    return value.astimezone(timezone.utc)


def _members(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)) or len(value) > MAX_MEMBERS:
        raise ValueError("universe_observation_member_budget_exceeded")
    if any(not isinstance(item, str) or not re.fullmatch(r"[A-Z0-9^][A-Z0-9._:/^=+\-]{0,127}", item)
           for item in value):
        raise ValueError("universe_observation_symbol_invalid")
    if len(set(value)) != len(value):
        raise ValueError("universe_observation_duplicate_members")
    return list(value)


@dataclass(frozen=True, slots=True)
class UniverseObservation:
    content_hash: str
    payload: str
    observed_at: datetime

    def envelope(self) -> dict[str, Any]:
        # Each consumer gets a detached copy; the shared cycle capture is frozen.
        return {"content_hash": self.content_hash, "payload": json.loads(self.payload)}


def capture_universe_observation(
    *, sources: Mapping[str, Sequence[str]], stages: Mapping[str, Sequence[str]],
    discovery_source: str, profile_filter_applied: bool, universe_cap: int,
    batch_size: int, observed_at: datetime | None = None,
    selection_policy: str = "engine-class-round-robin-v1",
) -> UniverseObservation:
    if set(sources) != set(SOURCES) or set(stages) != set(STAGES):
        raise ValueError("universe_observation_stages_invalid")
    format_version = 2 if selection_policy == "engine-class-round-robin-v2" else 1
    payload = {"format_version": format_version, "scope": "observed_engine_selection_only",
        "observed_at": _instant(observed_at or datetime.now(timezone.utc)).isoformat(),
        "sources": {key: _members(sources[key]) for key in SOURCES},
        "stages": {key: _members(stages[key]) for key in STAGES},
        "policy": {"version": selection_policy, "discovery_source": discovery_source,
            "profile_filter_applied": profile_filter_applied, "universe_cap": universe_cap,
            "batch_size": batch_size}, "source_history": dict(HISTORY)}
    if format_version == 2:
        payload["policy"]["universe_cap_scope"] = "per_cycle_work"
    encoded = _json(payload)
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    restore_universe_observation({"content_hash": digest, "payload": payload})
    return UniverseObservation(digest, encoded, _instant(payload["observed_at"]))


def restore_universe_observation(envelope: Any) -> UniverseObservation:
    if not isinstance(envelope, dict) or set(envelope) != {"content_hash", "payload"}:
        raise ValueError("universe_observation_envelope_invalid")
    payload, digest = envelope["payload"], envelope["content_hash"]
    if not isinstance(payload, dict) or set(payload) != {
        "format_version", "scope", "observed_at", "sources", "stages", "policy", "source_history",
    }:
        raise ValueError("universe_observation_payload_invalid")
    if type(payload["format_version"]) is not int or payload["format_version"] not in (1, 2):
        raise ValueError("universe_observation_format_invalid")
    if payload["scope"] != "observed_engine_selection_only" or payload["source_history"] != HISTORY:
        raise ValueError("universe_observation_history_invalid")
    observed = _instant(payload["observed_at"])
    if observed.isoformat() != payload["observed_at"]:
        raise ValueError("universe_observation_timestamp_noncanonical")
    sources, stages, policy = payload["sources"], payload["stages"], payload["policy"]
    if not isinstance(sources, dict) or set(sources) != set(SOURCES):
        raise ValueError("universe_observation_sources_invalid")
    if not isinstance(stages, dict) or set(stages) != set(STAGES):
        raise ValueError("universe_observation_stages_invalid")
    for members in (*sources.values(), *stages.values()):
        _members(members)
    policy_keys = {
        "version", "discovery_source", "profile_filter_applied", "universe_cap", "batch_size",
    }
    if payload["format_version"] == 2:
        policy_keys.add("universe_cap_scope")
    if not isinstance(policy, dict) or set(policy) != policy_keys:
        raise ValueError("universe_observation_policy_invalid")
    if (policy["version"] != f'engine-class-round-robin-v{payload["format_version"]}'
        or (payload["format_version"] == 2 and policy["universe_cap_scope"] != "per_cycle_work")
        or policy["discovery_source"] not in {"legacy_provider_discovery", "database_registry", "legacy_provider_discovery_fallback"}
        or type(policy["profile_filter_applied"]) is not bool
        or any(type(policy[key]) is not int or not 1 <= policy[key] <= MAX_MEMBERS for key in ("universe_cap", "batch_size"))
        or policy["batch_size"] > policy["universe_cap"]):
        raise ValueError("universe_observation_policy_invalid")
    candidates = list(dict.fromkeys(item for key in SOURCES for item in sources[key]))
    if candidates != stages["candidates"]:
        raise ValueError("universe_observation_candidate_sources_mismatch")
    for before, after in zip(STAGES[:4], STAGES[1:5]):
        if not set(stages[after]).issubset(stages[before]):
            raise ValueError("universe_observation_stage_membership_mismatch")
    # Class coverage anchors may come from eligible members outside the cap.
    # This distinction is preserved rather than falsely claiming cap membership.
    if (not stages["selected"] or not set(stages["selected"]).issubset(stages["eligible"])
        or stages["scheduled"] != (stages["eligible"][:policy["universe_cap"]]
                                   if payload["format_version"] == 1 else stages["eligible"])
        or len(stages["selected"]) > policy["batch_size"]):
        raise ValueError("universe_observation_selection_mismatch")
    encoded = _json(payload)
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) or hashlib.sha256(encoded.encode()).hexdigest() != digest:
        raise ValueError("universe_observation_content_hash_mismatch")
    return UniverseObservation(digest, encoded, observed)


def validate_universe_membership(envelope: Any, *, asset: str, decision_time: datetime) -> UniverseObservation:
    observation = restore_universe_observation(envelope)
    if observation.observed_at > _instant(decision_time):
        raise ValueError("universe_observation_after_decision")
    if asset not in json.loads(observation.payload)["stages"]["selected"]:
        raise ValueError("universe_observation_asset_not_selected")
    return observation
