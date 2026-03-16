from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.request
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text

from db.session import get_session

logger = logging.getLogger(__name__)


async def _collect_aggregate(scope: str) -> dict[str, Any]:
    scope_norm = str(scope or "weekly").strip().lower()
    if scope_norm not in {"weekly", "all_time"}:
        scope_norm = "weekly"

    since: datetime | None = None
    if scope_norm == "weekly":
        since = datetime.utcnow() - timedelta(days=7)

    where_outcomes = ""
    where_decisions = ""
    where_signals = ""
    where_decisions_with_rejects = "WHERE decision IN ('rejected','skipped')"
    params: dict[str, Any] = {}
    if since is not None:
        where_outcomes = "WHERE closed_at >= :since"
        where_decisions = "WHERE created_at >= :since"
        where_signals = "WHERE created_at >= :since"
        where_decisions_with_rejects = (
            "WHERE created_at >= :since AND decision IN ('rejected','skipped')"
        )
        params["since"] = since

    async with get_session() as session:
        perf_row = (
            await session.execute(
                text(
                    f"""
                    SELECT
                      COUNT(*) AS outcomes_total,
                      SUM(CASE WHEN status IN ('tp','tp1','tp2','tp3','partial_tp') THEN 1 ELSE 0 END) AS wins,
                      SUM(CASE WHEN status = 'sl' THEN 1 ELSE 0 END) AS losses,
                      AVG(r_multiple) AS avg_r,
                      SUM(r_multiple) AS net_r
                    FROM outcomes
                    {where_outcomes}
                    """
                ),
                params,
            )
        ).first()

        rej_rows = (
            await session.execute(
                text(
                    f"""
                    SELECT COALESCE(reason, '') AS reason, COUNT(*) AS c
                    FROM decision_log
                    {where_decisions_with_rejects}
                    GROUP BY reason
                    ORDER BY c DESC
                    LIMIT 12
                    """
                ),
                params,
            )
        ).fetchall()

        issued_rejected = (
            await session.execute(
                text(
                    f"""
                    SELECT
                      SUM(CASE WHEN decision = 'issued' THEN 1 ELSE 0 END) AS issued,
                      SUM(CASE WHEN decision IN ('rejected','skipped') THEN 1 ELSE 0 END) AS rejected
                    FROM decision_log
                    {where_decisions}
                    """
                ),
                params,
            )
        ).first()

        assets = (
            await session.execute(
                text(
                    f"""
                    SELECT asset, COUNT(*) AS c
                    FROM signals
                    {where_signals}
                    GROUP BY asset
                    ORDER BY c DESC
                    LIMIT 10
                    """
                ),
                params,
            )
        ).fetchall()

        await session.commit()

    outcomes_total = int((perf_row[0] or 0) if perf_row else 0)
    wins = int((perf_row[1] or 0) if perf_row else 0)
    losses = int((perf_row[2] or 0) if perf_row else 0)
    issued = int((issued_rejected[0] or 0) if issued_rejected else 0)
    rejected = int((issued_rejected[1] or 0) if issued_rejected else 0)

    return {
        "scope": scope_norm,
        "since_utc": since.isoformat() if since is not None else None,
        "outcomes_total": outcomes_total,
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / max(1, wins + losses)),
        "avg_r": float(perf_row[3]) if perf_row and perf_row[3] is not None else None,
        "net_r": float(perf_row[4]) if perf_row and perf_row[4] is not None else None,
        "issued": issued,
        "rejected_or_skipped": rejected,
        "top_rejections": [
            {"reason": str(r[0] or ""), "count": int(r[1] or 0)} for r in (rej_rows or [])
        ],
        "top_assets": [
            {"asset": str(r[0] or ""), "count": int(r[1] or 0)} for r in (assets or [])
        ],
    }


def _call_gemini_sync(api_key: str, prompt_payload: dict[str, Any]) -> str:
    model = (os.getenv("GEMINI_MODEL") or "gemini-1.5-pro").strip()
    req_body = {
        "contents": [{"parts": [{"text": json.dumps(prompt_payload)}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": int(os.getenv("GEMINI_REVIEW_MAX_TOKENS", "1200") or 1200),
        },
    }

    req = urllib.request.Request(
        url=(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        ),
        data=json.dumps(req_body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = int(os.getenv("GEMINI_REVIEW_HTTP_TIMEOUT_SEC", "60") or 60)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    try:
        return str(payload["candidates"][0]["content"]["parts"][0].get("text") or "").strip()
    except Exception:
        return ""


async def _train_model_with_overwrite() -> dict[str, Any]:
    from ml.train_model import main as train_main
    from utils.async_runner import run_sync

    started = datetime.utcnow().isoformat()
    try:
        # Run training in a worker thread so Telegram/webhook event loops remain responsive.
        ok = await asyncio.to_thread(lambda: bool(run_sync(train_main(), timeout=1200.0)))
        return {
            "attempted": True,
            "succeeded": bool(ok),
            "started_at": started,
            "finished_at": datetime.utcnow().isoformat(),
            "note": "model.json overwritten from latest training run" if ok else "training returned False",
        }
    except Exception as exc:
        logger.warning("[gemini] model retrain failed: %s", exc)
        return {
            "attempted": True,
            "succeeded": False,
            "started_at": started,
            "finished_at": datetime.utcnow().isoformat(),
            "note": f"training exception: {exc}",
        }


async def _store_review(key: str, value: dict[str, Any]) -> None:
    async with get_session() as session:
        await session.execute(
            text(
                """
                INSERT INTO runtime_state(key, value, expires_at, updated_at)
                VALUES (:k, :v::jsonb, NULL, NOW())
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, expires_at = NULL, updated_at = NOW()
                """
            ),
            {"k": key, "v": json.dumps(value)},
        )
        await session.commit()


async def run_gemini_review_pipeline(*, trigger: str, scope: str) -> dict[str, Any]:
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return {
            "ok": False,
            "error": "GEMINI_API_KEY is not configured",
            "trigger": trigger,
            "scope": scope,
        }

    started_at = datetime.utcnow().isoformat()
    aggregate = await _collect_aggregate(scope=scope)

    prompt_payload = {
        "task": (
            "You are a quantitative trading review assistant. Analyze the supplied aggregate stats, "
            "then provide: 1) tuning suggestions, 2) risk controls, 3) short research-style insights "
            "based on broad market best practices, 4) ML feature ideas to improve win ratio."
        ),
        "constraints": [
            "Avoid overfitting and data leakage.",
            "Use concise and actionable bullet points.",
            "Do not provide investment guarantees.",
            "Prefer robust improvements over aggressive optimization.",
        ],
        "aggregate": aggregate,
    }

    review_text = ""
    try:
        review_text = await asyncio.to_thread(_call_gemini_sync, api_key, prompt_payload)
    except Exception as exc:
        logger.warning("[gemini] review request failed: %s", exc)

    training = await _train_model_with_overwrite()

    result = {
        "ok": True,
        "trigger": str(trigger),
        "scope": str(aggregate.get("scope") or scope),
        "started_at": started_at,
        "finished_at": datetime.utcnow().isoformat(),
        "received": {
            "outcomes_total": int(aggregate.get("outcomes_total") or 0),
            "wins": int(aggregate.get("wins") or 0),
            "losses": int(aggregate.get("losses") or 0),
            "issued": int(aggregate.get("issued") or 0),
            "rejected_or_skipped": int(aggregate.get("rejected_or_skipped") or 0),
            "top_assets_count": len(aggregate.get("top_assets") or []),
            "top_rejections_count": len(aggregate.get("top_rejections") or []),
        },
        "processed": {
            "prompt_chars": len(json.dumps(prompt_payload)),
            "review_chars": len(review_text or ""),
        },
        "aggregate": aggregate,
        "review": review_text,
        "training": training,
    }

    await _store_review("gemini_ml_last_run", result)
    await _store_review(
        "gemini_weekly_ml_review",
        {
            "summary": aggregate,
            "recommendations": review_text,
            "training": training,
            "trigger": trigger,
            "scope": scope,
            "updated_at": datetime.utcnow().isoformat(),
        },
    )

    return result


async def get_last_gemini_review() -> dict[str, Any] | None:
    async with get_session() as session:
        row = (
            await session.execute(
                text("SELECT value FROM runtime_state WHERE key = :k"),
                {"k": "gemini_ml_last_run"},
            )
        ).first()
        await session.commit()

    if not row or row[0] is None:
        return None
    return dict(row[0]) if isinstance(row[0], dict) else None
