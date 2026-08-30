from __future__ import annotations

import json

import pytest

from services.continuous_improvement.audit_store import write_review_artifacts
from services.continuous_improvement.codex_handoff import build_codex_task, handoff_allowed
from services.continuous_improvement.collector import anonymize_research_payload, dataset_hash
from services.continuous_improvement.experiment_manager import (
    Experiment,
    ExperimentState,
    production_activation_allowed,
)
from services.continuous_improvement.promotion_gate import evaluate_production_eligibility
from services.continuous_improvement.recommendation_schema import (
    Recommendation,
    RecommendationKind,
    ReviewReport,
)
from services.continuous_improvement.reviewer import normalize_recommendations
from services.continuous_improvement.weekly_review import detect_incidents


def _recommendation(kind: RecommendationKind = RecommendationKind.CODE) -> Recommendation:
    return Recommendation(
        recommendation_id="rec-test",
        kind=kind,
        title="Test recommendation",
        rationale="Measured regression",
        evidence=("evidence-1",),
        proposed_change={"flag": "candidate"},
    )


def test_recommendations_can_never_auto_apply() -> None:
    with pytest.raises(ValueError, match="cannot_auto_apply"):
        Recommendation(
            recommendation_id="unsafe",
            kind=RecommendationKind.CODE,
            title="Unsafe",
            rationale="No",
            evidence=("evidence",),
            proposed_change={},
            auto_apply=True,
        )


def test_research_payload_strips_nested_identifiers_and_secrets() -> None:
    clean = anonymize_research_payload({
        "summary": {"signals": 4},
        "user_id": 42,
        "nested": [{"email": "user@example.test", "avg_r": 0.2, "token": "secret"}],
    })
    encoded = json.dumps(clean)
    assert "user@example.test" not in encoded
    assert "secret" not in encoded
    assert clean["nested"][0]["avg_r"] == 0.2


def test_dataset_hash_is_order_independent() -> None:
    assert dataset_hash({"a": 1, "b": 2}) == dataset_hash({"b": 2, "a": 1})


def test_experiment_requires_sequential_evidence_backed_promotion() -> None:
    experiment = Experiment("exp-1", "rec-1", ExperimentState.PROPOSED, {}, "hash")
    with pytest.raises(ValueError, match="illegal_experiment_transition"):
        experiment.transition(ExperimentState.SHADOW, evidence_id="e-1")
    backtested = experiment.transition(ExperimentState.BACKTESTED, evidence_id="bt-1")
    assert backtested.evidence_ids == ("bt-1",)
    assert production_activation_allowed(backtested) is False


def test_promotion_gate_fails_closed_until_every_evidence_gate_passes() -> None:
    experiment = Experiment("exp-1", "rec-1", ExperimentState.STAGING_APPROVED, {}, "hash")
    blocked = evaluate_production_eligibility(experiment, owner_approved=False, release_evidence={})
    assert blocked.eligible is False
    approved = evaluate_production_eligibility(
        experiment,
        owner_approved=True,
        release_evidence={key: True for key in ("tests", "walk_forward", "shadow", "paper", "staging_soak", "rollback")},
    )
    assert approved.eligible is True


def test_codex_handoff_is_a_task_not_production_authorization() -> None:
    task = build_codex_task(_recommendation())
    assert handoff_allowed(_recommendation()) is True
    assert task["production_mutation_authorized"] is False
    assert task["real_execution_authorized"] is False
    assert task["required_workflow"][-1] == "owner_approval"


def test_review_normalization_requires_evidence_and_owner_approval() -> None:
    items = normalize_recommendations({
        "assessment": "Delivery degraded",
        "highest_risk_findings": ["confirmed delivery dropped"],
        "recommended_code_changes": ["add reconciliation"],
        "recommended_env_tweaks": ["reduce batch size"],
    })
    assert {item.kind for item in items} == {RecommendationKind.CODE, RecommendationKind.PARAMETER}
    assert all(item.requires_owner_approval and not item.auto_apply for item in items)


def test_incidents_detect_storage_and_delivery_breaks() -> None:
    storage = detect_incidents({"summary": {"signals": 3}, "deliveries": {"reserved": 0}})
    delivery = detect_incidents({"summary": {"signals": 3}, "deliveries": {"reserved": 3, "sent_ok": 0}})
    assert storage[0]["code"] == "INC-SIGNAL-STORAGE"
    assert delivery[0]["code"] == "INC-DELIVERY"


def test_review_artifacts_are_json_and_human_readable(tmp_path) -> None:
    report = ReviewReport(
        review_id="review-test",
        period_start="2026-08-16T00:00:00+00:00",
        period_end="2026-08-23T00:00:00+00:00",
        code_sha="a" * 40,
        dataset_hash="b" * 64,
        summary={"signals": 4},
        recommendations=(_recommendation(),),
    )
    json_path, markdown_path = write_review_artifacts(report, tmp_path)
    assert json.loads(json_path.read_text(encoding="utf-8"))["guardrail"].startswith("recommendations_only")
    assert "owner approval required" in markdown_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_legacy_ai_feedback_records_proposal_without_runtime_mutation(monkeypatch) -> None:
    from worker import ai_feedback

    writes: dict[str, str] = {}

    monkeypatch.setenv("ML_PROB_THRESHOLD", "0.30")
    with pytest.MonkeyPatch.context() as nested:
        from core import redis_state

        nested.setattr(
            redis_state.state,
            "set_sync",
            lambda key, value, ex=None: writes.__setitem__(str(key), str(value)),
        )
        assert await ai_feedback.apply_recommendation({"new_threshold": 0.42, "reason": "test"}) is True

    assert ai_feedback.os.environ["ML_PROB_THRESHOLD"] == "0.30"
    assert "ENGINE_BASE_THRESHOLD" not in writes
    proposal = json.loads(writes["signalrankai:continuous_improvement:last_parameter_proposal"])
    assert proposal["auto_apply"] is False
    assert proposal["requires_owner_approval"] is True


@pytest.mark.asyncio
async def test_scheduled_review_is_due_checked_and_never_mutates_production(monkeypatch, tmp_path) -> None:
    from services.continuous_improvement import scheduler

    writes: dict[str, str] = {}
    monkeypatch.setattr(scheduler.state, "get_sync", lambda _key: "0")
    monkeypatch.setattr(scheduler.state, "set_sync", lambda key, value, ex=None: writes.__setitem__(key, value))
    monkeypatch.setenv("CONTINUOUS_IMPROVEMENT_ARTIFACT_DIR", str(tmp_path))

    report = ReviewReport(
        review_id="review-scheduled",
        period_start="2026-08-16T00:00:00+00:00",
        period_end="2026-08-23T00:00:00+00:00",
        code_sha="a" * 40,
        dataset_hash="b" * 64,
        summary={},
    )

    async def _run(**_kwargs):
        return report, (tmp_path / "review.json", tmp_path / "review.md")

    monkeypatch.setattr(scheduler, "run_weekly_review", _run)
    result = await scheduler.run_scheduled_review_once(now=2_000_000.0)
    assert result["review_id"] == "review-scheduled"
    assert result["production_mutation"] is False
    assert scheduler._LAST_RUN_KEY in writes


def test_worker_registers_review_only_in_analytics_ownership_lane() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "worker" / "worker.py").read_text(encoding="utf-8")
    block = source.split('"continuous_improvement_review"', 1)[0][-500:]
    assert "_analytics_work_allowed_in_worker()" in block
    assert 'CONTINUOUS_IMPROVEMENT_REVIEW_ENABLED' in block
