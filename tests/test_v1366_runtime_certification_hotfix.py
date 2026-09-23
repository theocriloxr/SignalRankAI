from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy.dialects import postgresql

from ml.train_model import _promotion_quality_gate
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
            "positive_precision": 0.44,
            "positive_rate": 0.30,
            "pr_auc": 0.48,
            "expected_r": 0.18,
        },
        deployed_runtime=True,
    )
    assert accepted is True


def test_deployed_ml_quality_gate_accepts_imbalanced_useful_model_below_majority_accuracy(monkeypatch) -> None:
    monkeypatch.delenv("ML_MIN_PROMOTION_AUC", raising=False)
    monkeypatch.delenv("ML_MIN_PROMOTION_ACCURACY", raising=False)
    monkeypatch.delenv("ML_MIN_POSITIVE_PRECISION", raising=False)
    monkeypatch.delenv("ML_MIN_POSITIVE_PRECISION_LIFT", raising=False)
    accepted, _, _ = _promotion_quality_gate(
        {
            "accuracy": 0.71,
            "auc": 0.76,
            "majority_baseline_accuracy": 0.76,
            "balanced_accuracy": 0.61,
            "positive_recall": 0.36,
            "positive_precision": 0.34,
            "positive_rate": 0.24,
            "pr_auc": 0.46,
            "expected_r": 0.17,
        },
        deployed_runtime=True,
    )
    assert accepted is True


def test_deployed_ml_quality_gate_still_rejects_majority_only_model(monkeypatch) -> None:
    monkeypatch.delenv("ML_MIN_PROMOTION_AUC", raising=False)
    monkeypatch.delenv("ML_MIN_PROMOTION_ACCURACY", raising=False)
    accepted, _, _ = _promotion_quality_gate(
        {
            "accuracy": 0.80,
            "auc": 0.61,
            "majority_baseline_accuracy": 0.80,
            "balanced_accuracy": 0.50,
            "positive_recall": 0.0,
            "positive_precision": 0.0,
            "positive_rate": 0.20,
            "pr_auc": 0.36,
            "expected_r": 0.10,
        },
        deployed_runtime=True,
    )
    assert accepted is False


def test_ml_class_balance_weight_is_training_only_and_bounded() -> None:
    source = (ROOT / "ml" / "train_model.py").read_text(encoding="utf-8")
    train_block = source[source.index("# Train model"):source.index("# Evaluate")]
    assert "train_positive" in train_block
    assert "train_negative" in train_block
    assert "math.sqrt(max(1.0, empirical_ratio))" in train_block
    assert '"ML_SCALE_POS_WEIGHT_MAX", "4.0"' in train_block
    assert "scale_pos_weight=scale_pos_weight" in train_block
    assert "y_te" not in train_block


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
