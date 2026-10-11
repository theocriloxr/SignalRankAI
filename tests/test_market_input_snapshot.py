"""Captured component values, privacy/resource boundaries and legacy replay."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from engine.adaptive import market_input
from engine.adaptive.data_quality import assess_candle_quality
from engine.adaptive.dataset import build_dataset
from engine.adaptive.dataset_snapshot import encode_dataset_snapshot, restore_dataset_snapshot
from engine.adaptive.market_input import capture_market_input, restore_market_input
from engine.adaptive.profiles import _profile_from_mapping
from engine.adaptive.runtime import AdaptiveStrategyService
from engine.adaptive.types import MarketContext

CAPTURED = datetime(2026, 1, 20, tzinfo=timezone.utc)


def sample_context():
    candles = tuple({"open_time_ms": int((CAPTURED - timedelta(hours=40-i)).timestamp()*1000),
        "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 10.0,
        "buy_volume": 6.0} for i in range(40))
    quality = assess_candle_quality(candles, timeframe="1h", provider="synthetic-owned", data_age_seconds=1)
    return MarketContext("BTCUSDT", "crypto", "1h", candles, {"ema_fast": 101.0, "ema_slow": 100.0},
        "trend", "london", "synthetic-owned", quality, "LONG", {"sentiment": 0.2}, {"rates": {"value": 4.0}})


def test_input_replay_retains_full_features_and_is_detached_and_immutable():
    source = sample_context()
    capture = capture_market_input(source, timestamp_convention="bar_open", captured_at=CAPTURED)
    source.candles[-1]["close"] = 999.0
    source.indicators["ema_fast"] = 999.0
    replay = restore_market_input(json.loads(capture.payload), content_hash=capture.content_hash)
    assert replay.candles[-1]["close"] == 101.0
    assert replay.candles[-1]["buy_volume"] == 6.0
    assert replay.indicators["ema_fast"] == 101.0 and replay.macro_context["rates"]["value"] == 4.0
    with pytest.raises(TypeError):
        replay.candles[-1]["close"] = 1
    with pytest.raises(TypeError):
        replay.macro_context["rates"]["value"] = 0
    assert capture_market_input(replay, timestamp_convention="bar_open", captured_at=CAPTURED) == capture
    assert json.loads(capture.payload)["source_history"]["historical_universe"] == "UNVERIFIED"


@pytest.mark.parametrize("change", ["candle", "feature", "scope", "capture", "false_provenance", "format"])
def test_changed_input_cannot_reuse_a_capture_identity(change):
    captured = capture_market_input(sample_context(), timestamp_convention="bar_open", captured_at=CAPTURED)
    payload = json.loads(captured.payload)
    if change == "candle":
        payload["context"]["candles"][-1]["close"] = 100
    elif change == "feature":
        payload["context"]["indicators"]["ema_fast"] = 99
    elif change == "scope":
        payload["context"]["asset"] = "ETHUSDT"
    elif change == "capture":
        payload["captured_at"] = (CAPTURED + timedelta(days=1)).isoformat()
    elif change == "false_provenance":
        payload["source_history"]["historical_universe"] = "PASS"
    else:
        payload["format_version"] = True
    with pytest.raises(ValueError):
        restore_market_input(payload, content_hash=captured.content_hash)


@pytest.mark.parametrize("change", ["secret", "nonfinite", "nonjson", "naive", "depth", "count", "bytes"])
def test_capture_rejects_unsafe_or_oversized_inputs_without_truncation(monkeypatch, change):
    context = sample_context()
    instant = CAPTURED
    if change == "secret":
        context.indicators["provider_api_key"] = "dummy-must-not-be-captured"
    elif change == "nonfinite":
        context.indicators["ema_fast"] = float("inf")
    elif change == "nonjson":
        context.indicators["arbitrary"] = object()
    elif change == "naive":
        instant = CAPTURED.replace(tzinfo=None)
    elif change == "depth":
        value = 1
        for _ in range(14):
            value = {"nested": value}
        context = replace(context, macro_context=value)
    elif change == "count":
        monkeypatch.setattr(market_input, "MAX_CANDLES", 20)
    else:
        monkeypatch.setattr(market_input, "MAX_INPUT_BYTES", 100)
    with pytest.raises((ValueError, TypeError)):
        capture_market_input(context, timestamp_convention="bar_open", captured_at=instant)


def test_runtime_components_receive_captured_readonly_values_and_public_diagnostics_omit_payload(monkeypatch):
    monkeypatch.setenv("ADAPTIVE_EVALUATION_TIMEFRAMES", "1h")
    context = sample_context()
    market = {"1h": {"candles": list(context.candles), "indicators": dict(context.indicators), "source": context.provider}}
    service = AdaptiveStrategyService()
    monkeypatch.setattr(service.profile_resolver, "resolve", lambda asset, cls: _profile_from_mapping({}, asset=asset, asset_class=cls))
    observed = []
    def evaluate(value):
        observed.append(value)
        with pytest.raises(TypeError):
            value.candles[-1]["close"] = 500.0
        return []
    service.components = [SimpleNamespace(evaluate=evaluate), SimpleNamespace(evaluate=evaluate)]
    assessment = service.evaluate("BTCUSDT", market, "trend")
    assert len(observed) == 2 and observed[1].candles[-1]["close"] == 101.0
    assert len(assessment.input_snapshots) == 1
    reference = assessment.sequence_references[0]
    assert reference["summary"]["market_input_hash"] == assessment.input_snapshots[0]["content_hash"]
    assert "input_snapshots" not in assessment.to_dict()


def test_main_engine_candidate_selection_preserves_capture_and_reference_binding(monkeypatch):
    from engine.consensus import consensus_filter
    from engine.signal_controller import SignalController
    from engine.core import _collapse_signal_variants
    monkeypatch.setenv("ADAPTIVE_EVALUATION_TIMEFRAMES", "1h")
    monkeypatch.setenv("CONSENSUS_ENABLED", "1")
    monkeypatch.setenv("CONSENSUS_MIN_GROUPS", "1")
    monkeypatch.setenv("CONSENSUS_MIN_TOTAL_WEIGHTED_CONF", "0")
    context = sample_context()
    service = AdaptiveStrategyService()
    service.components = [SimpleNamespace(evaluate=lambda context: [])]
    market = {"1h": {"candles": list(context.candles), "indicators": dict(context.indicators), "source": context.provider}}
    assessment = service.evaluate("BTCUSDT", market, "trend")
    candidate = {"asset": "BTCUSDT", "timeframe": "1h", "direction": "LONG", "entry": 100,
                 "stop_loss": 90, "take_profit": [110], "confidence": 0.9, "score": 90,
                 "strategy_name": "capture-flow", "strategy_group": "trend"}
    attached = service.apply_to_signals([candidate], assessment)
    controller = SignalController()
    selected = _collapse_signal_variants(controller.pick_best_direction_per_pair(
        consensus_filter(controller.normalize_signals(attached), min_score=0.01)))
    assert len(selected) == 1
    digest = selected[0]["adaptive_sequence_refs"][0]["summary"]["market_input_hash"]
    assert digest == selected[0]["_adaptive_input_snapshots"][0]["content_hash"]
    replay = restore_market_input(selected[0]["_adaptive_input_snapshots"][0]["payload"], content_hash=digest)
    assert replay.indicators["ema_fast"] == 101.0
    signal = service.apply_to_signals([{"strategy_group": "trend"}], assessment)[0]
    assert len(signal["_adaptive_input_snapshots"]) == 1
    json.dumps(signal, allow_nan=False)
    market["1h"]["candles"][-1]["close"] = 500.0
    stored = assessment.input_snapshots[0]["payload"]
    assert stored["context"]["candles"][-1]["close"] == 101.0


def test_capture_failure_keeps_explicit_missing_evidence_and_original_component_inputs(monkeypatch):
    monkeypatch.setenv("ADAPTIVE_EVALUATION_TIMEFRAMES", "1h")
    context = sample_context()
    service = AdaptiveStrategyService()
    monkeypatch.setattr(service.profile_resolver, "resolve", lambda asset, cls: _profile_from_mapping({}, asset=asset, asset_class=cls))
    observed = []
    service.components = [SimpleNamespace(evaluate=lambda value: observed.append(value) or [])]
    market = {"1h": {"candles": context.candles, "indicators": {"provider_api_key": "dummy"}}}
    assessment = service.evaluate("BTCUSDT", market, "trend")
    assert len(observed) == 1 and assessment.input_snapshots == ()
    summary = assessment.sequence_references[0]["summary"]
    assert summary["input_capture_status"] == "UNAVAILABLE" and "market_input_hash" not in summary


def test_runtime_rejects_excess_timeframes_before_truncating_capture_coverage(monkeypatch):
    monkeypatch.setenv("ADAPTIVE_EVALUATION_TIMEFRAMES", ",".join(f"{i}m" for i in range(1, 10)))
    service = AdaptiveStrategyService()
    monkeypatch.setattr(service.profile_resolver, "resolve", lambda asset, cls: _profile_from_mapping({}, asset=asset, asset_class=cls))
    with pytest.raises(ValueError, match="timeframe_budget"):
        service.evaluate("BTCUSDT", {}, "trend")


def test_optional_capture_reference_round_trips_without_rewriting_legacy_dataset_identity():
    from tests.test_dataset_snapshot import inputs, CUTOFF
    legacy = inputs()
    old_rows, old_manifest = build_dataset(legacy, as_of=CUTOFF)
    legacy[0]["sequence_provenance"][0]["summary"].update(market_input_hash="f"*64, input_capture_status="CAPTURED")
    rows, manifest = build_dataset(legacy, as_of=CUTOFF)
    assert manifest.content_hash != old_manifest.content_hash
    restored = restore_dataset_snapshot(json.loads(encode_dataset_snapshot(rows, manifest)), observation_cutoff=CUTOFF)
    assert restored == (rows, manifest)
    assert restore_dataset_snapshot(json.loads(encode_dataset_snapshot(old_rows, old_manifest)), observation_cutoff=CUTOFF) == (old_rows, old_manifest)
