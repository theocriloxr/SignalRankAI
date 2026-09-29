from pathlib import Path
from types import SimpleNamespace

import pytest

from ml.candidate_forward import _decision_stats, _outcome_class
from engine.ml import _candidate_forward_observation_key
from ml.train_model import _govern_training_source_influence


def _eligible_candidate(*, artifact="cand", parent="champ", schema=4):
    return {
        "artifact_hash_sha256": artifact,
        "schema_version": schema,
        "metrics": {
            "calibration": {"validated": True},
        },
        "payload": {
            "parent_model_hash_sha256": parent,
            "training_meta": {
                "offline_quality_gate": {"passed": True},
                "lineage": {"eligible": True},
                "candidate_forward_gate": {"required": True},
            },
        },
    }


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


def test_shadow_rejected_effective_weight_is_bounded_by_proof(monkeypatch):
    import pandas as pd

    monkeypatch.setenv("ML_MAX_SHADOW_REJECTED_EFFECTIVE_RATIO", "2")
    monkeypatch.setenv("ML_SHADOW_INFLUENCE_MIN_PROOF_ANCHOR", "1")
    frame = pd.DataFrame(
        [
            *[
                {
                    "source_type": "live_delivery",
                    "sample_weight": 1.0,
                }
                for _ in range(10)
            ],
            *[
                {
                    "source_type": "shadow_rejected",
                    "sample_weight": 0.6,
                }
                for _ in range(100)
            ],
        ]
    )

    governed, evidence = _govern_training_source_influence(frame)

    shadow_after = governed.loc[
        governed["source_type"] == "shadow_rejected",
        "sample_weight",
    ].sum()
    assert evidence["applied"] is True
    assert evidence["proof_effective_weight"] == 10.0
    assert abs(float(shadow_after) - 20.0) < 1e-6
    assert evidence["shadow_effective_weight_after"] == 20.0
    assert evidence["shadow_weight_scale"] < 1.0


def test_shadow_influence_governance_preserves_all_rows(monkeypatch):
    import pandas as pd

    monkeypatch.setenv("ML_MAX_SHADOW_REJECTED_EFFECTIVE_RATIO", "1")
    monkeypatch.setenv("ML_SHADOW_INFLUENCE_MIN_PROOF_ANCHOR", "5")
    frame = pd.DataFrame(
        [
            {"source_type": "archive_legacy", "sample_weight": 0.4},
            *[
                {
                    "source_type": "shadow_rejected",
                    "sample_weight": 1.0,
                }
                for _ in range(20)
            ],
        ]
    )

    governed, evidence = _govern_training_source_influence(frame)

    assert len(governed) == len(frame)
    assert evidence["proof_rows"] == 0
    assert evidence["shadow_effective_weight_after"] == 5.0
    assert governed.loc[
        governed["source_type"] == "archive_legacy",
        "sample_weight",
    ].iloc[0] == 0.4


def test_training_governance_has_schema_version_in_module_scope():
    import ml.train_model as trainer
    from ml.schema_version import get_current_schema_version

    assert hasattr(trainer, "CURRENT_SCHEMA_VERSION")
    assert int(trainer.CURRENT_SCHEMA_VERSION) == int(
        get_current_schema_version()
    )


def test_analytics_training_master_switch_blocks_drift_retrain():
    source = Path("runtime/analytics.py").read_text(encoding="utf-8")
    trainer = source[
        source.index("async def _run_ml_training_serialized"):
        source.index("async def _openai_startup_probe")
    ]
    assert 'if not _enabled("ANALYTICS_ML_TRAIN_ENABLED", True):' in trainer
    assert "status=disabled_by_master_switch" in trainer


def test_schema_migration_candidate_keeps_forward_proof_lease():
    trainer = Path("ml/train_model.py").read_text(encoding="utf-8")
    schema_block = trainer[
        trainer.index("schema_promotion = {"):
        trainer.index("lineage_decision = await asyncio.to_thread(")
    ]
    forward_block = trainer[
        trainer.index("candidate_forward_gate = {"):
        trainer.index("feature_baseline = _feature_distribution_baseline(")
    ]
    assert "candidate_first_requested" in schema_block
    assert "if not candidate_first_requested:" in schema_block
    assert "forward_candidate=%s" in schema_block
    assert "if promotion_eligible and candidate_first_requested:" in forward_block
    assert '"required": True' in forward_block


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
    assert "submit_background_coro(" in engine_ml
    candidate_persist = engine_ml[
        engine_ml.index("def _persist_candidate_forward_observation("):
        engine_ml.index("def _persist_shadow_prediction(")
    ]
    assert "run_sync(" not in candidate_persist
    assert "aligned_features = build_model_feature_values(" in candidate_persist
    assert "champion_probability=(" in core
    assert "champion_threshold=float(threshold)" in core
    assert "champion_passed=bool(approved)" in core


@pytest.mark.asyncio
async def test_artifact_loaders_snapshot_before_rollback(monkeypatch):
    from contextlib import asynccontextmanager

    import ml.candidate_forward as forward

    class ExpiringRow:
        def __init__(self, session, model_name):
            self._session = session
            self._values = {
                "id": 7 if model_name == "candidate" else 8,
                "artifact_hash_sha256": (
                    "candidate-hash" if model_name == "candidate" else "primary-hash"
                ),
                "model_version": "1.0.0",
                "feature_schema_version": "feature-schema-v4",
                "trained_at": None,
                "created_at": None,
                "metrics": {"auc": 0.8},
                "payload": {
                    "schema_version": 4,
                    "feature_schema_hash_sha256": "feature-hash",
                    "training_run_id": "run-1",
                    "trained_at": "2026-09-29T21:00:00",
                },
            }

        def __getattr__(self, name):
            if name in self._values:
                if self._session.expired:
                    raise RuntimeError("detached row accessed after rollback")
                return self._values[name]
            raise AttributeError(name)

    class ScalarResult:
        def __init__(self, row):
            self._row = row

        def scalars(self):
            return self

        def first(self):
            return self._row

    class FakeSession:
        def __init__(self):
            self.expired = False
            self.calls = 0

        async def execute(self, _query):
            self.calls += 1
            model_name = "candidate" if self.calls == 1 else "primary"
            return ScalarResult(ExpiringRow(self, model_name))

        async def rollback(self):
            self.expired = True

    session = FakeSession()

    @asynccontextmanager
    async def fake_get_session(**_kwargs):
        session.expired = False
        yield session

    monkeypatch.setattr("db.session.get_session", fake_get_session)

    candidate = await forward.load_active_candidate()
    primary = await forward.load_active_primary()

    assert candidate["artifact_hash_sha256"] == "candidate-hash"
    assert candidate["schema_version"] == 4
    assert candidate["training_run_id"] == "run-1"
    assert primary["artifact_hash_sha256"] == "primary-hash"
    assert primary["schema_version"] == 4


@pytest.mark.asyncio
async def test_candidate_lease_blocks_collecting_forward_candidate(monkeypatch):
    import ml.candidate_forward as forward

    async def fake_candidate():
        return _eligible_candidate()

    async def fake_primary():
        return {
            "artifact_hash_sha256": "champ",
            "schema_version": 4,
        }

    async def fake_evidence(_candidate=None):
        return {
            "eligible": False,
            "status": "collecting",
            "candidate_age_hours": 1.0,
            "observations": 40,
            "resolved": 8,
            "reasons": ["insufficient_observations"],
        }

    monkeypatch.setattr(forward, "load_active_candidate", fake_candidate)
    monkeypatch.setattr(forward, "load_active_primary", fake_primary)
    monkeypatch.setattr(
        forward,
        "evaluate_candidate_forward_evidence",
        fake_evidence,
    )
    monkeypatch.delenv("ML_ALLOW_ACTIVE_CANDIDATE_REPLACEMENT", raising=False)

    lease = await forward.candidate_replacement_lease()
    assert lease["blocked"] is True
    assert lease["reason"] == "active_candidate_forward_lease"
    assert lease["candidate_status"] == "collecting"


@pytest.mark.asyncio
async def test_candidate_lease_allows_failed_candidate_replacement(monkeypatch):
    import ml.candidate_forward as forward

    async def fake_candidate():
        return _eligible_candidate()

    async def fake_primary():
        return {
            "artifact_hash_sha256": "champ",
            "schema_version": 4,
        }

    async def fake_evidence(_candidate=None):
        return {
            "eligible": False,
            "status": "failed",
            "candidate_age_hours": 4.0,
            "observations": 150,
            "resolved": 80,
            "reasons": ["candidate_expected_r_below_floor"],
        }

    monkeypatch.setattr(forward, "load_active_candidate", fake_candidate)
    monkeypatch.setattr(forward, "load_active_primary", fake_primary)
    monkeypatch.setattr(
        forward,
        "evaluate_candidate_forward_evidence",
        fake_evidence,
    )

    lease = await forward.candidate_replacement_lease()
    assert lease["blocked"] is False
    assert lease["reason"] == "candidate_forward_status_failed"


@pytest.mark.asyncio
async def test_candidate_lease_allows_stale_parent_replacement(monkeypatch):
    import ml.candidate_forward as forward

    async def fake_candidate():
        return _eligible_candidate(parent="old-champ")

    async def fake_primary():
        return {
            "artifact_hash_sha256": "new-champ",
            "schema_version": 4,
        }

    monkeypatch.setattr(forward, "load_active_candidate", fake_candidate)
    monkeypatch.setattr(forward, "load_active_primary", fake_primary)

    lease = await forward.candidate_replacement_lease()
    assert lease["blocked"] is False
    assert lease["reason"] == "candidate_parent_no_longer_current"


def test_trainer_fail_closes_when_candidate_lease_is_unavailable():
    trainer = Path("ml/train_model.py").read_text(encoding="utf-8")
    guard = trainer[
        trainer.index("# Production retraining is challenger-first."):
        trainer.index("if lookback_days is None:")
    ]
    assert "candidate_replacement_lease" in guard
    assert "candidate_forward_lease_unavailable" in guard
    assert "return False" in guard


@pytest.mark.asyncio
async def test_candidate_promotion_requires_forward_proof_admission(monkeypatch):
    import ml.candidate_forward as forward

    candidate = _eligible_candidate()
    candidate["payload"]["training_meta"]["candidate_forward_gate"] = {
        "required": False,
        "reason": "not_required",
    }

    async def fake_candidate():
        return candidate

    async def fake_primary():
        return {
            "artifact_hash_sha256": "champ",
            "schema_version": 4,
        }

    monkeypatch.setattr(forward, "load_active_candidate", fake_candidate)
    monkeypatch.setattr(forward, "load_active_primary", fake_primary)

    result = await forward.promote_candidate_from_forward_proof(
        authorization_id="owner-forward-proof-approval"
    )
    assert result["ok"] is False
    assert result["reason"] == "candidate_not_admitted_to_forward_proof"


@pytest.mark.asyncio
async def test_candidate_promotion_rejects_recorded_noninferiority_failure(monkeypatch):
    import ml.candidate_forward as forward

    candidate = _eligible_candidate()
    candidate["payload"]["training_meta"]["champion_comparison"] = {
        "enabled": True,
        "reason": "material_regression",
        "regressions": {"auc": {"candidate": 0.80, "champion": 0.84}},
    }

    async def fake_candidate():
        return candidate

    async def fake_primary():
        return {
            "artifact_hash_sha256": "champ",
            "schema_version": 4,
        }

    monkeypatch.setattr(forward, "load_active_candidate", fake_candidate)
    monkeypatch.setattr(forward, "load_active_primary", fake_primary)

    result = await forward.promote_candidate_from_forward_proof(
        authorization_id="owner-forward-proof-approval"
    )
    assert result["ok"] is False
    assert result["reason"] == "candidate_offline_noninferiority_failed"


def test_training_uses_durable_champion_identity_as_production_parent():
    trainer = Path("ml/train_model.py").read_text(encoding="utf-8")
    block = trainer[
        trainer.index("deployed_runtime = _is_production_runtime()"):
        trainer.index("quality_ok, min_accuracy, min_auc = _promotion_quality_gate(")
    ]
    assert "await _load_durable_champion_metrics()" in block
    assert "durable_parent_model_hash_sha256" in block
    assert '"durable_registry"' in block
    assert "durable_champion_identity_unavailable" in block
    assert "parent_identity_source" in block


@pytest.mark.asyncio
async def test_candidate_promotion_requires_explicit_authorization_by_default(monkeypatch):
    import ml.candidate_forward as forward

    candidate = _eligible_candidate()
    primary = {
        "artifact_hash_sha256": "champ",
        "schema_version": 4,
    }

    async def fake_candidate():
        return candidate

    async def fake_primary():
        return primary

    async def fake_evidence(_candidate=None):
        return {"eligible": True, "status": "eligible"}

    monkeypatch.setattr(forward, "load_active_candidate", fake_candidate)
    monkeypatch.setattr(forward, "load_active_primary", fake_primary)
    monkeypatch.setattr(forward, "evaluate_candidate_forward_evidence", fake_evidence)
    monkeypatch.delenv("ML_CANDIDATE_FORWARD_AUTO_PROMOTION_ENABLED", raising=False)

    result = await forward.promote_candidate_from_forward_proof()
    assert result["ok"] is False
    assert result["reason"] == "promotion_authorization_required"


@pytest.mark.asyncio
async def test_candidate_schema_change_keeps_separate_schema_gate(monkeypatch):
    import ml.candidate_forward as forward

    async def fake_candidate():
        return _eligible_candidate(
            artifact="cand-v4",
            parent="champ-v3",
            schema=4,
        )

    async def fake_primary():
        return {
            "artifact_hash_sha256": "champ-v3",
            "schema_version": 3,
        }

    async def fake_evidence(_candidate=None):
        return {"eligible": True, "status": "eligible"}

    monkeypatch.setattr(forward, "load_active_candidate", fake_candidate)
    monkeypatch.setattr(forward, "load_active_primary", fake_primary)
    monkeypatch.setattr(forward, "evaluate_candidate_forward_evidence", fake_evidence)
    monkeypatch.delenv("ML_ALLOW_SCHEMA_VERSION_PROMOTION", raising=False)
    monkeypatch.delenv("ML_SCHEMA_PROMOTION_CERTIFICATION_ID", raising=False)

    result = await forward.promote_candidate_from_forward_proof(
        authorization_id="owner-forward-proof-approval"
    )
    assert result["ok"] is False
    assert result["reason"] == "schema_migration_requires_authorization"


@pytest.mark.asyncio
async def test_candidate_promotion_rejects_stale_parent_champion(monkeypatch):
    import ml.candidate_forward as forward

    async def fake_candidate():
        return _eligible_candidate(
            artifact="cand",
            parent="old-champ",
            schema=4,
        )

    async def fake_primary():
        return {
            "artifact_hash_sha256": "new-champ",
            "schema_version": 4,
        }

    monkeypatch.setattr(forward, "load_active_candidate", fake_candidate)
    monkeypatch.setattr(forward, "load_active_primary", fake_primary)

    result = await forward.promote_candidate_from_forward_proof(
        authorization_id="owner-forward-proof-approval"
    )
    assert result["ok"] is False
    assert result["reason"] == "candidate_parent_champion_changed"


@pytest.mark.asyncio
async def test_candidate_promotion_requires_valid_calibration(monkeypatch):
    import ml.candidate_forward as forward

    candidate = _eligible_candidate()
    candidate["metrics"]["calibration"]["validated"] = False

    async def fake_candidate():
        return candidate

    async def fake_primary():
        return {
            "artifact_hash_sha256": "champ",
            "schema_version": 4,
        }

    monkeypatch.setattr(forward, "load_active_candidate", fake_candidate)
    monkeypatch.setattr(forward, "load_active_primary", fake_primary)

    result = await forward.promote_candidate_from_forward_proof(
        authorization_id="owner-forward-proof-approval"
    )
    assert result["ok"] is False
    assert result["reason"] == "candidate_calibration_unvalidated"


@pytest.mark.asyncio
async def test_candidate_promotion_requires_recorded_offline_quality(monkeypatch):
    import ml.candidate_forward as forward

    candidate = _eligible_candidate()
    candidate["payload"]["training_meta"]["offline_quality_gate"] = {
        "passed": False
    }

    async def fake_candidate():
        return candidate

    async def fake_primary():
        return {
            "artifact_hash_sha256": "champ",
            "schema_version": 4,
        }

    monkeypatch.setattr(forward, "load_active_candidate", fake_candidate)
    monkeypatch.setattr(forward, "load_active_primary", fake_primary)

    result = await forward.promote_candidate_from_forward_proof(
        authorization_id="owner-forward-proof-approval"
    )
    assert result["ok"] is False
    assert result["reason"] == "offline_quality_evidence_missing_or_failed"


def test_owner_candidate_commands_are_registered_and_strictly_guarded():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    owner = (root / "signalrank_telegram" / "owner_commands.py").read_text(
        encoding="utf-8"
    )
    bot = (root / "signalrank_telegram" / "bot.py").read_text(
        encoding="utf-8"
    )
    policy = (root / "core" / "tier_policy.py").read_text(
        encoding="utf-8"
    )
    access = (root / "signalrank_telegram" / "command_access.py").read_text(
        encoding="utf-8"
    )

    assert "async def ml_candidate_command(" in owner
    assert "async def ml_candidate_promote_command(" in owner
    promote = owner[
        owner.index("async def ml_candidate_promote_command("):
    ]
    assert "await _is_strict_owner(update.effective_user.id)" in promote
    assert 'confirmation != "CONFIRM"' in promote
    assert "promote_candidate_from_forward_proof" in promote

    assert "ml_candidate_command," in bot
    assert "ml_candidate_promote_command," in bot
    assert 'CommandHandler("ml_candidate"' in bot
    assert 'CommandHandler("ml_candidate_promote"' in bot

    assert '"ml_candidate": Tier.OWNER' in policy
    assert '"ml_candidate_promote": Tier.OWNER' in policy
    assert '("ml_candidate",' in access
    assert '("ml_candidate_promote",' in access


def test_candidate_forward_outcomes_do_not_pollute_rejection_false_negative_metrics():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    worker = (root / "engine" / "shadow_outcome_worker.py").read_text(
        encoding="utf-8"
    )
    assert '"candidate_forward_outcome"' in worker
    assert '"CANDIDATE_FORWARD"' in worker
    assert 'candidate_forward:counts:{bucket}' in worker
    assert 'if is_candidate_forward:' in worker
