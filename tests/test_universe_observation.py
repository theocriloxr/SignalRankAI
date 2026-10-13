"""Prospective selection lineage, explicit unknown history and serving binding."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from types import SimpleNamespace

import pytest

from engine import universe_observation as universe
from engine.adaptive.market_input import capture_market_input, restore_market_input
from engine.adaptive.runtime import AdaptiveStrategyService
from tests.test_market_input_snapshot import CAPTURED, sample_context


def sample_universe():
    return universe.capture_universe_observation(
        sources={"managed": ["BTCUSDT"], "pinned": ["AAPL"], "discovered": ["ETHUSDT", "EURUSD"]},
        stages={"candidates": ["BTCUSDT", "AAPL", "ETHUSDT", "EURUSD"],
            "profile_filtered": ["BTCUSDT", "ETHUSDT", "EURUSD"],
            "market_open": ["BTCUSDT", "ETHUSDT"], "eligible": ["BTCUSDT", "ETHUSDT"],
            "scheduled": ["BTCUSDT"], "selected": ["BTCUSDT"]},
        discovery_source="database_registry", profile_filter_applied=True,
        universe_cap=1, batch_size=1, observed_at=CAPTURED,
    )


def rehash(envelope):
    envelope["content_hash"] = hashlib.sha256(json.dumps(envelope["payload"],
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return envelope


def test_observation_preserves_exclusions_and_order_without_claiming_history():
    snapshot = sample_universe()
    stored = snapshot.envelope()
    assert universe.restore_universe_observation(stored) == snapshot
    assert stored["payload"]["stages"]["candidates"] == ["BTCUSDT", "AAPL", "ETHUSDT", "EURUSD"]
    assert stored["payload"]["stages"]["profile_filtered"] == ["BTCUSDT", "ETHUSDT", "EURUSD"]
    assert set(stored["payload"]["source_history"].values()) == {"UNVERIFIED"}
    stored["payload"]["stages"]["selected"].clear()
    assert snapshot.envelope()["payload"]["stages"]["selected"] == ["BTCUSDT"]


@pytest.mark.parametrize("change", ["new_candidate", "source", "observed_at", "selection"])
def test_altered_scope_cannot_reuse_capture_identity(change):
    stored = sample_universe().envelope()
    if change == "new_candidate":
        stored["payload"]["sources"]["discovered"].append("SOLUSDT")
        stored["payload"]["stages"]["candidates"].append("SOLUSDT")
    elif change == "source":
        stored["payload"]["policy"]["discovery_source"] = "legacy_provider_discovery"
    elif change == "observed_at":
        stored["payload"]["observed_at"] = (CAPTURED + timedelta(seconds=1)).isoformat()
    else:
        stored["payload"]["stages"]["selected"] = ["ETHUSDT"]
    with pytest.raises(ValueError, match="hash_mismatch"):
        universe.restore_universe_observation(stored)


@pytest.mark.parametrize("change", ["missing_source", "extra_field", "duplicate", "naive", "history",
    "outside_candidates", "outside_eligible", "false_cap", "bool_limit", "bad_symbol", "budget"])
def test_rehashed_invalid_or_unsafe_observations_still_fail(monkeypatch, change):
    stored = sample_universe().envelope()
    payload = stored["payload"]
    if change == "missing_source":
        payload["sources"]["managed"] = []
    elif change == "extra_field":
        payload["policy"]["provider_api_key"] = "dummy"
    elif change == "duplicate":
        payload["stages"]["selected"] *= 2
    elif change == "naive":
        payload["observed_at"] = CAPTURED.replace(tzinfo=None).isoformat()
    elif change == "history":
        payload["source_history"]["prior_membership"] = "PASS"
    elif change == "outside_candidates":
        payload["stages"]["profile_filtered"].append("SOLUSDT")
    elif change == "outside_eligible":
        payload["stages"]["selected"] = ["AAPL"]
    elif change == "false_cap":
        payload["stages"]["scheduled"] = ["ETHUSDT"]
    elif change == "bool_limit":
        payload["policy"]["batch_size"] = True
    elif change == "bad_symbol":
        payload["sources"]["managed"] = ["https://user:secret@host/"]
    else:
        monkeypatch.setattr(universe, "MAX_MEMBERS", 2)
    with pytest.raises(ValueError):
        universe.restore_universe_observation(rehash(stored))


def test_class_anchor_outside_cap_is_preserved_as_actual_selection():
    stored = sample_universe().envelope()
    stored["payload"]["stages"]["selected"] = ["ETHUSDT"]
    observation = universe.restore_universe_observation(rehash(stored))
    universe.validate_universe_membership(observation.envelope(), asset="ETHUSDT", decision_time=CAPTURED)
    with pytest.raises(ValueError, match="not_selected"):
        universe.validate_universe_membership(observation.envelope(), asset="BTCUSDT", decision_time=CAPTURED)


def test_universe_cannot_be_attached_before_observation_or_to_an_unselected_asset():
    context = sample_context()
    observation = sample_universe().envelope()
    with pytest.raises(ValueError, match="after_decision"):
        capture_market_input(context, timestamp_convention="bar_open", captured_at=CAPTURED-timedelta(seconds=1),
            universe_observation=observation)
    observation["payload"]["stages"]["selected"] = ["ETHUSDT"]
    with pytest.raises(ValueError, match="not_selected"):
        capture_market_input(context, timestamp_convention="bar_open", captured_at=CAPTURED,
            universe_observation=rehash(observation))


def test_universe_and_component_capture_budgets_apply_without_truncation(monkeypatch):
    observation = sample_universe()
    monkeypatch.setattr(universe, "MAX_BYTES", 32)
    with pytest.raises(ValueError, match="byte_budget"):
        universe.restore_universe_observation(observation.envelope())


def test_runtime_keeps_universe_binding_through_actual_candidate_selection(monkeypatch):
    from engine.consensus import consensus_filter
    from engine.signal_controller import SignalController
    from engine.core import _collapse_signal_variants
    monkeypatch.setenv("ADAPTIVE_EVALUATION_TIMEFRAMES", "1h")
    monkeypatch.setenv("CONSENSUS_ENABLED", "1")
    monkeypatch.setenv("CONSENSUS_MIN_GROUPS", "1")
    monkeypatch.setenv("CONSENSUS_MIN_TOTAL_WEIGHTED_CONF", "0")
    context, observation = sample_context(), sample_universe()
    market = {"1h": {"candles": list(context.candles), "indicators": dict(context.indicators), "source": context.provider},
              "_universe_observation": observation.envelope()}
    service = AdaptiveStrategyService()
    service.components = [SimpleNamespace(evaluate=lambda context: [])]
    assessment = service.evaluate(context.asset, market, "trend")
    candidate = {"asset": context.asset, "timeframe": "1h", "direction": "LONG", "entry": 100,
        "stop_loss": 90, "take_profit": [110], "confidence": 0.9, "score": 90,
        "strategy_name": "universe-flow", "strategy_group": "trend"}
    controller = SignalController()
    selected = _collapse_signal_variants(controller.pick_best_direction_per_pair(consensus_filter(
        controller.normalize_signals(service.apply_to_signals([candidate], assessment)), min_score=0.01)))[0]
    stored = selected["_adaptive_input_snapshots"][0]
    assert selected["adaptive_sequence_refs"][0]["summary"]["universe_observation_hash"] == observation.content_hash
    assert selected["adaptive_sequence_refs"][0]["summary"]["universe_observation_status"] == "CAPTURED"
    assert stored["payload"]["universe_observation"] == observation.envelope()
    assert "universe_observation" not in assessment.to_dict()
    assert restore_market_input(stored["payload"], content_hash=stored["content_hash"]).asset == context.asset
    original = deepcopy(stored)
    market["_universe_observation"]["payload"]["stages"]["selected"] = ["ETHUSDT"]
    assert stored == original


def test_missing_legacy_universe_retains_original_input_identity():
    context = sample_context()
    legacy = capture_market_input(context, timestamp_convention="bar_open", captured_at=CAPTURED)
    assert "universe_observation" not in json.loads(legacy.payload)
    assert capture_market_input(context, timestamp_convention="bar_open", captured_at=CAPTURED,
        universe_observation=None) == legacy
    captured = capture_market_input(context, timestamp_convention="bar_open", captured_at=CAPTURED,
        universe_observation=sample_universe().envelope())
    assert captured.content_hash != legacy.content_hash


def test_v2_records_full_queue_and_bounds_work_without_rewriting_v1():
    legacy = sample_universe().envelope()
    payload = legacy["payload"]
    stages = deepcopy(payload["stages"])
    stages["scheduled"] = list(stages["eligible"])
    stages["selected"] = ["ETHUSDT"]
    current = universe.capture_universe_observation(
        sources=payload["sources"], stages=stages, discovery_source="database_registry",
        profile_filter_applied=True, universe_cap=1, batch_size=1, observed_at=CAPTURED,
        selection_policy="engine-class-round-robin-v2",
    )
    assert current.envelope()["payload"]["format_version"] == 2
    assert current.envelope()["payload"]["policy"]["universe_cap_scope"] == "per_cycle_work"
    assert universe.restore_universe_observation(current.envelope()) == current
    assert universe.restore_universe_observation(legacy).envelope() == legacy
    assert legacy["payload"]["format_version"] == 1
    assert legacy["payload"]["stages"]["scheduled"] == ["BTCUSDT"]
    universe.validate_universe_membership(current.envelope(), asset="ETHUSDT", decision_time=CAPTURED)
    for change in ("prefix", "scope", "format", "budget"):
        altered = current.envelope()
        if change == "prefix":
            altered["payload"]["stages"]["scheduled"] = ["BTCUSDT"]
        elif change == "scope":
            altered["payload"]["policy"]["universe_cap_scope"] = "full_universe"
        elif change == "format":
            altered["payload"]["format_version"] = 1
        else:
            altered["payload"]["stages"]["selected"] = ["BTCUSDT", "ETHUSDT"]
        with pytest.raises(ValueError):
            universe.restore_universe_observation(rehash(altered))
