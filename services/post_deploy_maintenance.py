"""Post-deploy maintenance run by the analytics service (8 Nov 2026).

Two owner steps from the 6-8 Nov work that only the server could run:

1. **Ledger refresh after audited outcome corrections.** Migration 0059 gave
   closed outcomes stored as ``pending`` their real result (the 4 Nov ZECUSDT
   stop). The per-user performance ledger kept its older copy until each
   recipient opened their results, so ``/readyz`` reported
   ``outcome_to_ledger_mismatch`` and "degraded" after the deploy. On every
   analytics start this re-reconciles the ledgers of users holding a ledger row
   for a migration-corrected outcome (cheap; idempotent).
2. **Stale-tick shadow label correction: dry run automatically, apply by the
   owner.** Runs ``scripts/correct_stale_tick_shadow_labels.py`` without
   ``--apply`` once (labels tracked before the stale-tick fix, 4 Nov 08:00
   UTC), pausing between id windows, and stores the counts. The owner reviews
   them and applies with ``/stale_tick_relabel apply`` in Telegram, as the
   owner asked ("without --apply first to see the counts, then with --apply").
   ``POST_DEPLOY_STALE_TICK_RELABEL=0`` disables the dry run.

Neither touches thresholds, gates, execution or billing.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

RELABEL_MARKER = "maintenance:stale_tick_relabel:v1:done"
PREVIEW_KEY = "maintenance:stale_tick_relabel:v1:preview"
# bec9a5f (stale market_ticks refused) went live on production on 4 Nov 2026
# in the morning UTC; labels tracked after this already used fresh prices.
RELABEL_UNTIL = datetime(2026, 11, 4, 8, 0)
CORRECTED_BY = ("migration_0059_close_pending_terminal",)


def _enabled(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    return default if raw is None else str(raw).strip().lower() in {"1", "true", "yes", "on"}


async def refresh_ledgers_for_corrected_outcomes() -> int:
    """Re-reconcile the ledgers of users who hold a row for a migration-corrected outcome."""
    from sqlalchemy import text

    from db.session import get_session
    from services.performance_ledger import reconcile_user_performance_ledger

    async with get_session(priority="analytics", label="post_deploy.ledger_users", timeout_seconds=30) as session:
        users = [
            int(r[0]) for r in (await session.execute(
                text(
                    "SELECT DISTINCT u.telegram_user_id FROM performance_ledger_entries p "
                    "JOIN users u ON u.id = p.user_id JOIN outcomes o ON o.signal_id = p.signal_id "
                    "WHERE o.corrected_by = ANY(:by) AND u.telegram_user_id IS NOT NULL"
                ),
                {"by": list(CORRECTED_BY)},
            )).all()
        ]
        await session.rollback()
    refreshed = 0
    for telegram_user_id in users:
        try:
            async with get_session(priority="analytics", label="post_deploy.ledger_refresh",
                                   timeout_seconds=60) as session:
                await reconcile_user_performance_ledger(session, telegram_user_id=telegram_user_id)
                await session.commit()
            refreshed += 1
        except Exception as exc:
            logger.warning("[post_deploy] ledger refresh failed user=%s error=%s", telegram_user_id,
                           type(exc).__name__)
    logger.info("[post_deploy] ledger_refresh users=%s refreshed=%s", len(users), refreshed)
    return refreshed


def _load_script():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "correct_stale_tick_shadow_labels.py"
    spec = importlib.util.spec_from_file_location("correct_stale_tick_shadow_labels", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def run_stale_tick_relabel(*, apply: bool) -> dict:
    """Dry run (counts only) or audited apply of the stale-tick label correction."""
    from core.redis_state import state

    dsn = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PRIVATE_URL") or ""
    if not dsn:
        return {"skipped": "no_database_url"}
    counts = await _load_script().run(
        dsn, since=RELABEL_UNTIL - timedelta(days=60), until=RELABEL_UNTIL, apply=apply, batch=500,
        id_window=50_000, all_assets=False, pause_seconds=0.5,
        out=lambda line: logger.info("%s", line),
    )
    summary = {**dict(counts), "mode": "apply" if apply else "dry_run", "at": datetime.utcnow().isoformat(),
               "until": RELABEL_UNTIL.isoformat()}
    state.set_sync(RELABEL_MARKER if apply else PREVIEW_KEY, json.dumps(summary, sort_keys=True))
    logger.info("[post_deploy] stale_tick_relabel %s %s", summary["mode"], summary)
    return summary


async def stale_tick_relabel_preview_once() -> dict:
    """The owner's step 1, automated: a dry run once, counts stored for review.

    Applying stays an owner decision (``/stale_tick_relabel apply``): the owner
    asked to see the counts first, and this changes production learning data.
    """
    from core.redis_state import state

    try:
        if state.get_sync(PREVIEW_KEY) or state.get_sync(RELABEL_MARKER):
            return {"skipped": "already_previewed"}
    except Exception:
        return {"skipped": "marker_unavailable"}
    return await run_stale_tick_relabel(apply=False)


async def post_deploy_maintenance(stop: asyncio.Event) -> None:
    """Run once per analytics start; never raises into the service.

    The work is one-shot, but analytics supervises its tasks and treats any task
    that *returns* before ``stop`` as a crash (``analytics_task_stopped_unexpectedly``)
    and restarts the whole service. Production restarted analytics every ~2-3
    minutes from 8 Nov 18:20 UTC (260 restarts in 10 h), which killed the
    scorecard rebuild, ML training and strategy discovery before they could run.
    So after the work this coroutine idles until ``stop`` is set.
    """
    await _run_maintenance(stop)
    await stop.wait()


async def _run_maintenance(stop: asyncio.Event) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=float(os.getenv("POST_DEPLOY_MAINTENANCE_DELAY_SECONDS", "120")))
        return
    except asyncio.TimeoutError:
        pass
    if _enabled("POST_DEPLOY_LEDGER_REFRESH", True):
        try:
            await refresh_ledgers_for_corrected_outcomes()
        except Exception as exc:
            logger.warning("[post_deploy] ledger refresh unavailable: %s", type(exc).__name__)
    if _enabled("POST_DEPLOY_STALE_TICK_RELABEL", True) and not stop.is_set():
        try:
            await stale_tick_relabel_preview_once()
        except Exception as exc:
            logger.warning("[post_deploy] stale_tick_relabel dry run failed: %s: %s", type(exc).__name__, exc)
    if _enabled("POST_DEPLOY_STALE_TICK_RELABEL_APPLY", True) and not stop.is_set():
        # Owner, 10 Nov 2026: "correct all wrong database details". The stale-tick label
        # correction was dry-run only, waiting for /stale_tick_relabel apply; the owner has
        # now asked for every wrong record to be corrected, so it is applied once here
        # (same audited script; the marker makes it run once).
        try:
            from core.redis_state import state

            if not state.get_sync(RELABEL_MARKER):
                await run_stale_tick_relabel(apply=True)
        except Exception as exc:
            logger.warning("[post_deploy] stale_tick_relabel apply failed: %s: %s", type(exc).__name__, exc)
    if not stop.is_set():
        # Owner, 10 Nov 2026: audited corrections from the read-only data audit.
        try:
            from services.data_corrections import run_once as data_corrections

            logger.info("[post_deploy] data_corrections %s", await data_corrections())
        except Exception as exc:
            logger.warning("[post_deploy] data_corrections failed: %s", type(exc).__name__)
    if not stop.is_set():
        # Owner, 10 Nov 2026: correct the stored asset class on past training rows, then retrain.
        try:
            from services.asset_class_backfill import run as asset_class_backfill

            from services.asset_class_backfill import backfill_signal_classes

            logger.info("[post_deploy] signal asset classes %s", await backfill_signal_classes())
            result = await asset_class_backfill(stop)
            logger.info("[post_deploy] asset_class_backfill %s", result)
        except Exception as exc:
            logger.warning("[post_deploy] asset_class_backfill failed: %s", type(exc).__name__)
