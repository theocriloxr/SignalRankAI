from __future__ import annotations

import hashlib
import json
import logging
import os
from collections import defaultdict
from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from db.session import get_session
from core.redis_state import state
from utils.timeutils import now_utc_naive

from .components import DEFAULT_COMPONENTS
from .dataset import AdaptiveDatasetRow, build_dataset
from .repository import publish_approved_profiles
from .walk_forward import walk_forward_evaluate

logger = logging.getLogger(__name__)


def _profit_factor(values: list[float]) -> float:
    wins = sum(value for value in values if value > 0)
    loss = abs(sum(value for value in values if value < 0))
    return wins / loss if loss else (999.0 if wins else 0.0)


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
) -> str:
    payload = {
        "asset": asset,
        "dataset_version": dataset_version,
        "feature_version": feature_version,
        "family_weights": family_weights,
        "regime_weights": regime_weights,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _derive_weights(rows: list[AdaptiveDatasetRow], minimum_samples: int) -> tuple[dict[str, float], dict[str, float], dict[str, Any]]:
    by_family: dict[str, list[float]] = defaultdict(list)
    by_regime: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_family[row.family].append(row.r_multiple)
        by_regime[row.regime].append(row.r_multiple)

    def bounded_weight(values: list[float]) -> float:
        expectancy = sum(values) / len(values)
        reliability = min(1.0, len(values) / max(minimum_samples * 3, 1))
        weight = 1.0 + max(-0.15, min(0.15, expectancy * 0.08)) * reliability
        if _profit_factor(values) < 1.0 or _max_drawdown(values) > float(os.getenv("ADAPTIVE_SEGMENT_MAX_DRAWDOWN_R", "12") or 12):
            weight = min(weight, 0.90)
        return round(max(0.80, min(1.15, weight)), 4)

    family_weights = {family: bounded_weight(values) for family, values in by_family.items() if len(values) >= minimum_samples}
    regime_weights = {regime: bounded_weight(values) for regime, values in by_regime.items() if len(values) >= minimum_samples}
    all_returns = [row.r_multiple for row in rows]
    summary = {
        "sample_size": len(rows),
        "mean_expectancy_r": sum(all_returns) / len(all_returns) if all_returns else 0.0,
        "profit_factor": _profit_factor(all_returns),
        "max_drawdown_r": _max_drawdown(all_returns),
        "family_segments": {key: len(value) for key, value in by_family.items()},
        "regime_segments": {key: len(value) for key, value in by_regime.items()},
    }
    return family_weights, regime_weights, summary


async def _monitor_runtime_profiles(session: Any) -> dict[str, Any]:
    """Suspend degraded runtime profiles using confirmed live-delivery evidence only."""
    minimum_live = max(20, int(os.getenv("ADAPTIVE_DRIFT_MIN_LIVE_SAMPLES", "30") or 30))
    drawdown_limit = max(1.0, float(os.getenv("ADAPTIVE_DRIFT_MAX_DRAWDOWN_R", "10") or 10))
    brier_limit = max(0.05, min(1.0, float(os.getenv("ADAPTIVE_DRIFT_MAX_BRIER", "0.35") or 0.35)))
    expectancy_floor = float(os.getenv("ADAPTIVE_DRIFT_MIN_EXPECTANCY_R", "-0.10") or -0.10)
    rows = (
        await session.execute(
            text(
                """
                SELECT p.profile_id,p.asset,p.state,p.rollback_profile_id,
                       MAX(ev.confidence) AS confidence,o.r_multiple,s.created_at,s.signal_id
                FROM adaptive_asset_profiles p
                JOIN adaptive_signal_evidence ev ON ev.profile_id=p.profile_id
                JOIN signals s ON s.signal_id=ev.signal_id
                JOIN outcomes o ON o.signal_id=s.signal_id
                WHERE p.is_current=TRUE
                  AND p.state IN ('CANARY','LIMITED_LIVE','APPROVED')
                  AND o.r_multiple IS NOT NULL
                  AND EXISTS (
                      SELECT 1 FROM signal_deliveries sd
                      WHERE sd.signal_id=s.signal_id
                        AND sd.sent_ok=TRUE
                        AND UPPER(COALESCE(sd.delivery_state,''))='CONFIRMED'
                  )
                  AND s.created_at >= NOW() - INTERVAL '120 days'
                GROUP BY p.profile_id,p.asset,p.state,p.rollback_profile_id,o.r_multiple,s.created_at,s.signal_id
                ORDER BY p.profile_id,s.created_at DESC
                """
            )
        )
    ).mappings().all()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    profile_meta: dict[str, dict[str, Any]] = {}
    for row in rows:
        profile_id = str(row["profile_id"])
        if len(grouped[profile_id]) < 250:
            grouped[profile_id].append(dict(row))
        profile_meta[profile_id] = dict(row)

    suspended: list[str] = []
    restored: list[str] = []
    for profile_id, evidence_rows in grouped.items():
        if len(evidence_rows) < minimum_live:
            continue
        returns = [float(row["r_multiple"]) for row in reversed(evidence_rows)]
        expectancy = sum(returns) / len(returns)
        drawdown = _max_drawdown(returns)
        brier = sum(
            (max(0.0, min(1.0, float(row.get("confidence") or 0.0))) - (1.0 if float(row["r_multiple"]) > 0 else 0.0)) ** 2
            for row in evidence_rows
        ) / len(evidence_rows)
        reasons: list[str] = []
        if expectancy < expectancy_floor:
            reasons.append("live_expectancy_below_floor")
        if drawdown > drawdown_limit:
            reasons.append("live_drawdown_above_limit")
        if brier > brier_limit:
            reasons.append("live_calibration_drift")
        if not reasons:
            continue
        meta = profile_meta[profile_id]
        asset = str(meta["asset"])
        rollback_profile_id = meta.get("rollback_profile_id")
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
                "details": json.dumps({"reasons": reasons, "sample_size": len(evidence_rows), "expectancy_r": expectancy, "max_drawdown_r": drawdown, "brier_score": brier}),
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
                "metrics": json.dumps({"reasons": reasons, "sample_size": len(evidence_rows), "expectancy_r": expectancy, "max_drawdown_r": drawdown, "brier_score": brier}),
                "resolution": "rollback" if rollback_profile_id else "neutral_fallback",
            },
        )
        suspended.append(asset)
        if rollback_profile_id:
            restored_count = (
                await session.execute(
                    text(
                        """
                        UPDATE adaptive_asset_profiles
                        SET is_current=TRUE,updated_at=NOW()
                        WHERE profile_id=:rollback_profile_id
                          AND state IN ('CANARY','LIMITED_LIVE','APPROVED')
                        RETURNING profile_id
                        """
                    ),
                    {"rollback_profile_id": rollback_profile_id},
                )
            ).scalar()
            if restored_count:
                restored.append(str(restored_count))
    return {"suspended_assets": suspended, "restored_profiles": restored}


class AdaptiveLearningWorker:
    async def run_once(self) -> dict[str, Any]:
        published = await publish_approved_profiles()
        paused = str(state.get_sync("adaptive:optimisation:paused") or "0").strip().lower() in {"1", "true", "yes", "on"}
        if paused:
            return {"published": published, "candidates": 0, "paused": True}
        if str(os.getenv("ADAPTIVE_OPTIMISATION_ENABLED", "1")).lower() not in {"1", "true", "yes", "on"}:
            return {"published": published, "candidates": 0, "disabled": True}

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
                            EXISTS (
                                SELECT 1 FROM signal_deliveries sd
                                WHERE sd.signal_id = s.signal_id
                                  AND sd.sent_ok = TRUE
                                  AND UPPER(COALESCE(sd.delivery_state, '')) = 'CONFIRMED'
                            ) AS delivered,
                            EXISTS (
                                SELECT 1 FROM trades t
                                WHERE t.signal_id = s.signal_id
                            ) AS executed,
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
                        ORDER BY s.created_at, s.signal_id
                        """
                    ),
                    {"cutoff": cutoff},
                )
            ).mappings().all()

            dataset_rows, manifest = build_dataset(raw_rows)
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
                    "first_at": manifest.first_decision_time,
                    "last_at": manifest.last_decision_time,
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
                    "schema": json.dumps({"market_context": "v1", "strategy_evidence": "v1", "sequence_reference": "v1"}),
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

            drift_result = await _monitor_runtime_profiles(session)

            by_asset: dict[tuple[str, str], list[AdaptiveDatasetRow]] = defaultdict(list)
            for row in dataset_rows:
                by_asset[(row.asset, row.asset_class)].append(row)

            created = 0
            duplicates = 0
            wfo_runs = 0
            for (asset, asset_class), asset_rows in by_asset.items():
                if len(asset_rows) < minimum_samples:
                    continue
                family_weights, regime_weights, evidence_summary = _derive_weights(asset_rows, minimum_samples)
                if not family_weights:
                    continue
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
                    duplicates += 1
                    continue

                version = int(
                    (
                        await session.execute(
                            text("SELECT COALESCE(MAX(version), 0) + 1 FROM adaptive_asset_profiles WHERE asset=:asset"),
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
                }
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
                        "config": json.dumps({"chronological": True, "embargo_seconds": int(os.getenv("ADAPTIVE_WFO_EMBARGO_SECONDS", "0") or 0)}),
                        "metrics": json.dumps({key: value for key, value in wfo.to_dict().items() if key != "folds"}),
                        "folds": json.dumps([fold.__dict__ if hasattr(fold, "__dict__") else {
                            "fold": fold.fold,
                            "train_count": fold.train_count,
                            "validation_count": fold.validation_count,
                            "train_end": fold.train_end,
                            "validation_start": fold.validation_start,
                            "validation_end": fold.validation_end,
                            "baseline_expectancy_r": fold.baseline_expectancy_r,
                            "candidate_expectancy_r": fold.candidate_expectancy_r,
                            "candidate_profit_factor": fold.candidate_profit_factor,
                            "candidate_max_drawdown_r": fold.candidate_max_drawdown_r,
                            "positive": fold.positive,
                        } for fold in wfo.folds]),
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

        if drift_result.get("suspended_assets"):
            for suspended_asset in drift_result["suspended_assets"]:
                from .repository import invalidate_profile_cache
                invalidate_profile_cache(suspended_asset)
            published = await publish_approved_profiles()

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
            "walk_forward_runs": wfo_runs,
            "rows": len(dataset_rows),
            "run_id": run_id,
            "dataset_version": manifest.dataset_version,
            "feature_version": feature_version,
            "sequence_coverage": manifest.sequence_coverage,
            "drift": drift_result,
        }
