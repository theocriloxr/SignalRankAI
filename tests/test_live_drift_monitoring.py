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
