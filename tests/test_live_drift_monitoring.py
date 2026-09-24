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
