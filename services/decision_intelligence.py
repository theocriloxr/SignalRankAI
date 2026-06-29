"""Structured decision intelligence for trading signal auditability."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping


REQUIRED_SECTIONS = (
    "why_selected",
    "strategy_votes",
    "votes_against",
    "ml",
    "gemini",
    "news",
    "technicals",
    "risk",
    "market_context",
    "historical_analogs",
    "confidence_calibration",
    "shadow_agreement",
    "outcome_learning",
)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _dict_list(value: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    if value is None:
        return []
    return [dict(item) for item in value]


def _signal_id(signal: Mapping[str, Any]) -> str | None:
    return str(signal.get("signal_id") or signal.get("id") or "") or None


def build_decision_record(
    signal: Mapping[str, Any],
    *,
    strategy_votes: Iterable[Mapping[str, Any]] | None = None,
    votes_against: Iterable[Mapping[str, Any]] | None = None,
    ml_prediction: Mapping[str, Any] | None = None,
    gemini_summary: Mapping[str, Any] | str | None = None,
    news_assessment: Mapping[str, Any] | None = None,
    technicals: Mapping[str, Any] | None = None,
    risk: Mapping[str, Any] | None = None,
    market_context: Mapping[str, Any] | None = None,
    historical_analogs: Iterable[Mapping[str, Any]] | None = None,
    confidence_calibration: Mapping[str, Any] | None = None,
    shadow_prediction: Mapping[str, Any] | None = None,
    outcome_learning: Mapping[str, Any] | None = None,
    version: str = "decision-intelligence-v1",
) -> Dict[str, Any]:
    """Build a complete, serializable decision audit record."""
    asset = str(signal.get("asset") or "").upper()
    timeframe = str(signal.get("timeframe") or "")
    direction = str(signal.get("direction") or "").lower()
    score = _float(signal.get("score") or signal.get("display_score"))
    confidence = _float(signal.get("confidence") or signal.get("ml_probability") or signal.get("ml_prob"))

    votes = _dict_list(strategy_votes)
    if not votes and (signal.get("strategy_name") or signal.get("strategy")):
        votes = [
            {
                "strategy": signal.get("strategy_name") or signal.get("strategy"),
                "weight": _float(signal.get("strategy_weight"), 1.0),
                "vote": "for",
            }
        ]

    ml = dict(ml_prediction or {})
    if not ml:
        ml = {
            "probability": signal.get("ml_probability") or signal.get("ml_prob"),
            "threshold": signal.get("ml_threshold"),
            "verdict": "approve" if _float(signal.get("ml_probability") or signal.get("ml_prob")) >= 0.5 else "unknown",
        }

    if isinstance(gemini_summary, str):
        gemini = {"summary": gemini_summary}
    else:
        gemini = dict(gemini_summary or {})

    news = dict(news_assessment or {})
    risk_payload = dict(risk or {})
    if not risk_payload:
        risk_payload = {
            "risk_reward": signal.get("rr_ratio") or signal.get("rr_estimate"),
            "stop_loss": signal.get("stop_loss"),
            "position_size": signal.get("position_size"),
            "risk_score": signal.get("risk_score"),
        }

    why = [
        f"{asset} {direction.upper()} {timeframe}".strip(),
        f"score={score:.2f}",
    ]
    if votes:
        why.append(f"strategy_votes={len(votes)}")
    if ml.get("probability") is not None:
        why.append(f"ml_probability={_float(ml.get('probability')):.4f}")

    record = {
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "signal_id": _signal_id(signal),
        "asset": asset,
        "timeframe": timeframe,
        "direction": direction,
        "decision": signal.get("decision") or "issued",
        "why_selected": "; ".join(part for part in why if part),
        "strategy_votes": votes,
        "votes_against": _dict_list(votes_against),
        "ml": ml,
        "gemini": gemini,
        "news": news,
        "technicals": dict(technicals or signal.get("indicators") or {}),
        "risk": risk_payload,
        "market_context": dict(market_context or {"regime": signal.get("regime"), "session": signal.get("session")}),
        "historical_analogs": _dict_list(historical_analogs),
        "confidence_calibration": dict(
            confidence_calibration
            or {
                "raw_confidence": confidence,
                "calibrated_confidence": confidence + _float(news.get("confidence_adjustment")),
            }
        ),
        "shadow_agreement": dict(shadow_prediction or {"available": False}),
        "outcome_learning": dict(outcome_learning or {"available": False}),
    }
    return record


def validate_decision_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    missing = [section for section in REQUIRED_SECTIONS if section not in record]
    errors: list[str] = []
    if not record.get("asset"):
        errors.append("asset_missing")
    if not record.get("timeframe"):
        errors.append("timeframe_missing")
    if record.get("decision") not in {"issued", "rejected", "skipped", "delayed", "suppressed", "error"}:
        errors.append("unknown_decision")
    if missing:
        errors.append("missing_sections")
    return {"ok": not errors, "errors": errors, "missing_sections": missing}


async def persist_decision_record(record: Mapping[str, Any]) -> int:
    """Persist a structured decision record in the existing DecisionLog table."""
    from db.repository import persist_decision_log

    validation = validate_decision_record(record)
    meta = dict(record)
    meta["validation"] = validation
    return await persist_decision_log(
        signal_id=record.get("signal_id"),
        asset=record.get("asset"),
        timeframe=record.get("timeframe"),
        decision=str(record.get("decision") or "issued"),
        reason=str(record.get("why_selected") or "")[:1000],
        meta=meta,
    )


__all__ = [
    "REQUIRED_SECTIONS",
    "build_decision_record",
    "persist_decision_record",
    "validate_decision_record",
]
