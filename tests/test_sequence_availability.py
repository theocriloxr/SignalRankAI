from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest

from engine.adaptive.availability import audit_sequence_availability, canonical_sequence_provenance
from engine.adaptive.dataset import build_dataset
from engine.adaptive.integrity import audit_adaptive_dataset
from engine.adaptive.sequence import sequence_reference
from engine.adaptive.walk_forward import walk_forward_evaluate


DECISION = datetime(2026, 1, 2, tzinfo=timezone.utc)
HASH = "a" * 64


def reference():
    return {"asset": "BTCUSDT", "timeframe": "1h", "sequence_hash": HASH,
        "candle_count": 20, "start_time_ms": int((DECISION - timedelta(hours=20)).timestamp() * 1000),
        "end_time_ms": int((DECISION - timedelta(hours=1)).timestamp() * 1000),
        "provider": "test-provider", "evidence_stage": "pre_signal",
        "summary": {"captured_at": DECISION.isoformat(), "timestamp_convention": "bar_open",
                    "publication_vintage": "unverified"}}


def audit(ref):
    return audit_sequence_availability(canonical_sequence_provenance([ref]),
        asset="BTCUSDT", decision_time=DECISION, sequence_hashes=[HASH])


def test_exact_close_and_capture_cutoff_is_inclusive_without_claiming_vintages():
    result = audit(reference())
    assert result["status"] == "PASS"
    assert result["scope"] == "captured_closed_bar_timing_only"


@pytest.mark.parametrize("change,reason", [
    ({"asset": "EURUSD"}, "sequence_scope_mismatch"),
    ({"evidence_stage": "post_signal"}, "sequence_scope_mismatch"),
    ({"sequence_hash": "b" * 64}, "sequence_lineage_mismatch"),
    ({"candle_count": True}, "sequence_count_invalid"),
    ({"start_time_ms": float("inf")}, "nonfinite_json"),
    ({"end_time_ms": True}, "sequence_timestamps_invalid"),
    ({"end_time_ms": int(DECISION.timestamp() * 1000)}, "sequence_bar_unclosed_at_decision"),
])
def test_malformed_and_future_sequence_inputs_cannot_qualify(change, reason):
    ref = reference() | change
    if reason == "nonfinite_json":
        with pytest.raises(ValueError):
            audit(ref)
    else:
        result = audit(ref)
        assert result["status"] == "FAIL" and reason in result["reasons"]


@pytest.mark.parametrize("captured", [(DECISION + timedelta(microseconds=1)).isoformat(), "invalid", "2026-01-02"])
def test_late_or_malformed_capture_time_is_not_persistence_proof(captured):
    ref = reference()
    ref["summary"]["captured_at"] = captured
    assert audit(ref)["status"] == "FAIL"


def test_unknown_metadata_cannot_mask_a_known_temporal_violation():
    ref = reference()
    ref["provider"] = "unknown"
    ref["summary"].pop("captured_at")
    ref["end_time_ms"] = int(DECISION.timestamp() * 1000)
    result = audit(ref)
    assert result["status"] == "FAIL"
    assert "sequence_bar_unclosed_at_decision" in result["reasons"]
    assert "sequence_capture_time_unavailable" in result["reasons"]


@pytest.mark.parametrize("variant", ["legacy", "provider", "convention", "duration"])
def test_unavailable_provenance_remains_unverified(variant):
    ref = reference()
    if variant == "legacy":
        ref["summary"] = {}
    elif variant == "provider":
        ref["provider"] = "unknown"
    elif variant == "convention":
        ref["summary"]["timestamp_convention"] = "close"
    else:
        ref["timeframe"] = "1M"
    assert audit(ref)["status"] == "UNVERIFIED"


def test_hashes_alone_are_not_point_in_time_evidence():
    assert audit_sequence_availability((), asset="BTCUSDT", decision_time=DECISION,
        sequence_hashes=[HASH])["status"] == "UNVERIFIED"


def rows():
    return [{"signal_id": str(i), "asset": "BTCUSDT", "family": "trend", "regime": "trend",
        "decision_time": DECISION + timedelta(hours=i),
        "outcome_known_at": DECISION + timedelta(hours=i, minutes=30),
        "r_multiple": -0.5 if i % 5 == 0 else 0.3, "evidence_category": "shadow",
        "sequence_hashes": [HASH], "sequence_provenance": [reference()]} for i in range(160)]


def test_revised_sequence_provenance_changes_dataset_identity_and_is_frozen():
    raw = rows()
    dataset, original = build_dataset(raw)
    frozen = dataset[0].sequence_provenance
    raw[0]["sequence_provenance"][0]["provider"] = "different-provider"
    _, revised = build_dataset(raw)
    assert original.content_hash != revised.content_hash
    assert dataset[0].sequence_provenance == frozen
    assert "test-provider" in frozen[0]


def test_future_provenance_blocks_actual_walk_forward_and_integrity():
    raw = rows()
    raw[0]["sequence_provenance"][0]["summary"]["captured_at"] = (DECISION + timedelta(days=1)).isoformat()
    dataset, _ = build_dataset(raw)
    wfo = walk_forward_evaluate(dataset, family_weights={}, minimum_train=60, validation_size=20)
    assert not wfo.folds and "sequence_availability_violation" in wfo.reasons
    report = audit_adaptive_dataset(dataset, wfo)
    assert not report["passed"]
    assert next(c for c in report["checks"] if c["check_id"] == "captured_sequence_availability")["status"] == "FAIL"


def test_valid_capture_does_not_certify_feature_repainting_or_survivorship():
    dataset, _ = build_dataset(rows())
    wfo = walk_forward_evaluate(dataset, family_weights={}, minimum_train=60, validation_size=20)
    assert wfo.folds and wfo.leakage_checks_passed
    report = audit_adaptive_dataset(dataset, wfo)
    checks = {c["check_id"]: c["status"] for c in report["checks"]}
    assert checks["captured_sequence_availability"] == "PASS"
    assert checks["survivorship"] == checks["lookahead_and_repainting"] == "UNVERIFIED"
    assert not report["passed"]


def test_future_label_mutations_cannot_change_an_as_of_dataset():
    raw = rows()
    cutoff = DECISION + timedelta(hours=100)
    earlier, original = build_dataset(raw, as_of=cutoff)
    mutated = deepcopy(raw)
    for row in mutated[100:]:
        row["r_multiple"] = 1000
    same, unchanged = build_dataset(mutated, as_of=cutoff)
    assert same == earlier and unchanged == original and original.row_count == 100
    corrected = deepcopy(raw)
    corrected[0]["outcome_known_at"] = cutoff + timedelta(seconds=1)
    labels, _ = build_dataset(corrected, as_of=cutoff)
    assert len(labels) == 99 and all(row.signal_id != "0" for row in labels)
    unknown = [raw[0] | {"outcome_known_at": None}]
    assert not build_dataset(unknown, as_of=cutoff)[0]


def test_as_of_rejects_naive_clocks_and_includes_exactly_available_labels():
    with pytest.raises(ValueError, match="as_of_must_be_aware"):
        build_dataset(rows(), as_of=DECISION.replace(tzinfo=None))
    assert build_dataset(rows(), as_of=DECISION + timedelta(minutes=30))[1].row_count == 1


def test_normalized_timestamp_alias_does_not_invent_an_open_convention():
    candle = {"close_time_ms": int(DECISION.timestamp() * 1000), "open": 10, "high": 11, "low": 9, "close": 10}
    ref = sequence_reference("BTCUSDT", "1h", {"candles": [candle], "source": "test-provider"})
    assert ref["summary"]["timestamp_convention"] == "unverified"
    datetime.fromisoformat(ref["summary"]["captured_at"])
    candle["open_time_ms"] = candle.pop("close_time_ms")
    assert sequence_reference("BTCUSDT", "1h", {"candles": [candle]})["summary"]["timestamp_convention"] == "bar_open"


def test_provenance_budget_rejects_excess_instead_of_dropping_bad_evidence():
    with pytest.raises(ValueError, match="budget"):
        canonical_sequence_provenance([reference()] * 9)
    ref = reference() | {"provider": "p" * 4096}
    with pytest.raises(ValueError, match="too_large"):
        canonical_sequence_provenance([ref])
    ref = reference() | {"api_key": "never_copy"}
    assert "never_copy" not in json.dumps(canonical_sequence_provenance([ref]))


def test_oversized_snapshot_is_rejected_before_materialization():
    class Oversized:
        def __len__(self):
            return 100_001
        def __iter__(self):
            pytest.fail("oversized input must not be consumed")
    with pytest.raises(ValueError, match="row_budget"):
        build_dataset(Oversized())


def test_streamed_input_budget_cannot_be_bypassed_with_unresolved_rows():
    with pytest.raises(ValueError, match="row_budget"):
        build_dataset({} for _ in range(100_001))
