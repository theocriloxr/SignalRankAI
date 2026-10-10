"""Canonical durable trial lineage for the existing adaptive research worker.

No client-supplied results are accepted. Definitions and terminal evidence are
append-only in PostgreSQL; retries identify the same experiment. A strategy
display-name change does not alter its family or trial fingerprint.
"""
from __future__ import annotations

import hashlib
import json
import asyncio
from typing import Any, Callable, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def canonical_json(value: Any) -> str:
    def inspect(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                token = str(key).lower()
                if any(secret in token for secret in ("password", "api_key", "private_key", "access_token", "refresh_token", "credential")):
                    raise ValueError("secret_field_in_research_evidence")
                inspect(child)
        elif isinstance(item, (tuple, list)):
            for child in item:
                inspect(child)
    inspect(value)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode()) > 256_000:
        raise ValueError("research_evidence_too_large")
    return encoded


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


async def register_hypothesis(
    session: AsyncSession, *, trial_family: str, spec: Mapping[str, Any],
    code_commit: str, created_by: str, parent_hypothesis_id: str | None = None,
) -> str:
    version = 1
    if parent_hypothesis_id:
        parent = (await session.execute(text(
            "SELECT trial_family,version FROM research_hypotheses WHERE hypothesis_id=:id"
        ), {"id": parent_hypothesis_id})).mappings().first()
        if not parent:
            raise ValueError("research_hypothesis_parent_missing")
        trial_family, version = parent["trial_family"], int(parent["version"]) + 1
    if not trial_family.strip() or len(trial_family) > 128 or not created_by or not code_commit:
        raise ValueError("hypothesis_provenance_required")
    payload = {"trial_family": trial_family, "spec": dict(spec), "version": version,
               "parent_hypothesis_id": parent_hypothesis_id, "code_commit": code_commit}
    digest = content_hash(payload)
    await session.execute(text("""
        INSERT INTO research_hypotheses(hypothesis_id,parent_hypothesis_id,trial_family,
            version,spec,content_hash,created_by,code_commit)
        VALUES(:id,:parent,:family,:version,CAST(:spec AS JSONB),:hash,:actor,:commit)
        ON CONFLICT(hypothesis_id) DO NOTHING
    """), {"id": digest, "parent": parent_hypothesis_id, "family": trial_family,
             "version": version, "spec": canonical_json(dict(spec)), "hash": digest,
             "actor": created_by, "commit": code_commit})
    return digest


async def start_experiment(
    session: AsyncSession, *, hypothesis_id: str, strategy_id: str,
    strategy_version: str, specification: Mapping[str, Any],
    parent_experiment_id: str | None = None,
) -> str:
    family = (await session.execute(text("SELECT trial_family FROM research_hypotheses WHERE hypothesis_id=:id"),
                                   {"id": hypothesis_id})).scalar_one()
    required = {"parameter_set", "dataset_version", "feature_version", "label_version",
                "execution_model_version", "risk_model_version", "code_commit", "random_seed",
                "asset_scope", "timeframe_scope", "regime_scope"}
    if not required <= specification.keys() or not strategy_id or not strategy_version:
        raise ValueError("experiment_specification_incomplete")
    if parent_experiment_id:
        parent_family = (await session.execute(text("SELECT trial_family FROM research_experiments WHERE experiment_id=:id"),
                                              {"id": parent_experiment_id})).scalar_one()
        if parent_family != family:
            raise ValueError("experiment_parent_family_mismatch")
    # Identity/strategy name are deliberately absent; renaming a strategy does
    # not reset lineage or inflate the count for an otherwise identical retry.
    fingerprint = content_hash({"family": family, "specification": dict(specification),
                                "strategy_version": strategy_version})
    await session.execute(text("""
        INSERT INTO research_experiments(experiment_id,hypothesis_id,parent_experiment_id,
            trial_family,trial_fingerprint,strategy_id,strategy_version,dataset_version,feature_version,specification)
        VALUES(:id,:hypothesis,:parent,:family,:fingerprint,:strategy,:version,:dataset,:feature,CAST(:spec AS JSONB))
        ON CONFLICT(trial_family,trial_fingerprint) DO NOTHING
    """), {"id": fingerprint, "hypothesis": hypothesis_id, "parent": parent_experiment_id,
             "family": family, "fingerprint": fingerprint, "strategy": strategy_id, "version": strategy_version,
             "dataset": specification["dataset_version"], "feature": specification["feature_version"],
             "spec": canonical_json(dict(specification))})
    return fingerprint


async def complete_experiment(session: AsyncSession, experiment_id: str, result: Mapping[str, Any], *, status: str = "COMPLETED") -> None:
    encoded = canonical_json(dict(result))
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    await session.execute(text("""
        INSERT INTO research_experiment_results(experiment_id,status,result,evidence_hash)
        VALUES(:id,:status,CAST(:result AS JSONB),:hash) ON CONFLICT(experiment_id) DO NOTHING
    """), {"id": experiment_id, "status": status, "result": encoded, "hash": digest})
    stored = (await session.execute(text("SELECT evidence_hash,status FROM research_experiment_results WHERE experiment_id=:id"),
                                   {"id": experiment_id})).mappings().one()
    if stored["evidence_hash"] != digest or stored["status"] != status:
        raise ValueError("conflicting_immutable_experiment_result")


async def trial_counts(session: AsyncSession, hypothesis_id: str) -> dict[str, Any]:
    row = (await session.execute(text("""
        SELECT COUNT(e.experiment_id) AS raw_trial_count, COUNT(r.experiment_id) AS terminal_trial_count
        FROM research_hypotheses h
        JOIN research_experiments e ON e.trial_family=h.trial_family
        LEFT JOIN research_experiment_results r ON r.experiment_id=e.experiment_id
        WHERE h.hypothesis_id=:id
    """), {"id": hypothesis_id})).mappings().one()
    raw = int(row["raw_trial_count"])
    return {"raw_trial_count": raw, "effective_trial_count": raw,
            "terminal_trial_count": int(row["terminal_trial_count"]),
            "effective_trial_method": "raw_count_no_dependence_discount",
            "history_scope": "since_ledger_introduction", "pre_ledger_trial_history_verified": False}


async def research_snapshot(session: AsyncSession, *, asset: str | None = None) -> dict:
    experiments = (await session.execute(text("""
        SELECT e.experiment_id,e.hypothesis_id,e.strategy_id,e.strategy_version,e.trial_family,
               e.dataset_version,e.feature_version,e.specification,e.started_at,
               jsonb_build_object('status',CASE WHEN ds.dataset_version IS NULL
                    THEN 'UNAVAILABLE' ELSE 'CAPTURED' END,
                    'scope','canonical_outcomes_and_captured_sequence_metadata',
                    'content_hash',ds.content_hash,'row_count',ds.row_count,
                    'observation_cutoff',ds.observation_cutoff,
                    'complete_market_input_replay',FALSE) AS dataset_snapshot,
               h.spec AS hypothesis,h.version AS hypothesis_version,h.parent_hypothesis_id,
               r.status,r.result,r.evidence_hash,r.completed_at
        FROM research_experiments e JOIN research_hypotheses h USING(hypothesis_id)
        LEFT JOIN research_experiment_results r USING(experiment_id)
        LEFT JOIN research_dataset_snapshots ds ON ds.dataset_version=e.dataset_version
        WHERE CAST(:asset AS TEXT) IS NULL OR e.specification->'asset_scope' ? :asset
        ORDER BY e.started_at DESC,e.experiment_id LIMIT 50
    """), {"asset": asset})).mappings().all()
    families = (await session.execute(text("""
        SELECT e.trial_family,COUNT(*) AS raw_trial_count,COUNT(r.experiment_id) AS terminal_trial_count
        FROM research_experiments e LEFT JOIN research_experiment_results r USING(experiment_id)
        GROUP BY e.trial_family ORDER BY e.trial_family LIMIT 100
    """))).mappings().all()
    return {"experiments": [dict(row) for row in experiments], "families": [dict(row) for row in families],
            "historical_coverage": "since_ledger_introduction", "automatic_live_promotion": False}


async def run_recorded_search(
    search: Callable, *, hypothesis_id: str, strategy_id: str, strategy_version: str,
    specification: Mapping[str, Any], session_factory: Callable | None = None,
    parent_experiment_id: str | None = None,
) -> dict[str, Any]:
    """Run the existing grid/Optuna optimizer in a worker thread with durable events.

    Each STARTED transaction commits before objective evaluation. PostgreSQL
    failures abort the search, rather than falling back to unrecorded trials.
    Research results never activate a model or an adaptive profile.
    """
    if session_factory is None:
        from db.session import get_session
        session_factory = get_session
    canonical_json(dict(specification))
    loop = asyncio.get_running_loop()
    started: dict[int, tuple[str, str]] = {}

    async def persist(event: str, number: int, parameters: Mapping, result: Mapping | None) -> str:
        if not isinstance(number, int) or isinstance(number, bool) or number < 0:
            raise ValueError("invalid_search_trial_number")
        params_json = canonical_json(dict(parameters))
        async with session_factory(priority="analytics", label="research.search.event", timeout_seconds=8) as session:
            if event == "STARTED":
                if number in started:
                    raise ValueError("duplicate_search_trial_start")
                definition = {**specification, "parameter_set": dict(parameters)}
                experiment = await start_experiment(session, hypothesis_id=hypothesis_id,
                    strategy_id=strategy_id, strategy_version=strategy_version, specification=definition,
                    parent_experiment_id=parent_experiment_id)
                await session.commit()
                started[number] = experiment, params_json
                return experiment
            if event not in {"COMPLETED", "FAILED", "REJECTED"} or number not in started:
                raise ValueError("invalid_search_trial_event")
            experiment, original_params = started[number]
            if original_params != params_json or not result or result.get("experiment_id") != experiment:
                raise ValueError("search_trial_identity_mismatch")
            await complete_experiment(session, experiment,
                {"optimizer_result": dict(result), "promotion_eligible": False,
                 "selection_bias_validation_required": True}, status=event)
            await session.commit()
            return experiment

    def recorder(event, number, parameters, result):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError("search_recorder_requires_worker_thread")
        future = asyncio.run_coroutine_threadsafe(persist(event, number, parameters, result), loop)
        try:
            return future.result(timeout=30)
        except TimeoutError:
            future.cancel()
            raise TimeoutError("research_event_persistence_timeout") from None

    result = await asyncio.to_thread(search, recorder)
    async with session_factory(priority="analytics", label="research.search.counts", timeout_seconds=8) as session:
        counts = await trial_counts(session, hypothesis_id)
    return {"result": result, "trial_counts": counts, "automatic_live_promotion": False}
