from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import text

from db.session import get_session, is_db_configured

logger = logging.getLogger(__name__)

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


def _win_bucket_expr() -> str:
    return "lower(COALESCE(o.canonical_outcome, o.status, ''))"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _api_key() -> str:
    return (os.getenv("OPENAI_API_KEY") or os.getenv("CODEX_OPENAI_API_KEY") or "").strip()


def _extract_json_response(payload: dict[str, Any]) -> dict[str, Any]:
    chunks: list[str] = []
    for item in payload.get("output") or []:
        for part in item.get("content") or []:
            if part.get("type") in {"output_text", "text"}:
                chunks.append(str(part.get("text") or ""))
    if not chunks and payload.get("output_text"):
        chunks.append(str(payload.get("output_text") or ""))
    text_value = "\n".join(chunks).strip()
    try:
        return json.loads(text_value)
    except Exception:
        start = text_value.find("{")
        end = text_value.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text_value[start : end + 1])
            except Exception:
                return {}
    return {}


def _aggregate_only_context(context: dict[str, Any]) -> dict[str, Any]:
    """Strip context to non-user, non-signal aggregate metrics for external AI."""
    return {
        "days": context.get("days"),
        "summary": context.get("summary") or {},
        "segments": [
            {
                "asset_class": row.get("asset_class"),
                "timeframe": row.get("timeframe"),
                "strategy_name": row.get("strategy_name"),
                "outcomes": row.get("outcomes"),
                "wins": row.get("wins"),
                "losses": row.get("losses"),
                "avg_r": row.get("avg_r"),
            }
            for row in list(context.get("segments") or [])[:12]
        ],
        "top_rejections": [
            {"reason": row.get("reason"), "count": row.get("n")}
            for row in list(context.get("top_rejections") or [])[:12]
        ],
        "same_asset_deliveries_12h": context.get("same_asset_deliveries_12h"),
        "deliveries": context.get("deliveries") or {},
    }


async def run_external_codex_aggregate_review(context: dict[str, Any]) -> dict[str, Any] | None:
    """Optional OpenAI review using approved aggregate-only, anonymized metrics."""
    if not _env_bool("OPENAI_CODEX_REVIEW_ENABLED", False):
        return None
    key = _api_key()
    if not key:
        return {"ok": False, "error": "OPENAI_API_KEY not configured"}

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "assessment": {"type": "string"},
            "highest_risk_findings": {"type": "array", "items": {"type": "string"}},
            "recommended_env_tweaks": {"type": "array", "items": {"type": "string"}},
            "recommended_code_changes": {"type": "array", "items": {"type": "string"}},
            "do_not_change_without_forward_test": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "assessment",
            "highest_risk_findings",
            "recommended_env_tweaks",
            "recommended_code_changes",
            "do_not_change_without_forward_test",
        ],
    }
    body = {
        "model": (os.getenv("OPENAI_CODEX_REVIEW_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip(),
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You are a conservative trading-systems governance reviewer. "
                            "Analyze aggregate metrics only. Do not claim future win rates. "
                            "Recommend testable safeguards and rollout flags."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(_aggregate_only_context(context), default=str)[:16000],
                    }
                ],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "signalrank_codex_governance",
                "schema": schema,
                "strict": True,
            }
        },
        "max_output_tokens": int(os.getenv("OPENAI_CODEX_REVIEW_MAX_TOKENS", "1200") or 1200),
    }
    try:
        async with httpx.AsyncClient(timeout=float(os.getenv("OPENAI_CODEX_REVIEW_TIMEOUT_SECONDS", "25") or 25)) as client:
            response = await client.post(
                OPENAI_RESPONSES_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=body,
            )
            response.raise_for_status()
        return {"ok": True, "review": _extract_json_response(response.json()), "data_scope": "aggregate_only"}
    except Exception as exc:
        logger.warning("[codex_governance] external aggregate review failed: %s", exc)
        return {"ok": False, "error": str(exc), "data_scope": "aggregate_only"}


async def collect_codex_governance_context(days: int = 30, limit: int = 12) -> dict[str, Any]:
    """Collect production evidence without sending data to any external service."""
    if not is_db_configured():
        return {"ok": False, "error": "database not configured"}
    since = datetime.utcnow() - timedelta(days=max(1, int(days)))
    outcome_bucket = _win_bucket_expr()
    async with get_session() as session:
        summary = (
            await session.execute(
                text(
                    f"""
                    SELECT COUNT(DISTINCT s.signal_id) AS signals,
                           COUNT(o.id) AS outcomes,
                           SUM(CASE WHEN {outcome_bucket} IN ('tp','tp1','tp2','tp3','partial_tp','win') THEN 1 ELSE 0 END) AS wins,
                           SUM(CASE WHEN {outcome_bucket} IN ('sl','loss','stop_loss') THEN 1 ELSE 0 END) AS losses,
                           SUM(CASE WHEN {outcome_bucket} IN ('time_stop','expired') THEN 1 ELSE 0 END) AS time_stops,
                           AVG(COALESCE(o.r_multiple, 0)) AS avg_r
                    FROM signals s
                    LEFT JOIN outcomes o ON o.signal_id = s.signal_id
                    WHERE s.created_at >= :since
                    """
                ),
                {"since": since},
            )
        ).mappings().first()
        by_segment = (
            await session.execute(
                text(
                    f"""
                    SELECT COALESCE(s.asset_class, 'unknown') AS asset_class,
                           COALESCE(s.timeframe, 'unknown') AS timeframe,
                           COALESCE(s.strategy_name, 'unknown') AS strategy_name,
                           COUNT(o.id) AS outcomes,
                           SUM(CASE WHEN {outcome_bucket} IN ('tp','tp1','tp2','tp3','partial_tp','win') THEN 1 ELSE 0 END) AS wins,
                           SUM(CASE WHEN {outcome_bucket} IN ('sl','loss','stop_loss') THEN 1 ELSE 0 END) AS losses,
                           AVG(COALESCE(o.r_multiple, 0)) AS avg_r
                    FROM outcomes o
                    JOIN signals s ON s.signal_id = o.signal_id
                    WHERE o.closed_at >= :since
                    GROUP BY 1,2,3
                    HAVING COUNT(o.id) > 0
                    ORDER BY outcomes DESC
                    LIMIT :limit
                    """
                ),
                {"since": since, "limit": int(limit)},
            )
        ).mappings().all()
        rejections = (
            await session.execute(
                text(
                    """
                    SELECT COALESCE(rejection_reason, 'unknown') AS reason, COUNT(*) AS n
                    FROM ml_rejected_signals
                    WHERE created_at >= :since
                    GROUP BY 1
                    ORDER BY n DESC
                    LIMIT :limit
                    """
                ),
                {"since": since, "limit": int(limit)},
            )
        ).mappings().all()
        duplicates = (
            await session.execute(
                text(
                    """
                    WITH sent AS (
                        SELECT sd.user_id, s.asset, sd.signal_id, sd.delivered_at,
                               LAG(sd.delivered_at) OVER (PARTITION BY sd.user_id, s.asset ORDER BY sd.delivered_at) AS prev_delivered_at
                        FROM signal_deliveries sd
                        JOIN signals s ON s.signal_id = sd.signal_id
                        WHERE sd.sent_ok IS TRUE AND sd.delivered_at >= :since
                    )
                    SELECT COUNT(*) AS same_asset_deliveries_12h
                    FROM sent
                    WHERE prev_delivered_at IS NOT NULL
                      AND delivered_at <= prev_delivered_at + INTERVAL '12 hours'
                    """
                ),
                {"since": since},
            )
        ).mappings().first()
        deliveries = (
            await session.execute(
                text(
                    """
                    SELECT COUNT(*) AS reserved,
                           SUM(CASE WHEN sent_ok IS TRUE THEN 1 ELSE 0 END) AS sent_ok,
                           SUM(CASE WHEN sent_ok IS FALSE THEN 1 ELSE 0 END) AS reserved_not_confirmed
                    FROM signal_deliveries
                    WHERE delivered_at >= :since
                    """
                ),
                {"since": since},
            )
        ).mappings().first()
        await session.commit()
    return {
        "ok": True,
        "days": int(days),
        "summary": dict(summary or {}),
        "segments": [dict(row) for row in by_segment],
        "top_rejections": [dict(row) for row in rejections],
        "same_asset_deliveries_12h": int((duplicates or {}).get("same_asset_deliveries_12h") or 0),
        "deliveries": dict(deliveries or {}),
    }


def build_local_codex_recommendations(context: dict[str, Any]) -> dict[str, Any]:
    summary = dict(context.get("summary") or {})
    deliveries = dict(context.get("deliveries") or {})
    segments = list(context.get("segments") or [])
    findings: list[str] = []
    env_tweaks: list[str] = []
    code_changes: list[str] = []
    holdouts: list[str] = []

    outcomes = int(summary.get("outcomes") or 0)
    wins = int(summary.get("wins") or 0)
    losses = int(summary.get("losses") or 0)
    win_rate = (wins / max(1, wins + losses)) * 100.0 if (wins + losses) else 0.0
    same_asset_12h = int(context.get("same_asset_deliveries_12h") or 0)
    reserved = int(deliveries.get("reserved") or 0)
    sent_ok = int(deliveries.get("sent_ok") or 0)
    reserved_not_confirmed = int(deliveries.get("reserved_not_confirmed") or 0)

    if same_asset_12h > 0:
        findings.append(f"{same_asset_12h} same-user/same-asset deliveries occurred inside 12h.")
        env_tweaks.append("Set ASSET_REPEAT_LOCK_HOURS=12 and DELIVERY_SAME_ASSET_COOLDOWN_HOURS=12 or higher.")
        code_changes.append("Keep all delivery paths routed through record_signal_delivery and the same-asset unresolved exposure gate.")
    if reserved and reserved_not_confirmed / max(1, reserved) > 0.05:
        findings.append(f"{reserved_not_confirmed}/{reserved} delivery reservations were not confirmed sent_ok.")
        env_tweaks.append("Keep DELIVERY_INFLIGHT_RETRY_SECONDS>=300 and monitor reserved_not_sent in /qa_report.")
        code_changes.append("Treat reserved-but-unsent rows as retryable operational failures, not delivered user quota.")
    if outcomes and win_rate < 45.0:
        findings.append(f"Tracked win rate is {win_rate:.1f}% across {wins + losses} terminal outcomes.")
        env_tweaks.extend(
            [
                "Raise QUALITY_MIN_OPENAI_SCORE/GEMINI equivalent only after reviewer is configured.",
                "Prefer QUALITY_MAX_RR_FX<=3.5, QUALITY_MAX_RR_CRYPTO<=3.5, QUALITY_MAX_STOP_LOSS_PCT_CRYPTO<=2.0 for small-account safety.",
            ]
        )
        code_changes.append("Promote per-asset-class expectancy gates and demote segments with negative avg_r until forward-tested recovery.")
    weak_segments = []
    for row in segments:
        seg_wins = int(row.get("wins") or 0)
        seg_losses = int(row.get("losses") or 0)
        seg_total = seg_wins + seg_losses
        seg_wr = (seg_wins / max(1, seg_total)) * 100.0 if seg_total else 0.0
        avg_r = float(row.get("avg_r") or 0.0)
        if seg_total >= 5 and (seg_wr < 45.0 or avg_r < 0):
            weak_segments.append(
                f"{row.get('asset_class')}/{row.get('timeframe')}/{row.get('strategy_name')}: {seg_wr:.1f}% WR, avg_r={avg_r:.2f}"
            )
    if weak_segments:
        findings.append("Weak live segments: " + "; ".join(weak_segments[:5]))
        code_changes.append("Add segment-level quarantine for strategies/timeframes with enough live losses and negative expectancy.")

    holdouts.extend(
        [
            "Do not claim 65-80% expected win rate until live tracked coverage is high and stable.",
            "Do not auto-apply model/code recommendations without tests, rollout flag, and rollback path.",
            "Do not loosen dedup or risk gates to increase signal volume while win rate is degraded.",
        ]
    )

    assessment = (
        "Local Codex governance review completed without external API calls. "
        "The priority is fewer duplicate exposures, stricter small-account risk, and evidence-based segment quarantine."
    )
    return {
        "assessment": assessment,
        "highest_risk_findings": findings or ["No critical local finding from the available aggregates."],
        "recommended_env_tweaks": env_tweaks,
        "recommended_code_changes": code_changes,
        "do_not_change_without_forward_test": holdouts,
    }


async def run_codex_governance_review(trigger: str, scope: str = "weekly") -> dict[str, Any]:
    days = {"daily": 1, "weekly": 7, "monthly": 30, "all_time": 3650}.get(str(scope or "weekly").lower(), 7)
    context = await collect_codex_governance_context(days=days)
    local_review = build_local_codex_recommendations(context) if context.get("ok") else {"assessment": context.get("error")}
    external_review = await run_external_codex_aggregate_review(context) if context.get("ok") else None
    result = {
        "ok": bool(context.get("ok")),
        "trigger": trigger,
        "scope": scope,
        "finished_at": datetime.utcnow().isoformat(),
        "context": context,
        "review": local_review,
        "external_codex_review": external_review,
        "guardrail": "recommendations_only_no_unattended_code_updates",
        "external_data_scope": "aggregate_only_no_user_or_signal_ids" if external_review else "none",
    }
    if is_db_configured():
        async with get_session() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO runtime_state(key, value, expires_at, updated_at)
                    VALUES ('codex_governance_last_review', :value::jsonb, NULL, NOW())
                    ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
                    """
                ),
                {"value": json.dumps(result, default=str)},
            )
            await session.commit()
    return result


async def get_last_codex_governance_review() -> dict[str, Any] | None:
    if not is_db_configured():
        return None
    async with get_session() as session:
        row = (
            await session.execute(
                text("SELECT value FROM runtime_state WHERE key = 'codex_governance_last_review' LIMIT 1")
            )
        ).first()
        await session.commit()
    if not row:
        return None
    value = row[0]
    if isinstance(value, dict):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return {"raw": str(value)[:2000]}
