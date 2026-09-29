from __future__ import annotations

import json

from ml.train_model import _champion_comparison_gate, _schema_promotion_gate


def _metrics(*, auc=0.75, pr_auc=0.68, balanced_accuracy=0.66, expected_r=0.8, ece=0.08, brier=0.18):
    return {
        "auc": auc,
        "pr_auc": pr_auc,
        "balanced_accuracy": balanced_accuracy,
        "expected_r": expected_r,
        "calibration": {
            "calibrated_ece": ece,
            "calibrated_brier": brier,
            "validated": True,
        },
    }


def _write_champion(path, metrics):
    path.write_text(json.dumps({"metrics": metrics}), encoding="utf-8")


def test_material_auc_regression_remains_challenger(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_CHAMPION_COMPARISON_ENABLED", "1")
    primary = tmp_path / "model.json"
    _write_champion(primary, _metrics(auc=0.75))

    ok, evidence = _champion_comparison_gate(
        _metrics(auc=0.731),
        primary,
        deployed_runtime=True,
    )

    assert ok is False
    assert evidence["reason"] == "material_regression"
    assert "auc" in evidence["regressions"]


def test_noninferior_candidate_can_replace_champion(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_CHAMPION_COMPARISON_ENABLED", "1")
    primary = tmp_path / "model.json"
    _write_champion(primary, _metrics())

    ok, evidence = _champion_comparison_gate(
        _metrics(auc=0.755, pr_auc=0.69, balanced_accuracy=0.665, expected_r=0.82, ece=0.079, brier=0.179),
        primary,
        deployed_runtime=True,
    )

    assert ok is True
    assert evidence["reason"] == "noninferior"
    assert not evidence["regressions"]


def test_first_champion_is_allowed_when_no_primary_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_CHAMPION_COMPARISON_ENABLED", "1")

    ok, evidence = _champion_comparison_gate(
        _metrics(),
        tmp_path / "missing.json",
        deployed_runtime=True,
    )

    assert ok is True
    assert evidence["reason"] == "no_existing_champion"


def test_calibration_regression_keeps_candidate_in_shadow(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_CHAMPION_COMPARISON_ENABLED", "1")
    primary = tmp_path / "model.json"
    _write_champion(primary, _metrics(ece=0.06, brier=0.17))

    ok, evidence = _champion_comparison_gate(
        _metrics(ece=0.095, brier=0.17),
        primary,
        deployed_runtime=True,
    )

    assert ok is False
    assert "calibrated_ece" in evidence["regressions"]


def test_durable_champion_metrics_override_stale_local_primary(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_CHAMPION_COMPARISON_ENABLED", "1")
    primary = tmp_path / "model.json"
    _write_champion(primary, _metrics(auc=0.60, pr_auc=0.50, balanced_accuracy=0.55, expected_r=0.10))

    ok, evidence = _champion_comparison_gate(
        _metrics(auc=0.731, pr_auc=0.675, balanced_accuracy=0.654, expected_r=0.74),
        primary,
        deployed_runtime=True,
        champion_metrics=_metrics(auc=0.75, pr_auc=0.70, balanced_accuracy=0.67, expected_r=0.85),
    )

    assert ok is False
    assert evidence["source"] == "durable_registry"
    assert "auc" in evidence["regressions"]

def test_same_schema_can_continue_through_promotion_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_SCHEMA_PROMOTION_REQUIRES_AUTHORIZATION", "1")
    primary = tmp_path / "model.json"
    primary.write_text(json.dumps({"schema_version": 3}), encoding="utf-8")

    ok, evidence = _schema_promotion_gate(
        3,
        primary,
        deployed_runtime=True,
    )

    assert ok is True
    assert evidence["reason"] == "same_schema"


def test_schema_migration_is_candidate_only_without_explicit_certification(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_SCHEMA_PROMOTION_REQUIRES_AUTHORIZATION", "1")
    monkeypatch.delenv("ML_ALLOW_SCHEMA_VERSION_PROMOTION", raising=False)
    monkeypatch.delenv("ML_SCHEMA_PROMOTION_CERTIFICATION_ID", raising=False)
    primary = tmp_path / "model.json"
    primary.write_text(json.dumps({"schema_version": 3}), encoding="utf-8")

    ok, evidence = _schema_promotion_gate(
        4,
        primary,
        deployed_runtime=True,
    )

    assert ok is False
    assert evidence["reason"] == "schema_migration_requires_authorization"
    assert evidence["candidate_schema_version"] == 4
    assert evidence["champion_schema_version"] == 3


def test_schema_migration_needs_both_authorization_and_certification(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_SCHEMA_PROMOTION_REQUIRES_AUTHORIZATION", "1")
    monkeypatch.setenv("ML_ALLOW_SCHEMA_VERSION_PROMOTION", "1")
    monkeypatch.delenv("ML_SCHEMA_PROMOTION_CERTIFICATION_ID", raising=False)
    primary = tmp_path / "model.json"
    primary.write_text(json.dumps({"schema_version": 3}), encoding="utf-8")

    blocked, blocked_evidence = _schema_promotion_gate(
        4,
        primary,
        deployed_runtime=True,
    )
    assert blocked is False
    assert blocked_evidence["certification_present"] is False

    monkeypatch.setenv(
        "ML_SCHEMA_PROMOTION_CERTIFICATION_ID",
        "schema-v4-forward-proof-001",
    )
    allowed, evidence = _schema_promotion_gate(
        4,
        primary,
        deployed_runtime=True,
    )
    assert allowed is True
    assert evidence["reason"] == "schema_migration_certified"
    assert evidence["certification_id"] == "schema-v4-forward-proof-001"


def test_durable_champion_schema_takes_precedence_over_local_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_SCHEMA_PROMOTION_REQUIRES_AUTHORIZATION", "1")
    primary = tmp_path / "model.json"
    primary.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")

    ok, evidence = _schema_promotion_gate(
        3,
        primary,
        deployed_runtime=True,
        champion_schema_version=3,
    )

    assert ok is True
    assert evidence["reason"] == "same_schema"
    assert evidence["source"] == "durable_registry"

