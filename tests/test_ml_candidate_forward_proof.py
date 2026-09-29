from types import SimpleNamespace

from ml.candidate_forward import _decision_stats, _outcome_class
from engine.ml import _candidate_forward_observation_key


def test_candidate_outcome_normalization_excludes_ambiguous_results():
    assert _outcome_class("tp3") == "win"
    assert _outcome_class("tp1") == "win"
    assert _outcome_class("sl") == "loss"
    assert _outcome_class("ambiguous") is None
    assert _outcome_class("no_hit") is None


def test_candidate_forward_decision_stats_use_realized_r():
    rows = [
        (
            SimpleNamespace(entry=100.0, stop_loss=95.0, take_profit="110.0"),
            {"candidate_passed": True},
            "win",
        ),
        (
            SimpleNamespace(entry=100.0, stop_loss=95.0, take_profit="110.0"),
            {"candidate_passed": True},
            "loss",
        ),
        (
            SimpleNamespace(entry=100.0, stop_loss=95.0, take_profit="110.0"),
            {"candidate_passed": False},
            "win",
        ),
    ]
    stats = _decision_stats(rows, "candidate_passed")
    assert stats["resolved"] == 2
    assert stats["wins"] == 1
    assert stats["losses"] == 1
    assert stats["win_rate"] == 0.5
    assert stats["expected_r"] == 0.5
    assert stats["profit_factor"] == 2.0


def test_candidate_observation_key_is_stable_and_artifact_scoped():
    signal = {
        "asset": "EURUSD",
        "timeframe": "15m",
        "direction": "long",
        "entry": 1.18,
        "stop_loss": 1.17,
        "take_profit": 1.20,
        "candle_timestamp": "2026-09-29T19:00:00+00:00",
        "fingerprint": "abc123",
    }
    first = _candidate_forward_observation_key(
        signal, {"artifact_hash_sha256": "candidate-a"}
    )
    again = _candidate_forward_observation_key(
        dict(signal), {"artifact_hash_sha256": "candidate-a"}
    )
    other = _candidate_forward_observation_key(
        signal, {"artifact_hash_sha256": "candidate-b"}
    )
    assert first == again
    assert first != other


def test_candidate_forward_proof_is_evaluation_only_and_candidate_first():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    trainer = (root / "ml" / "train_model.py").read_text(encoding="utf-8")
    engine_ml = (root / "engine" / "ml.py").read_text(encoding="utf-8")
    core = (root / "engine" / "core.py").read_text(encoding="utf-8")

    assert 'ML_PRODUCTION_CANDIDATE_FIRST", True' in trainer
    assert "reason=production_candidate_first" in trainer
    assert '== "candidate_shadow"' in trainer
    assert '"rejection_type": "candidate_shadow"' in engine_ml
    assert "candidate_observation_key" in engine_ml
    assert "candidate_artifact_hash_sha256" in engine_ml
    assert "champion_probability=(" in core
    assert "champion_threshold=float(threshold)" in core
    assert "champion_passed=bool(approved)" in core
