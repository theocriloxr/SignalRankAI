from engine.core import _signal_display_score
from engine.signal_metrics import resolve_score_percent
from engine.scoring import score_signal
from signalrank_telegram.bot import _delivery_score


def _high_raw_score_signal():
    return {
        "asset": "BTCUSDT",
        "direction": "long",
        "entry": 100.0,
        "stop_loss": 95.0,
        "take_profit": 118.0,
        "confidence": 0.98,
        "confluence": 100.0,
        "volatility": 0.04,
        "regime_fit": 1.0,
        "ml_probability": 0.95,
    }


def test_score_signal_uses_normalized_components_without_multiplier_inflation(monkeypatch):
    monkeypatch.delenv("SCORE_SOFT_CAP_ENABLED", raising=False)
    signal = _high_raw_score_signal()

    score = score_signal(signal)

    assert 90.0 < score < 100.0
    assert signal["score_raw"] <= 100.0
    assert round(signal["score_calibrated"], 2) == score
    assert signal["score_calibration_method"] == "heuristic_weighted_v2"
    assert "rr" in signal["score_components"]
    assert "ml_probability" in signal["score_components"]
    assert "regime_fit" in signal["score_components"]


def test_candle_evidence_is_an_auditable_score_component(monkeypatch):
    monkeypatch.setenv("SCORE_WEIGHT_CANDLE_EVIDENCE", "0.10")
    signal = _high_raw_score_signal()
    signal.update({
        "candle_evidence_score": 80.0,
        "candle_evidence_alignment": "supportive",
        "candle_confirmation": "confirmed",
    })

    score_signal(signal)

    assert signal["score_components"]["candle_evidence"]["value"] == 0.8
    assert signal["score_components"]["candle_evidence"]["weight"] == 0.1


def test_optional_candle_gate_rejects_invalidated_evidence(monkeypatch):
    monkeypatch.setenv("CANDLE_EVIDENCE_HARD_GATE_ENABLED", "true")
    signal = _high_raw_score_signal()
    signal.update({
        "candle_evidence_score": 90.0,
        "candle_evidence_alignment": "conflicting",
        "candle_confirmation": "invalidated",
    })

    assert score_signal(signal) == 0.0


def test_signal_display_score_prefers_calibrated_primary_score():
    signal = {
        "score": 96.25,
        "score_composite": 100.0,
        "quality_score": 100.0,
        "rank_score": 99.8,
    }

    assert _signal_display_score(signal) == 96.25
    assert _delivery_score(signal) == 96.25


def test_signal_display_score_falls_back_when_primary_missing():
    signal = {
        "score_composite": 97.4,
        "quality_score": 98.2,
    }

    assert _signal_display_score(signal) == 98.2
    assert _delivery_score(signal) == 98.2


def test_resolve_score_percent_prefers_calibrated_and_avoids_exact_100(monkeypatch):
    monkeypatch.delenv("SCORE_DISPLAY_MAX", raising=False)

    assert resolve_score_percent({"score": 100.0}) == 99.5
    assert resolve_score_percent({"score": 100.0, "score_calibrated": 98.7}) == 98.7


def test_engine_cycle_log_reports_display_and_raw_scores():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "engine" / "core.py").read_text(encoding="utf-8")

    assert "max_score_raw=" in source
    assert "max_score_raw_pre_threshold=" in source
    assert "_diagnostic_score(max_candidate_score)" in source
