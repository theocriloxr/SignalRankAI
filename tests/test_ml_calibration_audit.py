from pathlib import Path

import numpy as np

from ml.train_model import _fit_selected_calibration_curve, _select_probability_calibrator
from scripts.ml_calibration_audit import ML_PAST_SQL, REJECTED_SQL, PAPER_SQL, UNIQUE_IDS_SQL


def test_calibration_audit_queries_are_quoted_and_read_only() -> None:
    source = Path("scripts/ml_calibration_audit.py").read_text(encoding="utf-8")
    assert 'SET TRANSACTION READ ONLY' in source
    assert "await session.rollback()" in source
    assert "session.commit" not in source
    assert "COALESCE(outcome_status, '')" in str(ML_PAST_SQL)
    assert "COALESCE(actual_outcome, '')" in str(REJECTED_SQL)
    assert "COALESCE(actual_outcome, '')" in str(UNIQUE_IDS_SQL)
    assert "FROM paper_positions" in str(PAPER_SQL)
    assert "COALESCE(outcome_status,)" not in source
    assert "WHEOERE" not in source


def test_calibration_audit_uses_bounded_parameterized_lookback() -> None:
    source = Path("scripts/ml_calibration_audit.py").read_text(encoding="utf-8")
    assert "make_interval(days => :days)" in source
    assert "days = max(1, min(3650, int(days)))" in source
    assert 'priority="analytics"' in source
    assert 'drop_if_busy=False' in source



def test_calibrator_selection_is_nested_inside_calibration_window() -> None:
    source = Path("ml/train_model.py").read_text(encoding="utf-8")
    call = """_select_probability_calibrator(
                calibration_fit_proba,
                y_cal,
            )"""
    assert call in source
    assert "_select_probability_calibrator(y_proba" not in source
    assert "_select_probability_calibrator(y_te" not in source
    assert "[ml_calibration_selector]" in source


def test_selected_calibration_curves_are_monotonic_and_servable() -> None:
    probs = np.linspace(0.03, 0.97, 240)
    labels = (np.arange(240) % 5 < np.maximum(1, np.floor(probs * 5)).astype(int)).astype(int)
    kind, evidence = _select_probability_calibrator(probs, labels)
    assert kind in {"isotonic", "platt"}
    assert evidence["selection_rows"] > 0

    xs, ys = _fit_selected_calibration_curve(kind, probs, labels)
    assert len(xs) >= 2
    assert len(xs) == len(ys)
    assert all(float(a) <= float(b) for a, b in zip(xs, xs[1:]))
    assert all(float(a) <= float(b) + 1e-12 for a, b in zip(ys, ys[1:]))
    assert all(0.0 <= float(y) <= 1.0 for y in ys)


def test_platt_curve_uses_existing_interpolation_contract() -> None:
    probs = np.linspace(0.05, 0.95, 200)
    labels = (probs >= 0.58).astype(int)
    xs, ys = _fit_selected_calibration_curve("platt", probs, labels)
    assert len(xs) == 257
    assert xs[0] == 0.0
    assert xs[-1] == 1.0
    assert ys[0] < ys[-1]
