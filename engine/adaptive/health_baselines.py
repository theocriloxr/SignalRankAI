"""Approved comparisons of delivery R; never a broker-fill or edge certificate."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import time
from typing import Any, Mapping, Sequence
from uuid import uuid4

from sqlalchemy import text

from .lifecycle import lock_profile_lifecycle, health_interval_seconds
from .statistics import return_diagnostics

SCOPE = "confirmed_signal_delivery_outcomes"
CONDITIONS_VERSION = "delivery-health-conditions-v1"
PROFILE_KEYS = ("profile_id", "asset", "asset_class", "version", "source_scope",
    "preferred_families", "penalised_families", "disabled_families", "preferred_timeframes",
    "preferred_sessions", "avoided_sessions", "regime_weights", "family_weights",
    "minimum_confidence", "minimum_reward_risk", "maximum_score_multiplier", "minimum_score_multiplier")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def profile_hash(profile: Mapping[str, Any]) -> str:
    metadata = profile.get("metadata") or {}
    if not isinstance(metadata, Mapping):
        raise ValueError("invalid_profile_metadata")
    return _hash({**{key: profile.get(key) for key in PROFILE_KEYS},
                  "dataset_version": metadata.get("dataset_version"),
                  "feature_version": metadata.get("feature_version")})


@dataclass(frozen=True)
class HealthConditions:
    """All limits are explicitly chosen by the owner, before runtime promotion."""
    minimum_live_samples: int
    maximum_expectancy_decay_r: float
    maximum_drawdown_r: float
    maximum_drawdown_duration_observations: int
    maximum_profit_factor_decay_fraction: float
    maximum_brier_increase: float
    calibration_required: bool

    def __post_init__(self) -> None:
        for value, lower, upper in ((self.minimum_live_samples, 20, 250),
                (self.maximum_drawdown_duration_observations, 1, 250)):
            if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
                raise ValueError("invalid_health_condition_count")
        values = (self.maximum_expectancy_decay_r, self.maximum_drawdown_r,
                  self.maximum_profit_factor_decay_fraction, self.maximum_brier_increase)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
            raise ValueError("nonfinite_health_condition")
        if self.maximum_expectancy_decay_r < 0 or self.maximum_drawdown_r <= 0:
            raise ValueError("invalid_health_condition_limit")
        if not 0 <= self.maximum_profit_factor_decay_fraction <= 1 or not 0 <= self.maximum_brier_increase <= 1:
            raise ValueError("invalid_health_condition_fraction")
        if not isinstance(self.calibration_required, bool):
            raise ValueError("invalid_calibration_requirement")


def _date(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime):
        raise ValueError("invalid_health_evidence_timestamp")
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _observations(rows: Sequence[Mapping[str, Any]]) -> tuple[list[float], str]:
    if not 1 <= len(rows) <= 250:
        raise ValueError("health_observation_window_must_be_1_to_250")
    ordered = sorted(rows, key=lambda row: (_date(row["closed_at"]), str(row["signal_id"])))
    identifiers = [str(row["signal_id"]) for row in ordered]
    if len(set(identifiers)) != len(identifiers) or any(not value for value in identifiers):
        raise ValueError("health_observations_must_be_distinct")
    values = [row["r_multiple"] for row in ordered]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError("invalid_health_returns")
    evidence = [{"signal_id": row["signal_id"], "r_multiple": row["r_multiple"],
                 "created_at": _date(row["created_at"]).isoformat(),
                 "closed_at": _date(row["closed_at"]).isoformat(),
                 "calibration_version": row.get("ml_calibration_version"),
                 "probability": row.get("ml_probability_calibrated")} for row in ordered]
    if any(_date(row["created_at"]) > _date(row["closed_at"]) for row in ordered):
        raise ValueError("health_observation_chronology_invalid")
    return [float(value) for value in values], _hash(evidence)


def build_baseline_payload(rows: list[dict[str, Any]], conditions: HealthConditions) -> dict[str, Any]:
    from .learning import _runtime_health_metrics

    values, evidence_hash = _observations(rows)
    if len(values) < max(100, conditions.minimum_live_samples):
        raise ValueError("minimum_100_approved_delivery_observations")
    # Reuse canonical calibration validation; confidence is never a probability.
    descending = sorted(rows, key=lambda row: (_date(row["closed_at"]), str(row["signal_id"])), reverse=True)
    calibration = _runtime_health_metrics(descending, minimum_live=conditions.minimum_live_samples,
        drawdown_limit=conditions.maximum_drawdown_r, brier_limit=1, expectancy_floor=-1e300)
    metrics = return_diagnostics(values)
    if any(isinstance(v, float) and not math.isfinite(v) for v in metrics.values()):
        raise ValueError("nonfinite_baseline_metric")
    if calibration["delivery_evidence_status"] == "INVALID":
        raise ValueError("invalid_baseline_calibration")
    if metrics["expectancy_r"] <= 0 or metrics["profit_factor"] is None:
        raise ValueError("positive_expectancy_and_observed_losses_required")
    if metrics["max_drawdown_r"] > conditions.maximum_drawdown_r or metrics["max_drawdown_duration_observations"] > conditions.maximum_drawdown_duration_observations:
        raise ValueError("baseline_exceeds_approved_limits")
    if conditions.calibration_required and calibration["brier_score"] is None:
        raise ValueError("qualified_baseline_calibration_required")
    return {"metrics": {**metrics, "brier_score": calibration["brier_score"]},
        "conditions": asdict(conditions), "evidence_hash": evidence_hash,
        "calibration_versions": calibration["calibration_versions"],
        "first_decision_at": min(_date(row["created_at"]) for row in rows).isoformat(),
        "last_closed_at": max(_date(row["closed_at"]) for row in rows).isoformat(),
        "unavailable_metrics": ["time_return_sharpe", "sortino", "calmar", "trade_frequency",
            "MAE", "MFE", "slippage", "spread", "fill_rate", "latency", "regime_mix"],
        "broker_fills_certified": False, "window_limit": 250}


def baseline_valid(baseline: Mapping[str, Any] | None, profile: Mapping[str, Any]) -> bool:
    try:
        if baseline is None or baseline["evidence_scope"] != SCOPE or baseline["conditions_version"] != CONDITIONS_VERSION:
            return False
        if baseline["profile_id"] != profile["profile_id"] or baseline["profile_version"] != profile["version"]:
            return False
        if baseline["profile_hash"] != profile_hash(profile) or baseline["content_hash"] != _hash(baseline["payload"]):
            return False
        if not baseline["baseline_id"] or isinstance(baseline["approved_by"], bool) or int(baseline["approved_by"]) <= 0:
            return False
        conditions = HealthConditions(**baseline["payload"]["conditions"])
        metrics = baseline["payload"]["metrics"]
        numbers = [metrics[k] for k in ("expectancy_r", "profit_factor", "max_drawdown_r", "sample_size", "max_drawdown_duration_observations")]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in numbers):
            return False
        if metrics["expectancy_r"] <= 0 or metrics["profit_factor"] <= 0 or metrics["sample_size"] < max(100, conditions.minimum_live_samples):
            return False
        if not float(metrics["sample_size"]).is_integer() or metrics["sample_size"] > 250 or metrics["max_drawdown_r"] < 0:
            return False
        if conditions.calibration_required:
            score = metrics.get("brier_score")
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
                return False
        approved_at = _date(baseline["approved_at"])
        return _date(baseline["payload"]["last_closed_at"]) <= approved_at <= datetime.now(timezone.utc).replace(tzinfo=None)
    except (KeyError, ValueError, TypeError, OverflowError):
        return False


async def approved_baseline(session: Any, profile_id: str) -> dict[str, Any] | None:
    row = (await session.execute(text("SELECT * FROM strategy_health_baselines WHERE profile_id=:id"),
                                 {"id": profile_id})).mappings().first()
    return dict(row) if row else None


async def approve_health_baseline(session: Any, *, profile_id: str, profile_version: int,
                                  approved_by: int, conditions: HealthConditions) -> dict[str, Any]:
    if isinstance(approved_by, bool) or not isinstance(approved_by, int) or approved_by <= 0:
        raise ValueError("authenticated_owner_identity_required")
    await lock_profile_lifecycle(session)
    row = (await session.execute(text("SELECT * FROM adaptive_asset_profiles WHERE profile_id=:id FOR UPDATE"),
                                 {"id": profile_id})).mappings().first()
    if not row or row["version"] != profile_version or row["state"] not in {"SHADOW", "PAPER", "FORWARD_TEST"}:
        raise ValueError("matching_pre_promotion_profile_required")
    if await approved_baseline(session, profile_id):
        raise ValueError("immutable_baseline_already_approved_create_new_profile_version")
    observations = (await session.execute(text("""
        SELECT s.signal_id,s.created_at,o.closed_at,o.r_multiple,
               s.ml_probability_calibrated,s.ml_calibration_version,s.ml_calibration_validated,
               s.ml_calibration_validation_rows,s.ml_calibration_brier,s.ml_calibration_ece
        FROM signals s JOIN outcomes o ON o.signal_id=s.signal_id
        WHERE o.r_multiple IS NOT NULL AND o.closed_at IS NOT NULL AND o.closed_at<=NOW()
          AND s.created_at<=o.closed_at AND s.created_at>=NOW()-INTERVAL '120 days'
          AND o.performance_inclusion_status='eligible'
          AND EXISTS(SELECT 1 FROM adaptive_signal_evidence ev WHERE ev.signal_id=s.signal_id
                     AND ev.profile_id=:id AND ev.profile_version=:version)
          AND EXISTS(SELECT 1 FROM signal_deliveries sd WHERE sd.signal_id=s.signal_id
                     AND sd.sent_ok=TRUE AND UPPER(COALESCE(sd.delivery_state,''))='CONFIRMED')
        ORDER BY o.closed_at DESC,s.signal_id DESC LIMIT 250
    """), {"id": profile_id, "version": profile_version})).mappings().all()
    payload = build_baseline_payload([dict(item) for item in observations], conditions)
    identifier = uuid4().hex
    result = (await session.execute(text("""INSERT INTO strategy_health_baselines
        (baseline_id,profile_id,profile_version,profile_hash,evidence_scope,approved_by,conditions_version,payload,content_hash)
        VALUES(:baseline,:id,:version,:profile_hash,:scope,:actor,:conditions_version,CAST(:payload AS JSONB),:hash)
        RETURNING baseline_id,profile_id,profile_version,approved_at,evidence_scope
    """), {"baseline": identifier, "id": profile_id, "version": profile_version,
        "profile_hash": profile_hash(row), "scope": SCOPE, "actor": approved_by,
        "conditions_version": CONDITIONS_VERSION, "payload": _canonical(payload), "hash": _hash(payload)})).mappings().one()
    return {**dict(result), "payload": payload, "automatic_promotion": False}


def compare_health_baseline(baseline: Mapping[str, Any] | None, profile: Mapping[str, Any],
                            rows: list[dict[str, Any]]) -> dict[str, Any]:
    from .learning import _runtime_health_metrics

    result: dict[str, Any] = {"approved_baseline_comparison": "UNAVAILABLE" if baseline is None else "INVALID",
        "baseline_id": baseline.get("baseline_id") if baseline else None, "baseline_reasons": [],
        "baseline_sample_size": 0, "baseline_metrics": None, "live_comparison_metrics": None,
        "baseline_checks": {}, "broker_fills_certified": False}
    if baseline is None:
        result["baseline_reasons"] = ["approved_delivery_baseline_missing"]
        return result
    if not baseline_valid(baseline, profile):
        result["baseline_reasons"] = ["approved_delivery_baseline_invalid_or_profile_changed"]
        return result
    try:
        cutoff = _date(baseline["approved_at"])
        # An outcome of a decision preceding approval is baseline-era evidence,
        # even when it closes later. It cannot become forward validation.
        live = [row for row in rows if _date(row["created_at"]) >= cutoff]
        conditions = HealthConditions(**baseline["payload"]["conditions"])
        result.update(approved_baseline_comparison="INSUFFICIENT", baseline_sample_size=len(live),
                      baseline_metrics=baseline["payload"]["metrics"])
        if live:
            values, evidence_hash = _observations(live)
            result["comparison_evidence_hash"] = evidence_hash
        else:
            values = []
        if len(live) < conditions.minimum_live_samples:
            return result
        metrics = return_diagnostics(values)
        if any(isinstance(v, float) and not math.isfinite(v) for v in metrics.values()):
            raise ValueError("nonfinite_live_comparison")
        calibration = _runtime_health_metrics(sorted(live, key=lambda row: (_date(row["closed_at"]), str(row["signal_id"])), reverse=True),
            minimum_live=conditions.minimum_live_samples, drawdown_limit=conditions.maximum_drawdown_r,
            brier_limit=1, expectancy_floor=-1e300)
        if calibration["delivery_evidence_status"] == "INVALID":
            raise ValueError("invalid_live_calibration")
        metrics["brier_score"] = calibration["brier_score"]
        expected = baseline["payload"]["metrics"]
        checks = {"EXPECTANCY_DECAY": metrics["expectancy_r"] < expected["expectancy_r"] - conditions.maximum_expectancy_decay_r,
            "DRAWDOWN_EXCEEDED": metrics["max_drawdown_r"] > conditions.maximum_drawdown_r,
            "DRAWDOWN_DURATION_EXCEEDED": metrics["max_drawdown_duration_observations"] > conditions.maximum_drawdown_duration_observations,
            "PROFIT_FACTOR_DECAY": metrics["profit_factor"] is not None and metrics["profit_factor"] < expected["profit_factor"] * (1 - conditions.maximum_profit_factor_decay_fraction)}
        unknown = []
        if metrics["profit_factor"] is None:
            unknown.append("PROFIT_FACTOR_UNDEFINED_NO_LOSSES")
            checks["PROFIT_FACTOR_DECAY"] = None
        if conditions.calibration_required:
            # A new calibration version must earn its own forward sample; a
            # good version cannot conceal missing evidence for another one.
            versions = calibration["calibration_versions"]
            if any(item["brier_score"] is None for item in versions.values()) or not versions or calibration["calibrated_sample_size"] != len(live):
                unknown.append("CALIBRATION_COVERAGE_UNAVAILABLE")
            if metrics["brier_score"] is not None:
                checks["CALIBRATION_DECAY"] = metrics["brier_score"] > expected["brier_score"] + conditions.maximum_brier_increase
        reasons = [name for name, breached in checks.items() if breached]
        result.update(baseline_checks=checks, baseline_reasons=reasons + unknown,
            live_comparison_metrics=metrics, approved_baseline_comparison="BREACHED" if reasons else "UNAVAILABLE" if unknown else "WITHIN_LIMITS")
        return result
    except (KeyError, TypeError, ValueError, OverflowError):
        result.update(approved_baseline_comparison="INVALID", baseline_reasons=["invalid_forward_health_evidence"])
        return result


async def record_health_event(session: Any, *, profile_id: str, report: dict[str, Any]) -> None:
    # Identical retries within a cadence slot are idempotent; a later slot
    # records a new surveillance receipt even when observations are unchanged.
    slot = int(time.time() // health_interval_seconds())
    await session.execute(text("""INSERT INTO strategy_health_events(profile_id,baseline_id,event_hash,report)
        VALUES(:id,:baseline,:hash,CAST(:report AS JSONB)) ON CONFLICT(event_hash) DO NOTHING"""),
        {"id": profile_id, "baseline": report.get("baseline_id"), "hash": _hash({"profile_id": profile_id, "report": report, "slot": slot}),
         "report": _canonical(report)})


async def health_baseline_snapshot(session: Any, profile_id: str) -> dict[str, Any]:
    baseline = await approved_baseline(session, profile_id)
    events = (await session.execute(text("SELECT event_id,report,created_at FROM strategy_health_events "
        "WHERE profile_id=:id ORDER BY event_id DESC LIMIT 20"), {"id": profile_id})).mappings().all()
    return {"baseline": baseline, "events": [dict(row) for row in events], "broker_fills_certified": False}
