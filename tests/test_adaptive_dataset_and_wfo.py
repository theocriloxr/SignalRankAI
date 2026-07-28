from datetime import datetime, timedelta

from engine.adaptive.dataset import build_dataset
from engine.adaptive.promotion import evaluate_profile_promotion
from engine.adaptive.walk_forward import walk_forward_evaluate


def _rows(count: int = 160):
    start = datetime(2026, 1, 1)
    rows = []
    for index in range(count):
        rows.append(
            {
                "signal_id": f"s-{index:04d}",
                "decision_time": start + timedelta(hours=index),
                "asset": "BTCUSDT",
                "asset_class": "crypto",
                "timeframe": "1h",
                "family": "trend" if index % 2 else "price_action",
                "regime": "trending",
                "direction": "LONG",
                "r_multiple": 0.35 if index % 5 else -0.55,
                "status": "shadow",
                "sequence_hashes": [f"h-{index:04d}"],
                "data_quality_score": 0.95,
            }
        )
    return rows


def test_dataset_manifest_is_chronological_and_reproducible():
    rows = list(reversed(_rows(20)))
    dataset_a, manifest_a = build_dataset(rows)
    dataset_b, manifest_b = build_dataset(list(rows))
    assert dataset_a[0].decision_time < dataset_a[-1].decision_time
    assert manifest_a.dataset_version == manifest_b.dataset_version
    assert manifest_a.sequence_coverage == 1.0
    assert manifest_a.evidence_categories == ("shadow",)


def test_walk_forward_uses_only_earlier_training_rows():
    dataset, _ = build_dataset(_rows())
    result = walk_forward_evaluate(
        dataset,
        family_weights={"trend": 1.05, "price_action": 1.02},
        regime_weights={"trending": 1.01},
        minimum_train=80,
        validation_size=20,
        embargo_seconds=3600,
        cost_r=0.01,
    )
    assert result.fold_count >= 3
    assert result.leakage_checks_passed
    for fold in result.folds:
        assert fold.train_end < fold.validation_start


def test_promotion_requires_next_state_transition():
    metrics = {
        "sample_size": 300,
        "positive_wfo_folds": 4,
        "expectancy_r": 0.2,
        "profit_factor": 1.4,
        "max_drawdown_r": 4,
        "brier_score": 0.15,
        "leakage_checks_passed": True,
    }
    blocked = evaluate_profile_promotion(
        metrics,
        human_approved=True,
        current_state="SHADOW",
        target_state="CANARY",
    )
    allowed = evaluate_profile_promotion(
        metrics,
        human_approved=True,
        current_state="SHADOW",
        target_state="FORWARD_TEST",
    )
    assert not blocked.eligible
    assert "invalid_transition:SHADOW->CANARY" in blocked.reasons
    assert allowed.eligible


def test_future_rows_do_not_change_first_fold_training_weights():
    base_rows = _rows()
    dataset_a, _ = build_dataset(base_rows)
    changed = [dict(row) for row in base_rows]
    for row in changed[120:]:
        row["r_multiple"] = 9.0
        row["family"] = "future_only_family"
    dataset_b, _ = build_dataset(changed)
    result_a = walk_forward_evaluate(
        dataset_a,
        family_weights={},
        regime_weights={},
        minimum_train=80,
        validation_size=20,
        embargo_seconds=3600,
        cost_r=0.01,
    )
    result_b = walk_forward_evaluate(
        dataset_b,
        family_weights={},
        regime_weights={},
        minimum_train=80,
        validation_size=20,
        embargo_seconds=3600,
        cost_r=0.01,
    )
    assert result_a.folds[0] == result_b.folds[0]
