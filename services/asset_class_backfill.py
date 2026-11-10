"""Correct the stored asset class on past training rows, then retrain (owner request, 10 Nov 2026).

"Correct all the past data in the asset-class bug to be using the correct asset
classes, and the retrain."

Tracked rejected setups (``decision_log``, ``decision='rejected'``, ML layer) are
the bulk of the training data. Most had no ``features.asset_class_enc`` stored,
and the trainer defaulted it to 0 (crypto), so FX, commodity, stock and index
setups trained as crypto. Training already recomputes the class from the symbol
(``ml.features.live_asset_class_enc``, the engine's own encoding); this job also
corrects the stored rows so every reader (training, evidence, reports) agrees.

* Only tracked rows inside ``ASSET_CLASS_BACKFILL_DAYS`` (default 120, covering
  the 90-day training lookback), newest first, via ``ix_decision_log_tracked_id``.
* Windows of ``ASSET_CLASS_BACKFILL_WINDOW`` ids (2,000); only rows whose stored
  value is missing or different are rewritten, by primary key; a pause between
  windows keeps the database responsive.
* The cursor is kept in ``runtime_state`` so a restart resumes; a done marker
  makes it run once. When it finishes it requests an ML training run
  (the same queue as the owner's ``/ml_retrain``).

It changes the encoded class only: no outcome, label, threshold or gate.
``ASSET_CLASS_BACKFILL_ENABLED=false`` turns it off.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import timedelta
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

DONE_KEY = "maintenance:asset_class_backfill:v1:done"
CURSOR_KEY = "maintenance:asset_class_backfill:v1:cursor"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


async def _state_get(session: Any, key: str) -> Any:
    row = (await session.execute(text("SELECT value FROM runtime_state WHERE key=:k"), {"k": key})).first()
    if not row:
        return None
    value = row[0]
    return json.loads(value) if isinstance(value, str) else value


async def _state_set(session: Any, key: str, value: Any) -> None:
    await session.execute(
        text("INSERT INTO runtime_state(key, value, expires_at, updated_at) VALUES (:k, CAST(:v AS JSONB), NULL, NOW()) "
             "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()"),
        {"k": key, "v": json.dumps(value)},
    )


async def run(stop: asyncio.Event | None = None, *, pause_seconds: float | None = None) -> dict[str, Any]:
    """Correct the stored classes; returns counts. Safe to call repeatedly (resumes, then no-ops)."""
    from db.session import get_session
    from ml.features import live_asset_class_enc
    from utils.timeutils import now_utc_naive

    if str(os.getenv("ASSET_CLASS_BACKFILL_ENABLED", "1")).strip().lower() not in {"1", "true", "yes", "on"}:
        return {"status": "disabled"}
    window = max(200, min(20000, _env_int("ASSET_CLASS_BACKFILL_WINDOW", 2000)))
    pause = float(os.getenv("ASSET_CLASS_BACKFILL_PAUSE_SECONDS", "0.5")) if pause_seconds is None else pause_seconds
    cutoff = now_utc_naive() - timedelta(days=max(1, _env_int("ASSET_CLASS_BACKFILL_DAYS", 120)))

    async with get_session(priority="analytics", label="asset_class_backfill.state", timeout_seconds=20) as session:
        if await _state_get(session, DONE_KEY):
            await session.rollback()
            return {"status": "already_done"}
        cursor = await _state_get(session, CURSOR_KEY) or {}
        await session.rollback()
    before = int(cursor.get("before") or 2**31 - 1)
    counts = {"scanned": int(cursor.get("scanned") or 0), "corrected": int(cursor.get("corrected") or 0)}
    classes: dict[str, float] = {}
    finished = False

    failures = 0
    while stop is None or not stop.is_set():
        try:
            async with get_session(priority="analytics", label="asset_class_backfill.window", timeout_seconds=120) as session:
                ids = [int(r[0]) for r in (await session.execute(text(
                    "SELECT id FROM decision_log WHERE meta->>'outcome_tracked_at' IS NOT NULL AND id < :before "
                    "ORDER BY id DESC LIMIT :window"), {"before": before, "window": window})).all()]
                if not ids:
                    finished = True
                    await session.rollback()
                    break
                rows = (await session.execute(text(
                    "SELECT id, asset, created_at, meta->'features'->>'asset_class_enc' AS enc FROM decision_log "
                    "WHERE id = ANY(:ids) AND decision = 'rejected' AND meta->>'layer' = 'ml'"), {"ids": ids})).all()
                fixes: dict[float, list[int]] = {}
                reached_cutoff = False
                for row_id, asset, created_at, stored in rows:
                    if created_at is not None and created_at < cutoff:
                        reached_cutoff = True
                        continue
                    key = str(asset or "")
                    if key not in classes:
                        classes[key] = float(live_asset_class_enc(key))
                    want = classes[key]
                    try:
                        have = float(stored) if stored is not None else None
                    except (TypeError, ValueError):
                        have = None
                    if have != want:
                        fixes.setdefault(want, []).append(int(row_id))
                for enc, fix_ids in fixes.items():
                    await session.execute(text(
                        "UPDATE decision_log SET meta = jsonb_set(meta, '{features}', "
                        "COALESCE(meta->'features', '{}'::jsonb) || jsonb_build_object('asset_class_enc', CAST(:enc AS DOUBLE PRECISION))) "
                        "WHERE id = ANY(:ids)"), {"enc": enc, "ids": fix_ids})
                    counts["corrected"] += len(fix_ids)
                counts["scanned"] += len(rows)
                before = min(ids)
                await _state_set(session, CURSOR_KEY, {"before": before, **counts})
                await session.commit()
            failures = 0
        except Exception as exc:
            # A busy database must not end the job (production 10 Nov 2026: it stopped after one
            # failed window and only resumed on the next restart). Wait, retry, pause after 5.
            failures += 1
            logger.warning("[asset_class_backfill] window failed before=%s attempt=%s error=%s", before, failures,
                           type(exc).__name__)
            if failures >= 5:
                break
            await asyncio.sleep(10.0 * failures)
            continue
        if reached_cutoff or len(ids) < window:
            finished = True
            break
        if pause > 0:
            await asyncio.sleep(pause)

    if not finished:
        logger.info("[asset_class_backfill] paused before=%s %s", before, counts)
        return {"status": "paused", **counts}
    async with get_session(priority="analytics", label="asset_class_backfill.done", timeout_seconds=20) as session:
        await _state_set(session, DONE_KEY, {"finished_at": now_utc_naive().isoformat(), **counts})
        await session.commit()
    try:
        from core.redis_state import state
        from runtime.analytics import ML_FORCE_TRAIN_KEY

        state.set_sync(ML_FORCE_TRAIN_KEY, "asset_class_backfill", ex=6 * 3600)
    except Exception:
        logger.info("[asset_class_backfill] retrain request not queued")
    logger.info("[asset_class_backfill] done %s; retrain requested", counts)
    return {"status": "done", **counts}


SIGNALS_DONE_KEY = "maintenance:signal_asset_class:v1:done"


async def backfill_signal_classes() -> dict[str, Any]:
    """Fill the empty ``signals.asset_class`` (42,702 recent rows, audit 10 Nov 2026), once.

    One indexed update per distinct symbol with the engine's classification
    (``core.asset_class_key``); only empty values are written.
    """
    from core.asset_class_key import canonical_asset_class
    from db.session import get_session

    async with get_session(priority="analytics", label="signal_class_backfill", timeout_seconds=60) as session:
        if await _state_get(session, SIGNALS_DONE_KEY):
            await session.rollback()
            return {"status": "already_done"}
        assets = [str(r[0]) for r in (await session.execute(text(
            "SELECT DISTINCT asset FROM signals WHERE COALESCE(asset_class, '') = '' AND asset IS NOT NULL"))).all()]
        updated = 0
        for asset in assets:
            result = await session.execute(text(
                "UPDATE signals SET asset_class = :c WHERE asset = :a AND COALESCE(asset_class, '') = ''"),
                {"c": canonical_asset_class(asset)[:16], "a": asset})
            updated += int(getattr(result, "rowcount", 0) or 0)
        await _state_set(session, SIGNALS_DONE_KEY, {"assets": len(assets), "updated": updated})
        await session.commit()
    logger.info("[asset_class_backfill] signals assets=%s updated=%s", len(assets), updated)
    return {"status": "done", "assets": len(assets), "updated": updated}


async def asset_class_backfill_loop(stop: asyncio.Event) -> None:
    """Resume the backfill every 10 minutes until it is done (no deploy needed)."""
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=float(os.getenv("ASSET_CLASS_BACKFILL_RETRY_SECONDS", "600")))
            return
        except asyncio.TimeoutError:
            pass
        try:
            result = await run(stop)
            if result.get("status") in {"done", "already_done", "disabled"}:
                return
        except Exception as exc:
            logger.warning("[asset_class_backfill] retry failed error=%s", type(exc).__name__)
