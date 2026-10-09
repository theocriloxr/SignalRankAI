from __future__ import annotations

import hashlib
import asyncio
import json
import logging
import math
import os
from dataclasses import asdict
from contextlib import asynccontextmanager
from collections import defaultdict
from datetime import timedelta
from typing import Any, AsyncIterator
from uuid import uuid4

from sqlalchemy import text

from core.production_integrity import calibration_evidence_valid
from ml.metrics import brier_score
from db.session import get_session
from core.redis_state import state
from utils.timeutils import now_utc_naive

from .components import DEFAULT_COMPONENTS
from .dataset import AdaptiveDatasetRow, build_dataset
from .statistics import profit_factor as _profit_factor
from .repository import publish_approved_profiles
from .walk_forward import walk_forward_evaluate
from .integrity import audit_adaptive_dataset
from .research_ledger import register_hypothesis, start_experiment, complete_experiment, trial_counts
from .statistics import return_diagnostics, block_bootstrap_survival

logger = logging.getLogger(__name__)


def _max_drawdown(values: list[float]) -> float:
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _feature_version() -> tuple[str, str, dict[str, str]]:
    components = {
        str(getattr(component, "strategy_id", type(component).__name__)): str(getattr(component, "version", "unknown"))
        for component in DEFAULT_COMPONENTS
    }
    schema = {
        "market_context": "v1",
        "strategy_evidence": "v1",
        "sequence_reference": "v1",
        "outcome_target": "r_multiple",
        "order_flow_policy": "genuine_only",
    }
    canonical = json.dumps({"components": components, "schema": schema}, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return f"adaptive-features:{digest[:20]}", digest, components


def _profile_fingerprint(
    *,
    asset: str,
    dataset_version: str,
    feature_version: str,
    family_weights: dict[str, float],
    regime_weights: dict[str, float],
    evidence_category: str = "unknown",
) -> str:
    payload = {
        "asset": asset,
        "dataset_version": dataset_version,
        "feature_version": feature_version,
        "family_weights": family_weights,
        "regime_weights": regime_weights,
        "evidence_category": evidence_category,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _derive_weights(
    rows: list[AdaptiveDatasetRow], minimum_samples: int
) -> tuple[dict[str, float], dict[str, float], dict[str, Any]]:
    by_family: dict[str, list[float]] = defaultdict(list)
    by_regime: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_family[row.family].append(row.r_multiple)
        by_regime[row.regime].append(row.r_multiple)

    def bounded_weight(values: list[float]) -> float:
        expectancy = sum(values) / len(values)
        reliability = min(1.0, len(values) / max(minimum_samples * 3, 1))
        weight = 1.0 + max(-0.15, min(0.15, expectancy * 0.08)) * reliability
        pf = _profit_factor(values)
        if (pf is not None and pf < 1.0) or _max_drawdown(values) > float(
            os.getenv("ADAPTIVE_SEGMENT_MAX_DRAWDOWN_R", "12") or 12
        ):
            weight = min(weight, 0.90)
        return round(max(0.80, min(1.15, weight)), 4)

    family_weights = {
        family: bounded_weight(values) for family, values in by_family.items() if len(values) >= minimum_samples
    }
    regime_weights = {
        regime: bounded_weight(values) for regime, values in by_regime.items() if len(values) >= minimum_samples
    }
    all_returns = [row.r_multiple for row in rows]
    summary = {
        "sample_size": len(rows),
        "mean_expectancy_r": sum(all_returns) / len(all_returns) if all_returns else 0.0,
        "profit_factor": _profit_factor(all_returns) if all_returns else None,
        "profit_factor_reason": "no_observed_losses" if all_returns and not any(value < 0 for value in all_returns) else "no_observations" if not all_returns else None,
        "max_drawdown_r": _max_drawdown(all_returns),
        "family_segments": {key: len(value) for key, value in by_family.items()},
        "regime_segments": {key: len(value) for key, value in by_regime.items()},
    }
    return family_weights, regime_weights, summary


async def _monitor_runtime_profiles(session: Any) -> dict[str, Any]:
    """Suspend degraded runtime profiles using confirmed live-delivery evidence only."""
    minimum_live = max(20, int(os.getenv("ADAPTIVE_DRIFT_MIN_LIVE_SAMPLES", "30") or 30))
    drawdown_limit = float(os.getenv("ADAPTIVE_DRIFT_MAX_DRAWDOWN_R", "10") or 10)
    brier_limit = float(os.getenv("ADAPTIVE_DRIFT_MAX_BRIER", "0.35") or 0.35)
    expectancy_floor = float(os.getenv("ADAPTIVE_DRIFT_MIN_EXPECTANCY_R", "-0.10") or -0.10)
    if minimum_live > 250 or not all(math.isfinite(v) for v in (drawdown_limit, brier_limit, expectancy_floor)) or drawdown_limit < 1 or not 0.05 <= brier_limit <= 1:
        raise ValueError("invalid_adaptive_health_thresholds")
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT p.profile_id,p.asset,p.state,p.rollback_profile_id,h.*
                FROM adaptive_asset_profiles p
                LEFT JOIN LATERAL (
                    SELECT o.r_multiple,o.closed_at,s.created_at,s.signal_id,
                           s.ml_probability_calibrated,s.ml_calibration_version,
                           s.ml_calibration_validated,s.ml_calibration_validation_rows,
                           s.ml_calibration_brier,s.ml_calibration_ece
                    FROM signals s JOIN outcomes o ON o.signal_id=s.signal_id
                    WHERE o.r_multiple IS NOT NULL
                      AND o.performance_inclusion_status='eligible'
                      AND o.closed_at IS NOT NULL AND o.closed_at <= NOW()
                      AND s.created_at <= o.closed_at
                      AND s.created_at >= NOW() - INTERVAL '120 days'
                      AND EXISTS (SELECT 1 FROM adaptive_signal_evidence ev
                                  WHERE ev.profile_id=p.profile_id AND ev.signal_id=s.signal_id)
                      AND EXISTS (SELECT 1 FROM signal_deliveries sd
                                  WHERE sd.signal_id=s.signal_id AND sd.sent_ok=TRUE
                                    AND UPPER(COALESCE(sd.delivery_state,''))='CONFIRMED')
                    ORDER BY o.closed_at DESC,s.signal_id LIMIT 250
                ) h ON TRUE
                WHERE p.is_current=TRUE AND p.state IN ('CANARY','LIMITED_LIVE','APPROVED')
                ORDER BY p.profile_id,h.closed_at DESC,h.signal_id
                """
                )
            )
        )
        .mappings()
        .all()
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    profile_meta: dict[str, dict[str, Any]] = {}
    for row in rows:
        profile_id = str(row["profile_id"])
        evidence = grouped[profile_id]
        # A LEFT JOIN placeholder is a profile with no eligible outcomes, not
        # an invalid observed return. Keep it in coverage without inventing R.
        if row["signal_id"] is not None and len(evidence) < 250:
            evidence.append(dict(row))
        profile_meta[profile_id] = dict(row)

    suspended: list[str] = []
    restored: list[str] = []
    diagnostics: list[dict[str, Any]] = []
    coverage = {status: 0 for status in ("UNAVAILABLE", "INSUFFICIENT", "OBSERVED", "INVALID")}
    for profile_id, evidence_rows in grouped.items():
        metrics = _runtime_health_metrics(evidence_rows, minimum_live=minimum_live,
            drawdown_limit=drawdown_limit, brier_limit=brier_limit, expectancy_floor=expectancy_floor)
        coverage[metrics["delivery_evidence_status"]] += 1
        meta = profile_meta[profile_id]
        if len(diagnostics) < 20:
            diagnostics.append({"profile_id": profile_id, "asset": str(meta["asset"]),
                "profile_state": str(meta["state"]),
                **{k: v for k, v in metrics.items() if k != "calibration_versions"}})
        reasons = metrics["reasons"]
        if not reasons:
            continue
        asset = str(meta["asset"])
        await session.execute(
            text(
                """
                UPDATE adaptive_asset_profiles
                SET state='SUSPENDED',is_current=FALSE,
                    metadata=jsonb_set(COALESCE(metadata,'{}'::jsonb),'{automatic_suspension}',CAST(:details AS JSONB),TRUE),
                    updated_at=NOW()
                WHERE profile_id=:profile_id
                """
            ),
            {
                "profile_id": profile_id,
                "details": json.dumps(metrics, allow_nan=False),
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO adaptive_drift_events(asset,profile_id,drift_type,severity,metrics,resolution,created_at)
                VALUES(:asset,:profile_id,'live_performance_drift','critical',CAST(:metrics AS JSONB),:resolution,NOW())
                """
            ),
            {
                "asset": asset,
                "profile_id": profile_id,
                "metrics": json.dumps(metrics, allow_nan=False),
                "resolution": "neutral_fallback_requires_revalidation",
            },
        )
        suspended.append(asset)
    return {"suspended_assets": suspended, "restored_profiles": restored,
            "evaluated_profile_count": len(grouped), "profile_diagnostics": diagnostics,
            "delivery_evidence_counts": coverage,
            "diagnostics_truncated": len(grouped) > len(diagnostics)}


def _runtime_health_metrics(rows: list[dict[str, Any]], *, minimum_live: int,
                            drawdown_limit: float, brier_limit: float, expectancy_floor: float) -> dict[str, Any]:
    """Delivery outcome diagnostics; component confidence is never a probability."""
    result: dict[str, Any] = {"reasons": [], "sample_size": len(rows), "expectancy_r": None,
        "max_drawdown_r": None, "brier_score": None, "calibrated_sample_size": 0,
        "delivery_evidence_status": "UNAVAILABLE" if not rows else "INSUFFICIENT",
        "coverage_reason": "no_eligible_delivery_outcomes" if not rows else "minimum_delivery_sample_not_met",
        "calibration_status": "UNAVAILABLE", "calibration_versions": {},
        "qualified_calibration_version_count": 0, "brier_aggregation": "worst_qualified_version",
        "broker_fills_certified": False, "approved_baseline_comparison": "UNVERIFIED"}
    if len(rows) > 250:
        raise ValueError("delivery_health_window_must_be_0_to_250")
    if not rows:
        return result
    if any(isinstance(row.get("r_multiple"), bool) or not isinstance(row.get("r_multiple"), (int, float))
           or not math.isfinite(row["r_multiple"]) for row in rows):
        result["reasons"].append("invalid_delivery_health_observations")
        result.update(delivery_evidence_status="INVALID", coverage_reason="invalid_delivery_health_observations")
        return result
    versions: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for row in rows:
        if row.get("ml_calibration_validated") is not True:
            continue
        if not calibration_evidence_valid(row):
            result["reasons"].append("invalid_calibrated_health_observations")
            result.update(delivery_evidence_status="INVALID", coverage_reason="invalid_calibrated_health_observations")
            return result
        versions[row["ml_calibration_version"]].append((int(row["r_multiple"] > 0), float(row["ml_probability_calibrated"])))
    result["calibrated_sample_size"] = sum(len(observations) for observations in versions.values())
    scores: list[float] = []
    for version, observations in sorted(versions.items()):
        score = brier_score([label for label, _ in observations], [probability for _, probability in observations]) if len(observations) >= minimum_live else None
        result["calibration_versions"][version] = {"sample_size": len(observations), "brier_score": score}
        if score is not None:
            scores.append(score)
    result["qualified_calibration_version_count"] = len(scores)
    result["brier_score"] = max(scores) if scores else None
    result["calibration_status"] = "OBSERVED" if scores else "INSUFFICIENT" if versions else "UNAVAILABLE"
    if len(rows) < minimum_live:
        return result
    returns = [float(row["r_multiple"]) for row in reversed(rows)]
    try:
        expectancy, drawdown = math.fsum(returns) / len(returns), _max_drawdown(returns)
        if not math.isfinite(expectancy) or not math.isfinite(drawdown):
            raise ValueError("delivery_metric_overflow")
    except (OverflowError, ValueError):
        result["reasons"].append("invalid_delivery_health_observations")
        result.update(delivery_evidence_status="INVALID", coverage_reason="invalid_delivery_health_observations")
        return result
    result.update(expectancy_r=expectancy, max_drawdown_r=drawdown,
                  delivery_evidence_status="OBSERVED", coverage_reason=None)
    if expectancy < expectancy_floor:
        result["reasons"].append("live_expectancy_below_floor")
    if drawdown > drawdown_limit:
        result["reasons"].append("live_drawdown_above_limit")
    if scores and max(scores) > brier_limit:
        result["reasons"].append("live_calibration_drift")
    return result


async def monitor_profile_health() -> dict[str, Any]:
    """Commit health decisions independently from research; invalidate under lock."""
    from .lifecycle import lock_profile_lifecycle
    from .repository import invalidate_profile_cache

    async with get_session(priority="critical", label="adaptive.monitor", timeout_seconds=4) as session:
        await lock_profile_lifecycle(session)
        drift = await _monitor_runtime_profiles(session)
        for asset in drift.get("suspended_assets", []):
            invalidate_profile_cache(asset)
        await session.commit()
    published = await publish_approved_profiles()
    return {**drift, "published": published}


@asynccontextmanager
async def _record_evaluation_failure(session: Any, experiment_id: str, run_id: str) -> AsyncIterator[None]:
    """Preserve a handled failure after rolling back an aborted evaluation transaction."""
    try:
        yield
    except Exception as exc:
        failure = {"reason": "adaptive_candidate_evaluation_failed", "error_type": type(exc).__name__[:128],
                   "stage": "walk_forward_and_candidate_persistence", "promotion_eligible": False}
        try:
            async with asyncio.timeout(8):
                await session.rollback()
        except Exception as rollback_error:
            logger.warning("[adaptive_learning] failed_transaction_rollback_error error_type=%s", type(rollback_error).__name__)
        try:
            async with asyncio.timeout(8), get_session(priority="critical", label="adaptive.record_failure", timeout_seconds=8) as failed_session:
                await failed_session.execute(text("SELECT pg_advisory_xact_lock(hashtext('signalrankai_adaptive_learning'))"))
                # A concurrent worker may have closed the same idempotent trial
                # after our rollback. Preserve its immutable terminal evidence.
                terminal = (await failed_session.execute(text(
                    "SELECT status FROM research_experiment_results WHERE experiment_id=:id"), {"id": experiment_id})).scalar_one_or_none()
                if terminal is None:
                    await complete_experiment(failed_session, experiment_id, failure, status="FAILED")
                await failed_session.execute(text(
                    "UPDATE adaptive_optimisation_runs SET status='FAILED',completed_at=NOW(),"
                    "summary=CAST(:summary AS JSONB) WHERE run_id=:run_id"),
                    {"run_id": run_id, "summary": json.dumps({**failure, "experiment_id": experiment_id,
                                                              "preserved_terminal_status": terminal})})
                await failed_session.commit()
        except Exception as recording_error:
            logger.error("[adaptive_learning] failure_recording_failed run=%s experiment=%s error_type=%s; retained definition remains visible",
                         run_id, experiment_id, type(recording_error).__name__)
        raise


class AdaptiveLearningWorker:
    async def run_once(self) -> dict[str, Any]:
        # Pausing research never pauses the independent health loop.
        drift_result = await monitor_profile_health()
        published = int(drift_result["published"])
        paused = str(state.get_sync("adaptive:optimisation:paused") or "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if paused:
            return {"published": published, "candidates": 0, "paused": True, "drift": drift_result}
        if str(os.getenv("ADAPTIVE_OPTIMISATION_ENABLED", "1")).lower() not in {"1", "true", "yes", "on"}:
            return {"published": published, "candidates": 0, "disabled": True, "drift": drift_result}

        minimum_samples = max(20, int(os.getenv("ADAPTIVE_MIN_OUTCOME_SAMPLES", "40") or 40))
        lookback_days = max(30, int(os.getenv("ADAPTIVE_LOOKBACK_DAYS", "365") or 365))
        cutoff = now_utc_naive() - timedelta(days=lookback_days)
        feature_version, feature_hash, component_versions = _feature_version()
        run_id = str(uuid4())

        async with get_session(
            priority="analytics",
            label="adaptive.optimise",
            timeout_seconds=float(os.getenv("ADAPTIVE_DB_TIMEOUT_SECONDS", "8") or 8),
        ) as session:
            lock_ok = bool(
                (
                    await session.execute(
                        text("SELECT pg_try_advisory_xact_lock(hashtext('signalrankai_adaptive_learning'))")
                    )
                ).scalar()
            )
            if not lock_ok:
                return {"published": published, "candidates": 0, "skipped": "distributed_lock_busy"}

            raw_rows = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT
                            s.signal_id,
                            s.created_at AS decision_time,
                            s.asset,
                            COALESCE(s.asset_class, 'unknown') AS asset_class,
                            s.timeframe,
                            COALESCE(s.regime, 'unknown') AS regime,
                            COALESCE(s.strategy_group, 'unknown') AS family,
                            s.direction,
                            s.status,
                            o.r_multiple,
                            GREATEST(o.closed_at,o.corrected_at) AS outcome_known_at,
                            CASE WHEN LOWER(o.provenance) IN ('paper','shadow','backtest','walk_forward','forward_test','canary')
                                 THEN LOWER(o.provenance) ELSE 'stored' END AS evidence_category,
                            EXISTS (
                                SELECT 1 FROM signal_deliveries sd
                                WHERE sd.signal_id = s.signal_id
                                  AND sd.sent_ok = TRUE
                                  AND UPPER(COALESCE(sd.delivery_state, '')) = 'CONFIRMED'
                            ) AS delivered,
                            FALSE AS executed,
                            COALESCE((
                                SELECT ARRAY_AGG(DISTINCT seq.sequence_hash ORDER BY seq.sequence_hash)
                                FROM adaptive_signal_sequences seq
                                WHERE seq.signal_id = s.signal_id
                            ), ARRAY[]::VARCHAR[]) AS sequence_hashes,
                            COALESCE((
                                SELECT MAX(
                                    CASE
                                        WHEN (ev.data_quality->>'score') ~ '^[0-9]+(\\.[0-9]+)?$'
                                        THEN (ev.data_quality->>'score')::DOUBLE PRECISION
                                        ELSE 0
                                    END
                                )
                                FROM adaptive_signal_evidence ev
                                WHERE ev.signal_id = s.signal_id
                            ), 0) AS data_quality_score,
                            (
                                SELECT ev.profile_id
                                FROM adaptive_signal_evidence ev
                                WHERE ev.signal_id = s.signal_id AND ev.profile_id IS NOT NULL
                                ORDER BY ev.created_at DESC
                                LIMIT 1
                            ) AS profile_id
                        FROM signals s
                        JOIN outcomes o ON o.signal_id = s.signal_id
                        WHERE s.created_at >= :cutoff
                          AND o.r_multiple IS NOT NULL
                          AND o.closed_at IS NOT NULL
                          AND o.performance_inclusion_status='eligible'
                        ORDER BY s.created_at, s.signal_id
                        """
                        ),
                        {"cutoff": cutoff},
                    )
                )
                .mappings()
                .all()
            )

            dataset_rows, manifest = build_dataset([dict(row) for row in raw_rows])
            await session.execute(
                text(
                    """
                    INSERT INTO adaptive_dataset_versions(
                        dataset_version, content_hash, row_count, first_decision_at, last_decision_at,
                        evidence_categories, assets, sequence_coverage, manifest
                    ) VALUES(
                        :version, :content_hash, :row_count, :first_at, :last_at,
                        CAST(:categories AS JSONB), CAST(:assets AS JSONB), :coverage, CAST(:manifest AS JSONB)
                    ) ON CONFLICT(dataset_version) DO NOTHING
                    """
                ),
                {
                    "version": manifest.dataset_version,
                    "content_hash": manifest.content_hash,
                    "row_count": manifest.row_count,
                    "first_at": manifest.first_decision_time.replace(tzinfo=None) if manifest.first_decision_time else None,
                    "last_at": manifest.last_decision_time.replace(tzinfo=None) if manifest.last_decision_time else None,
                    "categories": json.dumps(list(manifest.evidence_categories)),
                    "assets": json.dumps(list(manifest.assets)),
                    "coverage": manifest.sequence_coverage,
                    "manifest": json.dumps(manifest.to_dict()),
                },
            )
            await session.execute(
                text(
                    """
                    INSERT INTO adaptive_feature_versions(feature_version, content_hash, component_versions, feature_schema)
                    VALUES(:version, :content_hash, CAST(:components AS JSONB), CAST(:schema AS JSONB))
                    ON CONFLICT(feature_version) DO NOTHING
                    """
                ),
                {
                    "version": feature_version,
                    "content_hash": feature_hash,
                    "components": json.dumps(component_versions),
                    "schema": json.dumps(
                        {"market_context": "v1", "strategy_evidence": "v1", "sequence_reference": "v1"}
                    ),
                },
            )
            await session.execute(
                text(
                    """
                    INSERT INTO adaptive_optimisation_runs(
                        run_id, status, mode, dataset_version, feature_version, started_at, config, summary
                    ) VALUES(
                        :run_id, 'RUNNING', 'sequence_profile_wfo', :dataset_version, :feature_version,
                        NOW(), CAST(:config AS JSONB), '{}'::jsonb
                    )
                    """
                ),
                {
                    "run_id": run_id,
                    "dataset_version": manifest.dataset_version,
                    "feature_version": feature_version,
                    "config": json.dumps(
                        {
                            "lookback_days": lookback_days,
                            "minimum_samples": minimum_samples,
                            "automatic_live_promotion": False,
                            "chronological_validation": True,
                        }
                    ),
                },
            )

            code_commit = str(os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("GITHUB_SHA") or "unknown")
            hypothesis_id = await register_hypothesis(
                session, trial_family="adaptive_outcome_family_regime_weighting",
                spec={"strategy_family": "adaptive_profile_weighting", "mechanism_status": "mechanism_unproven",
                      "economic_mechanism": None, "reason_edge_should_exist": None,
                      "known_failure_modes": ["selection_bias", "overlapping_outcomes", "cost_proxy", "regime_shift"],
                      "description": "Bounded family/regime participation learned from earlier resolved outcomes"},
                code_commit=code_commit, created_by="adaptive_learning_worker",
            )
            by_asset: dict[tuple[str, str, str], list[AdaptiveDatasetRow]] = defaultdict(list)
            for row in dataset_rows:
                by_asset[(row.asset, row.asset_class, row.evidence_category)].append(row)

            created = 0
            duplicates = 0
            terminal_trials_skipped = 0
            failed_trials_skipped = 0
            wfo_runs = 0
            for (asset, asset_class, evidence_category), asset_rows in by_asset.items():
                if len(asset_rows) < minimum_samples:
                    continue
                family_weights, regime_weights, evidence_summary = _derive_weights(asset_rows, minimum_samples)
                if not family_weights:
                    continue
                experiment_id = await start_experiment(
                    session, hypothesis_id=hypothesis_id, strategy_id="adaptive_profile_weighting", strategy_version="v2",
                    specification={"parameter_set": {"family_weights": family_weights, "regime_weights": regime_weights,
                                                     "minimum_segment_samples": minimum_samples,
                                                     "minimum_train": max(60, int(os.getenv("ADAPTIVE_WFO_MINIMUM_TRAIN_ROWS", "80") or 80)),
                                                     "validation_size": max(20, int(os.getenv("ADAPTIVE_WFO_VALIDATION_ROWS", "30") or 30)),
                                                     "embargo_seconds": max(0, int(os.getenv("ADAPTIVE_WFO_EMBARGO_SECONDS", "0") or 0)),
                                                     "cost_r": max(0.0, float(os.getenv("ADAPTIVE_WFO_COST_R", "0.01") or 0.01))},
                                   "dataset_version": manifest.dataset_version, "feature_version": feature_version,
                                   "label_version": "resolved_R_with_correction_availability_v2",
                                   "execution_model_version": "outcome_weighting_proxy_v2",
                                   "risk_model_version": "bounded_participation_v1", "code_commit": code_commit,
                                   "random_seed": 0, "asset_scope": [asset],
                                   "timeframe_scope": sorted({row.timeframe for row in asset_rows}),
                                   "regime_scope": sorted({row.regime for row in asset_rows}),
                                   "evidence_category": evidence_category},
                )
                # A crash must not erase an attempted trial. Commit the definition
                # before evaluation, then reacquire the worker transaction lock.
                await session.commit()
                await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('signalrankai_adaptive_learning'))"))
                terminal = (await session.execute(text(
                    "SELECT status FROM research_experiment_results WHERE experiment_id=:id"), {"id": experiment_id})).scalar_one_or_none()
                if terminal is not None:
                    terminal_trials_skipped += 1
                    if terminal == "FAILED":
                        failed_trials_skipped += 1
                    else:
                        duplicates += 1
                    continue
                async with _record_evaluation_failure(session, experiment_id, run_id):
                    wfo = walk_forward_evaluate(
                        asset_rows,
                        family_weights=family_weights,
                        regime_weights=regime_weights,
                        minimum_train=max(60, int(os.getenv("ADAPTIVE_WFO_MINIMUM_TRAIN_ROWS", "80") or 80)),
                        validation_size=max(20, int(os.getenv("ADAPTIVE_WFO_VALIDATION_ROWS", "30") or 30)),
                        embargo_seconds=max(0, int(os.getenv("ADAPTIVE_WFO_EMBARGO_SECONDS", "0") or 0)),
                        cost_r=max(0.0, float(os.getenv("ADAPTIVE_WFO_COST_R", "0.01") or 0.01)),
                    )
                    fingerprint = _profile_fingerprint(
                        asset=asset,
                        dataset_version=manifest.dataset_version,
                        feature_version=feature_version,
                        family_weights=family_weights,
                        regime_weights=regime_weights,
                        evidence_category=evidence_category,
                    )
                    exists = bool(
                        (
                            await session.execute(
                                text(
                                    """
                                    SELECT 1 FROM adaptive_asset_profiles
                                    WHERE asset=:asset
                                      AND metadata->>'profile_fingerprint'=:fingerprint
                                    LIMIT 1
                                    """
                                ),
                                {"asset": asset, "fingerprint": fingerprint},
                            )
                        ).scalar()
                    )
                    if exists:
                        await complete_experiment(session, experiment_id,
                            {"reason": "existing_profile_fingerprint", "promotion_eligible": False,
                             "profile_fingerprint": fingerprint, "walk_forward": wfo.to_dict()}, status="REJECTED")
                        duplicates += 1
                        continue

                    version = int(
                        (
                            await session.execute(
                                text(
                                    "SELECT COALESCE(MAX(version), 0) + 1 FROM adaptive_asset_profiles WHERE asset=:asset"
                                ),
                                {"asset": asset},
                            )
                        ).scalar()
                        or 1
                    )
                    profile_id = f"{asset}:adaptive:{fingerprint[:12]}"
                    metadata = {
                        **evidence_summary,
                        "evidence_source": "chronological_outcomes_and_sequence_references",
                        "dataset_version": manifest.dataset_version,
                        "feature_version": feature_version,
                        "sequence_coverage": manifest.sequence_coverage,
                        "profile_fingerprint": fingerprint,
                        "walk_forward": wfo.to_dict(),
                        "requires_sequence_wfo": not bool(wfo.fold_count),
                        "automatic_live_promotion": False,
                        "human_approval_required": True,
                        "brier_score": None,
                        "research_experiment_id": experiment_id,
                        "evidence_category": evidence_category,
                    }
                    counts = await trial_counts(session, hypothesis_id)
                    research_evidence = {
                        "hypothesis_id": hypothesis_id, "experiment_id": experiment_id,
                        "dataset_version": manifest.dataset_version, "feature_version": feature_version,
                        "code_commit": code_commit, "trial_counts": counts,
                        "integrity": audit_adaptive_dataset(asset_rows, wfo),
                        "return_diagnostics": return_diagnostics([row.r_multiple for row in asset_rows]),
                        "multiple_testing": {"status": "UNVERIFIED", "deflated_sharpe_probability": None,
                                             "reason": "irregular_trade_R_and_incomplete_historical_trial_coverage"},
                        "survival": block_bootstrap_survival([row.r_multiple for row in asset_rows], risk_fraction=0.005,
                                                            block_size=min(10, len(asset_rows)), horizon=100, runs=100, seed=0),
                        "promotion_eligible": False,
                        "walk_forward": wfo.to_dict(), "evidence_category": evidence_category,
                    }
                    await complete_experiment(session, experiment_id, research_evidence)
                    metadata["research_validation"] = research_evidence
                    await session.execute(
                        text(
                            """
                            INSERT INTO adaptive_asset_profiles(
                                profile_id, asset, asset_class, version, state, source_scope, is_current,
                                family_weights, regime_weights, minimum_confidence, minimum_reward_risk,
                                maximum_score_multiplier, minimum_score_multiplier, data_sufficiency_score,
                                sample_size, metadata, created_at, updated_at
                            ) VALUES(
                                :profile_id, :asset, :asset_class, :version, 'SHADOW', 'asset', FALSE,
                                CAST(:family_weights AS JSONB), CAST(:regime_weights AS JSONB), 0.70, 1.5,
                                1.15, 0.85, :sufficiency, :sample_size, CAST(:metadata AS JSONB), NOW(), NOW()
                            ) ON CONFLICT(profile_id) DO NOTHING
                            """
                        ),
                        {
                            "profile_id": profile_id,
                            "asset": asset,
                            "asset_class": asset_class,
                            "version": version,
                            "family_weights": json.dumps(family_weights),
                            "regime_weights": json.dumps(regime_weights),
                            "sufficiency": min(1.0, len(asset_rows) / max(minimum_samples * 4, 1)),
                            "sample_size": len(asset_rows),
                            "metadata": json.dumps(metadata),
                        },
                    )
                    wfo_run_id = str(uuid4())
                    await session.execute(
                        text(
                            """
                            INSERT INTO adaptive_walk_forward_runs(
                                run_id, profile_id, dataset_version, feature_version, status,
                                started_at, completed_at, config, metrics, folds
                            ) VALUES(
                                :run_id, :profile_id, :dataset_version, :feature_version, 'COMPLETED',
                                NOW(), NOW(), CAST(:config AS JSONB), CAST(:metrics AS JSONB), CAST(:folds AS JSONB)
                            )
                            """
                        ),
                        {
                            "run_id": wfo_run_id,
                            "profile_id": profile_id,
                            "dataset_version": manifest.dataset_version,
                            "feature_version": feature_version,
                            "config": json.dumps(
                                {
                                    "chronological": True,
                                    "embargo_seconds": int(os.getenv("ADAPTIVE_WFO_EMBARGO_SECONDS", "0") or 0),
                                }
                            ),
                            "metrics": json.dumps({key: value for key, value in wfo.to_dict().items() if key != "folds"}),
                            "folds": json.dumps(
                                [asdict(fold) for fold in wfo.folds]
                            ),
                        },
                    )
                    created += 1
                    wfo_runs += 1

            await session.execute(
                text(
                    """
                    UPDATE adaptive_optimisation_runs
                    SET status='COMPLETED', completed_at=NOW(), summary=CAST(:summary AS JSONB)
                    WHERE run_id=:run_id
                    """
                ),
                {
                    "run_id": run_id,
                    "summary": json.dumps(
                        {
                            "rows": len(dataset_rows),
                            "assets": len(by_asset),
                            "candidates": created,
                            "duplicates_skipped": duplicates,
                            "terminal_trials_skipped": terminal_trials_skipped,
                            "failed_trials_skipped": failed_trials_skipped,
                            "walk_forward_runs": wfo_runs,
                            "dataset_version": manifest.dataset_version,
                            "feature_version": feature_version,
                            "sequence_coverage": manifest.sequence_coverage,
                            "drift": drift_result,
                        }
                    ),
                },
            )
            await session.commit()

        logger.info(
            "[adaptive_learning] run=%s rows=%s candidates=%s duplicates=%s wfo=%s dataset=%s",
            run_id,
            len(dataset_rows),
            created,
            duplicates,
            wfo_runs,
            manifest.dataset_version,
        )
        return {
            "published": published,
            "candidates": created,
            "duplicates_skipped": duplicates,
            "terminal_trials_skipped": terminal_trials_skipped,
            "failed_trials_skipped": failed_trials_skipped,
            "walk_forward_runs": wfo_runs,
            "rows": len(dataset_rows),
            "run_id": run_id,
            "dataset_version": manifest.dataset_version,
            "feature_version": feature_version,
            "sequence_coverage": manifest.sequence_coverage,
            "drift": drift_result,
        }
