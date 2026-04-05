from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
import traceback
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text

from db.session import get_session

logger = logging.getLogger(__name__)

_gemini_cooldown_until_utc: datetime | None = None
_gemini_cooldown_db_loaded: bool = False  # load from DB at most once per process


def _load_cooldown_from_db() -> None:
    """Restore any active Gemini cooldown from runtime_state so Railway
    redeploys respect a previously set 429 cooldown."""
    global _gemini_cooldown_until_utc
    try:
        from utils.async_runner import run_sync as _rs

        async def _fetch() -> str | None:
            async with get_session() as _s:
                row = (
                    await _s.execute(
                        text("SELECT value FROM runtime_state WHERE key = 'gemini_cooldown_until'"),
                    )
                ).first()
                return row[0] if row else None

        val = _rs(_fetch(), timeout=5.0)
        if val:
            # value is stored as a JSONB string (quoted ISO timestamp)
            ts_str = val if isinstance(val, str) else str(val)
            ts_str = ts_str.strip('"')
            ts = datetime.fromisoformat(ts_str)
            if ts > datetime.utcnow():
                _gemini_cooldown_until_utc = ts
                logger.info("[gemini] cooldown restored from DB: until=%s", ts.isoformat())
    except Exception as _e:
        logger.debug("[gemini] cooldown load from DB failed (non-fatal): %s", _e)


def _persist_cooldown_to_db() -> None:
    """Write the current cooldown expiry to runtime_state so it survives restarts."""
    global _gemini_cooldown_until_utc
    if _gemini_cooldown_until_utc is None:
        return
    try:
        from utils.async_runner import run_sync as _rs

        _until_iso = json.dumps(_gemini_cooldown_until_utc.isoformat())

        async def _save() -> None:
            async with get_session() as _s:
                await _s.execute(
                    text(
                        """
                        INSERT INTO runtime_state(key, value, expires_at, updated_at)
                        VALUES (:k, CAST(:v AS JSONB), NULL, NOW())
                        ON CONFLICT (key) DO UPDATE
                        SET value = EXCLUDED.value, updated_at = NOW()
                        """
                    ),
                    {"k": "gemini_cooldown_until", "v": _until_iso},
                )
                await _s.commit()

        _rs(_save(), timeout=5.0)
    except Exception as _e:
        logger.debug("[gemini] cooldown persist to DB failed (non-fatal): %s", _e)


def _gemini_in_cooldown() -> tuple[bool, str | None]:
    global _gemini_cooldown_until_utc, _gemini_cooldown_db_loaded
    # Restore from DB exactly once per process so restarts respect active cooldowns.
    if not _gemini_cooldown_db_loaded:
        _gemini_cooldown_db_loaded = True
        _load_cooldown_from_db()
    if _gemini_cooldown_until_utc is None:
        return False, None
    now = datetime.utcnow()
    if now >= _gemini_cooldown_until_utc:
        _gemini_cooldown_until_utc = None
        return False, None
    return True, _gemini_cooldown_until_utc.isoformat()


def _set_gemini_cooldown(hours: int) -> None:
    global _gemini_cooldown_until_utc
    safe_hours = max(1, int(hours or 24))
    _gemini_cooldown_until_utc = datetime.utcnow() + timedelta(hours=safe_hours)
    _persist_cooldown_to_db()


def _extract_feature_suggestions(review_text: str, limit: int = 8) -> list[str]:
    text = str(review_text or "").strip()
    if not text:
        return []

    lines = [ln.strip() for ln in text.splitlines()]
    suggestions: list[str] = []
    capture = False

    for ln in lines:
        low = ln.lower()
        if any(
            marker in low
            for marker in (
                "feature suggestions",
                "bot feature suggestions",
                "functionality suggestions",
                "product suggestions",
            )
        ):
            capture = True
            continue

        if capture:
            if low.startswith("###") or low.startswith("##"):
                break
            if low.startswith("-") or low.startswith("*") or low[:2].isdigit() and low[1] == ".":
                cleaned = ln.lstrip("-*0123456789. ").strip()
                if cleaned:
                    suggestions.append(cleaned)

    # Fallback: pick lines that explicitly mention feature/product/system upgrades.
    if not suggestions:
        for ln in lines:
            low = ln.lower()
            if any(k in low for k in ("feature", "module", "workflow", "automation", "dashboard", "alert")):
                candidate = ln.lstrip("-*0123456789. ").strip()
                if candidate and candidate not in suggestions:
                    suggestions.append(candidate)

    out: list[str] = []
    for s in suggestions:
        if s not in out:
            out.append(s)
        if len(out) >= max(1, int(limit)):
            break
    return out


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


def _gemini_model_candidates() -> list[str]:
    """Resolve Gemini model candidates, starting with GEMINI_MODEL.

    Defaults include currently common public model IDs. Users can override with
    GEMINI_MODEL_FALLBACKS="model_a,model_b,...".
    """
    primary = (os.getenv("GEMINI_MODEL") or "gemini-2.0-flash").strip() or "gemini-2.0-flash"
    fallbacks_raw = (os.getenv("GEMINI_MODEL_FALLBACKS") or "").strip()
    # Comprehensive list of public Gemini models (add more as released)
    all_known_models = [
        # Gemini 3.1 Series
        "gemini-3.1-pro",
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-image",

        # Gemini 3 Series
        "gemini-3-pro",
        "gemini-3-flash",
        "gemini-3-deep-think",
        "gemini-3-pro-image",

        # Gemini 2.5 Series
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash-image",

        # Gemini 2.0 Series
        "gemini-2.0-pro",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",

        # Gemini 1.5 Series
        "gemini-1.5-pro",
        "gemini-1.5-flash",

        # Gemini 1.0 Series
        "gemini-1.0-ultra",
        "gemini-1.0-pro",
        "gemini-1.0-pro-vision",
        "gemini-1.0-nano",

        # Legacy Aliases
        "gemini-pro",
        "gemini-pro-vision",
    ]
    extra = []
    if fallbacks_raw:
        extra = [m.strip() for m in fallbacks_raw.split(",") if m.strip()]
    # Always try primary, then user fallbacks, then all known models (deduped, in order)
    out: list[str] = []
    for m in [primary] + extra + all_known_models:
        if m and m not in out:
            out.append(m)
    return out


def _call_gemini_sync(api_key: str, prompt_payload: dict[str, Any]) -> str:
    in_cd, until = _gemini_in_cooldown()
    if in_cd:
        raise RuntimeError(f"gemini cooldown active until {until}")

    models = _gemini_model_candidates()
    req_body = {
        "contents": [{"parts": [{"text": json.dumps(prompt_payload)}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": int(os.getenv("GEMINI_REVIEW_MAX_TOKENS", "1200") or 1200),
        },
    }

    timeout = int(os.getenv("GEMINI_REVIEW_HTTP_TIMEOUT_SEC", "60") or 60)

    last_err: Exception | None = None
    for model in models:
        req = urllib.request.Request(
            url=(
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={api_key}"
            ),
            data=json.dumps(req_body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            try:
                return str(payload["candidates"][0]["content"]["parts"][0].get("text") or "").strip()
            except Exception:
                return ""
        except urllib.error.HTTPError as exc:
            import traceback
            last_err = exc
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="ignore")[:800]
            except Exception:
                body = ""
            # Model-level 404 is usually recoverable by trying next candidate.
            if int(getattr(exc, "code", 0) or 0) == 404:
                logger.warning("[gemini] model '%s' not found (HTTP 404), trying fallback", model)
                continue
            if int(getattr(exc, "code", 0) or 0) == 429:
                cd_hours = int(os.getenv("GEMINI_COOLDOWN_HOURS", "24") or 24)
                _set_gemini_cooldown(cd_hours)
                logger.warning("[gemini] HTTP 429 detected; enabling cooldown for %sh", cd_hours)
            logger.error(
                "[gemini] HTTP %s for model '%s': %s\nType: %s\nTraceback:\n%s",
                getattr(exc, "code", "?"),
                model,
                body or str(exc),
                type(exc).__name__,
                traceback.format_exc(),
            )
            raise
        except Exception as exc:
            import traceback
            last_err = exc
            logger.error(
                "[gemini] request failed for model '%s': %s\nType: %s\nTraceback:\n%s",
                model,
                exc,
                type(exc).__name__,
                traceback.format_exc(),
            )
            continue

    if last_err is not None:
        raise last_err
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
                VALUES (:k, CAST(:v AS JSONB), NULL, NOW())
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, expires_at = NULL, updated_at = NOW()
                """
            ),
            {"k": key, "v": json.dumps(value)},
        )
        await session.commit()


async def run_gemini_review_pipeline(*, trigger: str, scope: str) -> dict[str, Any]:
    in_cd, until = _gemini_in_cooldown()
    if in_cd:
        return {
            "ok": False,
            "error": f"gemini cooldown active until {until}",
            "trigger": trigger,
            "scope": scope,
        }

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
            "based on broad market best practices, 4) ML feature ideas to improve win ratio, "
            "5) bot feature suggestions to improve functionality, execution safety, and reliability."
        ),
        "constraints": [
            "Avoid overfitting and data leakage.",
            "Use concise and actionable bullet points.",
            "Do not provide investment guarantees.",
            "Prefer robust improvements over aggressive optimization.",
            "Format output with clear section headers including 'Feature Suggestions'.",
        ],
        "aggregate": aggregate,
    }

    review_text = ""
    try:
        review_text = await asyncio.to_thread(_call_gemini_sync, api_key, prompt_payload)
    except Exception as exc:
        logger.error(
            "[gemini] review request failed: %s\nType: %s\nTraceback:\n%s",
            exc,
            type(exc).__name__,
            traceback.format_exc(),
        )

    training = await _train_model_with_overwrite()
    feature_suggestions = _extract_feature_suggestions(review_text)

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
        "feature_suggestions": feature_suggestions,
        "training": training,
    }

    await _store_review("gemini_ml_last_run", result)
    await _store_review(
        "gemini_weekly_ml_review",
        {
            "summary": aggregate,
            "recommendations": review_text,
            "feature_suggestions": feature_suggestions,
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
