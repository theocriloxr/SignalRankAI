from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from engine.adaptive import dataset_snapshot
from engine.adaptive.dataset import build_dataset
from engine.adaptive.dataset_snapshot import encode_dataset_snapshot, restore_dataset_snapshot
from engine.adaptive.walk_forward import walk_forward_evaluate


CUTOFF = datetime(2026, 2, 1, tzinfo=timezone.utc)


def inputs():
    first = CUTOFF - timedelta(days=10)
    return [{"signal_id": str(i), "decision_time": first + timedelta(hours=i),
        "outcome_known_at": first + timedelta(hours=i, minutes=30),
        "asset": "BTCUSDT", "asset_class": "crypto", "timeframe": "1h",
        "family": "trend", "regime": "trending", "direction": "LONG",
        "r_multiple": -0.5 if i % 5 == 0 else 0.4, "evidence_category": "shadow",
        "data_quality_score": 0.9, "sequence_hashes": ["a" * 64],
        "sequence_provenance": [{"asset": "BTCUSDT", "timeframe": "1h",
            "sequence_hash": "a" * 64, "candle_count": 20,
            "start_time_ms": int((first + timedelta(hours=i - 20)).timestamp() * 1000),
            "end_time_ms": int((first + timedelta(hours=i - 1)).timestamp() * 1000),
            "provider": "synthetic-test", "evidence_stage": "pre_signal",
            "summary": {"captured_at": (first + timedelta(hours=i)).isoformat(),
                "timestamp_convention": "bar_open", "publication_vintage": "unverified"}}]}
        for i in range(160)]


def snapshot():
    rows, manifest = build_dataset(inputs(), as_of=CUTOFF)
    return rows, manifest, json.loads(encode_dataset_snapshot(rows, manifest))


def test_replay_restores_exact_rows_and_folds_after_the_source_changes():
    raw = inputs()
    rows, manifest = build_dataset(raw, as_of=CUTOFF)
    encoded = encode_dataset_snapshot(rows, manifest)
    raw[0]["r_multiple"] = -500
    raw[0]["sequence_provenance"][0]["provider"] = "revised-provider"
    restored, restored_manifest = restore_dataset_snapshot(json.loads(encoded), observation_cutoff=CUTOFF)
    assert (restored, restored_manifest) == (rows, manifest)
    assert build_dataset(raw, as_of=CUTOFF)[1].content_hash != manifest.content_hash
    def evaluate(data):
        return walk_forward_evaluate(data, family_weights={}, minimum_train=80, validation_size=20).to_dict()
    assert evaluate(restored) == evaluate(rows)


@pytest.mark.parametrize("change", ["return", "order", "provider", "manifest_count", "unknown_field",
    "naive_time", "future_label", "boolean_quality", "duplicate_hash", "unresolved", "missing_field"])
def test_changed_or_noncanonical_snapshot_cannot_be_replayed(change):
    _, _, payload = snapshot()
    row = payload["rows"][0]
    if change == "return": row["r_multiple"] = 999
    elif change == "order": payload["rows"].reverse()
    elif change == "provider":
        ref = json.loads(row["sequence_provenance"][0]); ref["provider"] = "revised"
        row["sequence_provenance"][0] = json.dumps(ref)
    elif change == "manifest_count": payload["manifest"]["row_count"] = 1
    elif change == "unknown_field": row["api_key"] = "never_accept"
    elif change == "naive_time": row["decision_time"] = row["decision_time"].replace("+00:00", "")
    elif change == "future_label": row["outcome_known_at"] = (CUTOFF + timedelta(days=1)).isoformat()
    elif change == "boolean_quality": row["data_quality_score"] = True
    elif change == "duplicate_hash": row["sequence_hashes"] *= 2
    elif change == "unresolved": row["outcome_known_at"] = None
    elif change == "missing_field": del row["family"]
    with pytest.raises(ValueError):
        restore_dataset_snapshot(payload, observation_cutoff=CUTOFF)


def test_snapshot_budget_rejects_excess_and_never_returns_a_truncated_dataset(monkeypatch):
    rows, manifest, payload = snapshot()
    monkeypatch.setattr(dataset_snapshot, "MAX_SNAPSHOT_BYTES", 1024)
    with pytest.raises(ValueError, match="byte_budget"):
        encode_dataset_snapshot(rows, manifest)
    with pytest.raises(ValueError, match="byte_budget"):
        restore_dataset_snapshot(payload, observation_cutoff=CUTOFF)


def test_manifest_must_describe_the_actual_rows_and_empty_snapshots_round_trip():
    rows, manifest, _ = snapshot()
    with pytest.raises(ValueError, match="row_count"):
        encode_dataset_snapshot(rows, replace(manifest, row_count=1))
    with pytest.raises(ValueError, match="content_hash"):
        encode_dataset_snapshot(rows, replace(manifest, content_hash="0" * 64))
    empty, empty_manifest = build_dataset([], as_of=CUTOFF)
    payload = json.loads(encode_dataset_snapshot(empty, empty_manifest))
    assert restore_dataset_snapshot(payload, observation_cutoff=CUTOFF) == (empty, empty_manifest)


def test_replay_requires_a_cutoff_and_cannot_use_an_earlier_unavailable_label():
    _, _, payload = snapshot()
    with pytest.raises(ValueError, match="aware"):
        restore_dataset_snapshot(payload, observation_cutoff=CUTOFF.replace(tzinfo=None))
    with pytest.raises(ValueError):
        restore_dataset_snapshot(deepcopy(payload), observation_cutoff=CUTOFF - timedelta(days=9))
