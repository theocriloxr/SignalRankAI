from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy.dialects import postgresql

from ml.train_model import _class_balance_scale, _promotion_quality_gate, _select_classification_threshold
from services.outcome_reconciliation import build_outcome_reconciliation_query


ROOT = Path(__file__).resolve().parents[1]


def test_outcome_reconciliation_query_is_valid_grouped_postgres_sql() -> None:
    query = build_outcome_reconciliation_query(
        cutoff=datetime(2026, 7, 1),
        limit=5000,
    )
    sql = str(
        query.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).upper()
    assert "DISTINCT ON" not in sql
    assert "GROUP BY SIGNAL_DELIVERIES.SIGNAL_ID" in sql
    assert "MIN(COALESCE(" in sql
    assert "PROOF_DELIVERY_CANDIDATES.FIRST_PROOF_TIME ASC" in sql


def test_deployed_ml_quality_gate_rejects_logged_weak_model(monkeypatch) -> None:
    monkeypatch.delenv("ML_MIN_PROMOTION_AUC", raising=False)
    monkeypatch.delenv("ML_MIN_PROMOTION_ACCURACY", raising=False)
    accepted, min_accuracy, min_auc = _promotion_quality_gate(
        {"accuracy": 0.50, "auc": 0.575},
        deployed_runtime=True,
    )
    assert accepted is False
    assert min_accuracy == 0.55
    assert min_auc == 0.60


def test_deployed_ml_quality_gate_accepts_only_candidate_above_threshold(monkeypatch) -> None:
    monkeypatch.delenv("ML_MIN_PROMOTION_AUC", raising=False)
    monkeypatch.delenv("ML_MIN_PROMOTION_ACCURACY", raising=False)
    accepted, _, _ = _promotion_quality_gate(
        {
            "accuracy": 0.66,
            "auc": 0.68,
            "majority_baseline_accuracy": 0.58,
            "balanced_accuracy": 0.63,
            "positive_recall": 0.42,
            "pr_auc": 0.48,
            "expected_r": 0.18,
        },
        deployed_runtime=True,
    )
    assert accepted is True


def test_ml_promotion_requires_calibration_in_deployed_runtime() -> None:
    source = (ROOT / "ml" / "train_model.py").read_text(encoding="utf-8")
    assert '"ML_PROMOTION_REQUIRES_VALID_CALIBRATION"' in source
    assert "status=candidate_only reason=calibration_unvalidated" in source
    assert "primary_model_preserved=true" in source


def test_outcome_notification_budget_starts_after_database_snapshot() -> None:
    source = (ROOT / "signalrank_telegram" / "bot.py").read_text(encoding="utf-8")
    pending_pos = source.index("pending = run_sync(_fetch())")
    deadline_pos = source.index(
        "_outcome_deadline = time.monotonic() + _outcome_budget_seconds",
        pending_pos,
    )
    assert deadline_pos > pending_pos
    assert 'OUTCOME_NOTIFICATION_FETCH_MARKET_PRICE_FALLBACK", False' in source
    assert 'OUTCOME_NOTIFICATION_PRICE_TIMEOUT_SECONDS", "3"' in source


def test_deployed_ml_quality_gate_accepts_imbalanced_candidate_that_beats_utility_gates(monkeypatch) -> None:
    for name in (
        "ML_MIN_PROMOTION_AUC",
        "ML_MIN_PROMOTION_ACCURACY",
        "ML_MIN_BALANCED_ACCURACY",
        "ML_MIN_POSITIVE_RECALL",
        "ML_MIN_PR_AUC",
        "ML_MIN_EXPECTED_R",
    ):
        monkeypatch.delenv(name, raising=False)

    accepted, _, _ = _promotion_quality_gate(
        {
            "accuracy": 0.7616,
            "auc": 0.7665,
            "majority_baseline_accuracy": 0.7634,
            "balanced_accuracy": 0.5956,
            "positive_recall": 0.2803,
            "pr_auc": 0.4465,
            "expected_r": 0.48,
        },
        deployed_runtime=True,
    )
    assert accepted is True


def test_deployed_ml_quality_gate_still_rejects_majority_collapse(monkeypatch) -> None:
    for name in (
        "ML_MIN_PROMOTION_AUC",
        "ML_MIN_PROMOTION_ACCURACY",
        "ML_MIN_BALANCED_ACCURACY",
        "ML_MIN_POSITIVE_RECALL",
        "ML_MIN_PR_AUC",
        "ML_MIN_EXPECTED_R",
    ):
        monkeypatch.delenv(name, raising=False)

    accepted, _, _ = _promotion_quality_gate(
        {
            "accuracy": 0.82,
            "auc": 0.55,
            "majority_baseline_accuracy": 0.82,
            "balanced_accuracy": 0.50,
            "positive_recall": 0.0,
            "pr_auc": 0.18,
            "expected_r": -0.12,
        },
        deployed_runtime=True,
    )
    assert accepted is False


def test_class_balance_scale_is_bounded_for_minority_positive_class(monkeypatch) -> None:
    monkeypatch.delenv("ML_CLASS_BALANCE_ENABLED", raising=False)
    monkeypatch.delenv("ML_CLASS_BALANCE_MIN_SCALE", raising=False)
    monkeypatch.delenv("ML_CLASS_BALANCE_MAX_SCALE", raising=False)
    y = np.asarray([0] * 90 + [1] * 10, dtype=int)
    scale = _class_balance_scale(y)
    assert 1.0 < scale <= 4.0
    assert scale == pytest.approx(3.0)


def test_classification_threshold_is_selected_on_imbalanced_calibration_window(monkeypatch) -> None:
    monkeypatch.delenv("ML_CLASSIFICATION_THRESHOLD_TUNING_ENABLED", raising=False)
    monkeypatch.delenv("ML_CLASSIFICATION_THRESHOLD_MIN", raising=False)
    monkeypatch.delenv("ML_CLASSIFICATION_THRESHOLD_MAX", raising=False)

    y = np.asarray([0] * 80 + [1] * 20, dtype=int)
    probabilities = np.asarray([0.05] * 60 + [0.25] * 20 + [0.35] * 20, dtype=float)
    threshold = _select_classification_threshold(y, probabilities)

    fixed_pred = (probabilities >= 0.5).astype(int)
    tuned_pred = (probabilities >= threshold).astype(int)
    fixed_recall = ((fixed_pred == 1) & (y == 1)).sum() / max(1, (y == 1).sum())
    tuned_recall = ((tuned_pred == 1) & (y == 1)).sum() / max(1, (y == 1).sum())

    assert 0.15 <= threshold < 0.5
    assert tuned_recall > fixed_recall
    assert tuned_recall == pytest.approx(1.0)


def test_training_uses_fit_window_balance_and_calibration_threshold_only() -> None:
    source = (ROOT / "ml" / "train_model.py").read_text(encoding="utf-8")
    assert "class_balance_scale = _class_balance_scale(y_tr, w_tr)" in source
    assert "scale_pos_weight=class_balance_scale" in source
    assert "classification_threshold = _select_classification_threshold(y_cal, calibration_fit_proba)" in source
    assert "y_pred = (np.asarray(y_proba, dtype=float) >= classification_threshold).astype(int)" in source
    assert "decision_threshold=classification_threshold" in source
    assert '"classification_threshold": float(classification_threshold)' in source
    assert '"scale_pos_weight": float(class_balance_scale)' in source


def test_temporal_split_reserves_production_validation_floor_when_capacity_allows() -> None:
    from ml.train_model import _temporal_three_way_indices

    train, calibration, validation = _temporal_three_way_indices(
        290,
        ordered_indices=list(range(290)),
        train_ratio=0.70,
        calibration_ratio=0.15,
        minimum_train_rows=50,
        minimum_calibration_rows=30,
        minimum_validation_rows=100,
    )
    assert len(validation) == 100
    assert len(calibration) >= 30
    assert len(train) >= 50
    assert len(train) + len(calibration) + len(validation) == 290
    assert set(train).isdisjoint(calibration)
    assert set(train).isdisjoint(validation)
    assert set(calibration).isdisjoint(validation)
    assert max(train) < min(calibration) < min(validation)


def test_training_passes_calibration_evidence_floors_into_temporal_split() -> None:
    source = (ROOT / "ml" / "train_model.py").read_text(encoding="utf-8")
    assert 'ML_MIN_CALIBRATION_VALIDATION_ROWS' in source
    assert 'ML_MIN_CALIBRATION_FIT_ROWS' in source
    assert 'ML_MIN_MODEL_FIT_ROWS' in source
    assert 'minimum_validation_rows=calibration_min_rows' in source
    assert 'minimum_calibration_rows=minimum_calibration_fit_rows' in source
    assert 'minimum_train_rows=minimum_model_fit_rows' in source
    assert '[ml_temporal_split]' in source
