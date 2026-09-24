from __future__ import annotations

import numpy as np

from ml import inference


class _FakeModel:
    def __init__(self, probability: float):
        self.probability = probability

    def predict(self, _dmatrix):
        return np.asarray([self.probability], dtype=float)


def _filter(raw_probability: float) -> inference.MLFilter:
    filt = inference.MLFilter.__new__(inference.MLFilter)
    filt.active = True
    filt.model = _FakeModel(raw_probability)
    filt.feature_cols = ["score"]
    filt.schema_version = 1
    filt.model_format_version = 1
    filt.feature_encoding_version = ""
    filt.calibration_kind = "isotonic"
    filt.calibration_x = [0.0, 0.86, 1.0]
    filt.calibration_y = [0.0, 0.70, 1.0]
    filt.metrics = {"classification_threshold": 0.83}
    filt.classification_threshold = 0.83
    filt.last_raw_probability = None
    return filt


def test_ml_decision_uses_raw_probability_threshold_but_returns_calibrated_confidence(monkeypatch):
    filt = _filter(0.86)
    monkeypatch.setattr(inference.xgb, "DMatrix", lambda *args, **kwargs: object())

    approved, confidence = filt.ml_filter({"score": 82.0}, threshold=0.85)

    assert approved is True
    assert abs(float(confidence) - 0.70) < 1e-6
    assert abs(float(filt.last_raw_probability) - 0.86) < 1e-6


def test_ml_rejects_when_raw_probability_misses_raw_cutoff(monkeypatch):
    filt = _filter(0.82)
    monkeypatch.setattr(inference.xgb, "DMatrix", lambda *args, **kwargs: object())

    approved, confidence = filt.ml_filter({"score": 82.0}, threshold=0.85)

    assert approved is False
    assert confidence is not None
    assert abs(float(filt.last_raw_probability) - 0.82) < 1e-6


def test_model_certified_raw_threshold_is_available_for_runtime_governance():
    filt = _filter(0.90)
    assert filt.recommended_raw_threshold() == 0.83


def test_certified_threshold_is_authoritative_by_default(monkeypatch):
    from engine import core

    class _Optimizer:
        def get_threshold(self):
            return 0.99

    filt = _filter(0.90)
    monkeypatch.setattr(core, "_threshold_optimizer", _Optimizer())
    monkeypatch.delenv("ML_ALLOW_ADAPTIVE_THRESHOLD_AROUND_CERTIFIED", raising=False)

    assert abs(core._current_ml_prob_threshold(filt) - 0.83) < 1e-9


def test_adaptive_threshold_can_be_explicitly_bounded_around_certified_model(monkeypatch):
    from engine import core

    class _Optimizer:
        def get_threshold(self):
            return 0.99

    filt = _filter(0.90)
    monkeypatch.setattr(core, "_threshold_optimizer", _Optimizer())
    monkeypatch.setenv("ML_ALLOW_ADAPTIVE_THRESHOLD_AROUND_CERTIFIED", "1")
    monkeypatch.setenv("ML_ADAPTIVE_THRESHOLD_MAX_DELTA", "0.08")

    assert abs(core._current_ml_prob_threshold(filt) - 0.91) < 1e-9
