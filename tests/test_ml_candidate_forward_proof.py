from types import SimpleNamespace

import pytest

from ml.candidate_forward import _decision_stats, _outcome_class
from engine.ml import _candidate_forward_observation_key


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
