from __future__ import annotations

import numpy as np
import pandas as pd

from ml.drift_monitor import detect_feature_drift
from ml.train_model import _feature_distribution_baseline


def test_feature_baseline_is_bounded_and_deterministic():
    frame = pd.DataFrame({
        "a": np.linspace(0.0, 1.0, 1000),
        "b": np.linspace(-2.0, 2.0, 1000),
    })
    one = _feature_distribution_baseline(frame, ["a", "b"], max_points=64)
    two = _feature_distribution_baseline(frame, ["a", "b"], max_points=64)

    assert one == two
    assert set(one) == {"a", "b"}
    assert len(one["a"]) == 64
    assert one["a"][0] == 0.0
    assert one["a"][-1] == 1.0


def test_drift_is_not_actionable_without_live_sample_coverage():
    baseline = {f"f{i}": [float(x) for x in range(100)] for i in range(6)}
    live = {f"f{i}": [1000.0] * 10 for i in range(6)}

    result = detect_feature_drift(
        baseline,
        live,
        psi_threshold=0.25,
        minimum_samples=50,
        minimum_features=5,
    )

    assert result["actionable"] is False
    assert result["drift_detected"] is False
    assert len(result["insufficient_features"]) == 6


def test_persistent_distribution_shift_becomes_actionable():
    baseline = {f"f{i}": [float(x) for x in range(100)] for i in range(6)}
    live = {f"f{i}": [1000.0 + float(x) for x in range(100)] for i in range(6)}

    result = detect_feature_drift(
        baseline,
        live,
        psi_threshold=0.25,
        minimum_samples=50,
        minimum_features=5,
    )

    assert result["actionable"] is True
    assert result["drift_detected"] is True
    assert len(result["drifting_features"]) >= 5


def test_live_sampler_publishes_only_numeric_feature_samples(monkeypatch):
    import ml.live_drift as live_drift

    published = {}
    monkeypatch.setenv("ML_DRIFT_LIVE_PUBLISH_EVERY", "10")
    monkeypatch.setenv("ML_DRIFT_LIVE_PUBLISH_SECONDS", "15")
    monkeypatch.setattr(live_drift.state, "set_sync", lambda key, value, ex=None: published.update({"key": key, "value": value, "ex": ex}))
    with live_drift._LOCK:
        live_drift._SAMPLES.clear()
        live_drift._COUNT = 9
        live_drift._LAST_PUBLISH_MONO = 0.0

    live_drift.record_live_feature_vector({"score": 0.81, "bad": "not-a-number"})

    snapshot = live_drift.snapshot_feature_samples()
    assert snapshot["score"] == [0.81]
    assert "bad" not in snapshot
    assert published["key"] == "signalrankai:ml:live_feature_stats"



def test_prediction_starvation_requires_coverage_and_zero_passes():
    from ml.drift_monitor import detect_prediction_starvation

    samples = [
        {
            "raw_probability": 0.40 + (i % 5) * 0.01,
            "calibrated_probability": 0.41,
            "threshold": 0.63,
            "passed": 0.0,
        }
        for i in range(60)
    ]
    result = detect_prediction_starvation(
        samples,
        minimum_samples=50,
        minimum_pass_rate=0.01,
    )

    assert result["actionable"] is True
    assert result["starvation_detected"] is True
    assert result["pass_rate"] == 0.0
    assert result["raw_max"] < result["threshold_min"]


def test_prediction_starvation_does_not_fire_without_coverage_or_when_model_passes():
    from ml.drift_monitor import detect_prediction_starvation

    tiny = [
        {
            "raw_probability": 0.40,
            "calibrated_probability": 0.41,
            "threshold": 0.63,
            "passed": 0.0,
        }
        for _ in range(10)
    ]
    assert detect_prediction_starvation(tiny, minimum_samples=50)["actionable"] is False
    assert detect_prediction_starvation(tiny, minimum_samples=50)["starvation_detected"] is False

    healthy = [
        {
            "raw_probability": 0.70 if i % 4 == 0 else 0.50,
            "calibrated_probability": 0.66 if i % 4 == 0 else 0.45,
            "threshold": 0.63,
            "passed": 1.0 if i % 4 == 0 else 0.0,
        }
        for i in range(80)
    ]
    result = detect_prediction_starvation(healthy, minimum_samples=50, minimum_pass_rate=0.01)
    assert result["actionable"] is True
    assert result["starvation_detected"] is False
    assert result["pass_rate"] > 0.01


def test_live_prediction_sampler_publishes_bounded_anonymous_output_stats(monkeypatch):
    import json
    import ml.live_drift as live_drift

    published = {}
    monkeypatch.setenv("ML_DRIFT_PREDICTION_PUBLISH_EVERY", "10")
    monkeypatch.setenv("ML_DRIFT_PREDICTION_PUBLISH_SECONDS", "15")
    monkeypatch.setattr(
        live_drift.state,
        "set_sync",
        lambda key, value, ex=None: published.update({"key": key, "value": value, "ex": ex}),
    )
    with live_drift._LOCK:
        live_drift._PREDICTIONS.clear()
        live_drift._PREDICTION_COUNT = 9
        live_drift._LAST_PREDICTION_PUBLISH_MONO = 0.0

    live_drift.record_live_prediction(0.48, 0.41, 0.63)

    snapshot = live_drift.snapshot_prediction_samples()
    assert snapshot == [{
        "raw_probability": 0.48,
        "calibrated_probability": 0.41,
        "threshold": 0.63,
        "passed": 0.0,
    }]
    assert published["key"] == "signalrankai:ml:live_prediction_stats"
    payload = json.loads(published["value"])
    assert payload[0]["raw_probability"] == 0.48
    assert set(payload[0]) == {
        "raw_probability",
        "calibrated_probability",
        "threshold",
        "passed",
    }


def test_ml_inference_records_prediction_telemetry_after_raw_space_threshold_decision():
    from pathlib import Path

    source = Path("ml/inference.py").read_text(encoding="utf-8")
    section = source[source.index("def ml_filter("):]
    assert "record_live_prediction(raw_prob, prob, thresh_val)" in section
    assert section.index("record_live_prediction(raw_prob, prob, thresh_val)") < section.index(
        "approved = self.raw_probability_passes(raw_prob, thresh_val)"
    )


def test_worker_reports_prediction_starvation_without_automatically_relaxing_thresholds():
    from pathlib import Path

    source = Path("worker/worker.py").read_text(encoding="utf-8")
    section = source[source.index("async def _drift_monitor_loop"):]
    assert "detect_prediction_starvation" in section
    assert "[ml_prediction_starvation]" in section
    assert "ML_STARVATION_MIN_LIVE_SAMPLES" in section
    assert "ML_STARVATION_MIN_PASS_RATE" in section
    assert "ML_PROB_THRESHOLD" not in section



def test_analytics_runtime_owns_drift_monitor_when_enabled():
    from pathlib import Path

    source = Path("runtime/analytics.py").read_text(encoding="utf-8")
    assert 'if _enabled("ML_DRIFT_MONITOR_ENABLED", False):' in source
    assert 'name="analytics-ml-drift"' in source
    assert "detect_feature_drift" in source
    assert "detect_prediction_starvation" in source
    assert "load_live_prediction_samples" in source
    assert "[analytics_ml_drift]" in source
    assert "[analytics_ml_prediction_starvation]" in source


def test_prediction_starvation_never_relaxes_certified_threshold_in_analytics_runtime():
    from pathlib import Path

    source = Path("runtime/analytics.py").read_text(encoding="utf-8")
    section = source[source.index("async def _ml_drift_loop"):source.index("async def run_async")]
    assert "ML_STARVATION_RETRAIN_ON_DETECT" in section
    assert '"0.01"' in section
    assert "ML_PROB_THRESHOLD" not in section
    assert "classification_threshold" not in section



def test_analytics_prediction_health_survives_missing_feature_baseline():
    from pathlib import Path

    source = Path("runtime/analytics.py").read_text(encoding="utf-8")
    section = source[
        source.index("async def _ml_drift_loop"):
        source.index("async def run_async")
    ]
    prediction_index = section.index("prediction_result=detect_prediction_starvation")
    feature_index = section.index("baseline=await load_durable_feature_baseline")
    assert prediction_index < feature_index
    assert 'reason": "baseline_or_live_features_unavailable"' in section
    assert 'raise FileNotFoundError' not in section
    assert "signalrankai:ml:starvation:mode" in section


def test_starvation_recovery_is_bounded_and_preserves_certified_cutoff(monkeypatch):
    import engine.core as core

    monkeypatch.setenv("ML_STARVATION_RECOVERY_ENABLED", "1")
    monkeypatch.setenv("ML_STARVATION_RECOVERY_MIN_SCORE", "85")
    monkeypatch.setenv("ML_STARVATION_RECOVERY_MIN_CONFLUENCE", "50")
    monkeypatch.setenv("ML_STARVATION_RECOVERY_RAW_FLOOR", "0.40")
    monkeypatch.setenv("ML_STARVATION_RECOVERY_CHALLENGER_FLOOR", "0.45")
    monkeypatch.setenv("ML_STARVATION_RECOVERY_MAX_SIGNALS_PER_CYCLE", "1")
    monkeypatch.setattr(
        core,
        "_ml_starvation_recovery_context",
        lambda: {
            "actionable": True,
            "starvation_detected": True,
            "samples": 80,
            "pass_rate": 0.0,
            "raw_max": 0.50,
            "threshold_min": 0.629,
        },
    )
    signal = {
        "score": 91.0,
        "confluence_score": 62.0,
    }
    challenger = {
        "available": True,
        "probability": 0.52,
        "threshold": 0.70,
        "passed": False,
        "version": "candidate-test",
    }

    allowed, details = core._ml_starvation_recovery_decision(
        signal,
        raw_probability=0.48,
        certified_threshold=0.629,
        challenger=challenger,
        pipeline_stats={},
    )
    assert allowed is True
    assert details["reason"] == "serving_model_starvation"
    assert details["certified_threshold"] == 0.629

    capped, capped_details = core._ml_starvation_recovery_decision(
        signal,
        raw_probability=0.48,
        certified_threshold=0.629,
        challenger=challenger,
        pipeline_stats={"ml_recovery_passed": 1},
    )
    assert capped is False
    assert capped_details["reason"] == "cycle_cap"


def test_starvation_recovery_rejects_weak_deterministic_or_model_evidence(monkeypatch):
    import engine.core as core

    monkeypatch.setenv("ML_STARVATION_RECOVERY_ENABLED", "1")
    monkeypatch.setattr(
        core,
        "_ml_starvation_recovery_context",
        lambda: {
            "actionable": True,
            "starvation_detected": True,
            "samples": 80,
        },
    )

    weak_score, details = core._ml_starvation_recovery_decision(
        {"score": 70.0, "confluence_score": 70.0},
        raw_probability=0.50,
        certified_threshold=0.629,
        challenger={"available": False},
        pipeline_stats={},
    )
    assert weak_score is False
    assert details["reason"] == "score_below_recovery_floor"

    challenger_disagrees, details = core._ml_starvation_recovery_decision(
        {"score": 92.0, "confluence_score": 65.0},
        raw_probability=0.50,
        certified_threshold=0.629,
        challenger={
            "available": True,
            "probability": 0.20,
            "threshold": 0.70,
            "passed": False,
        },
        pipeline_stats={},
    )
    assert challenger_disagrees is False
    assert details["reason"] == "challenger_disagrees"


def test_starvation_recovery_never_rewrites_ml_probability_threshold():
    from pathlib import Path

    source = Path("engine/core.py").read_text(encoding="utf-8")
    section = source[
        source.index("def _ml_starvation_recovery_context"):
        source.index("def load_tradable_assets")
    ]
    assert "ML_PROB_THRESHOLD" not in section
    assert "ML_STARVATION_RECOVERY_RAW_FLOOR" in section
    assert "ML_STARVATION_RECOVERY_MAX_SIGNALS_PER_CYCLE" in section


def test_challenger_scoring_restores_durable_candidate_without_promotion():
    from pathlib import Path

    source = Path("engine/ml.py").read_text(encoding="utf-8")
    assert "def score_shadow_signal(" in source
    assert 'model_name="candidate"' in source
    scorer = source[
        source.index("def score_shadow_signal("):
        source.index("def _persist_shadow_prediction")
    ]
    assert "booster.predict" in scorer
    assert '"passed": probability >= threshold' in scorer
    assert "persist_active_model_artifact" not in scorer
