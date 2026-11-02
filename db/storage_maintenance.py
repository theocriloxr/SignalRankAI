from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from sqlalchemy import text

from db.session import get_session

logger = logging.getLogger(__name__)


def _retention_db_priority() -> str:
    role = str(os.getenv("DB_ROLE") or os.getenv("RUN_MODE") or "").strip().lower()
    return "analytics" if role == "analytics" or role.startswith("analytics-") else "background"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(os.getenv(name) or default).strip())
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def retention_config() -> dict[str, int | bool]:
    """Return bounded retention settings.

    Retention is disabled by default. Environments must opt in explicitly.
    The tracked-rejection default exceeds the ML trainer's normal 90-day
    lookback so enabling defaults does not discard samples used by training.
    """
    return {
        "enabled": _env_bool("LEARNING_HISTORY_RETENTION_ENABLED", False),
        "interval_seconds": _env_int("LEARNING_HISTORY_RETENTION_INTERVAL_SECONDS", 3600, 300, 86400),
        "startup_delay_seconds": _env_int("LEARNING_HISTORY_RETENTION_STARTUP_DELAY_SECONDS", 300, 0, 3600),
        "batch_size": _env_int("LEARNING_HISTORY_RETENTION_BATCH_SIZE", 5000, 100, 25000),
        "max_batches": _env_int("LEARNING_HISTORY_RETENTION_MAX_BATCHES", 4, 1, 20),
        "decision_days": _env_int("DECISION_LOG_RETENTION_DAYS", 30, 1, 3650),
        "rejection_tracked_days": _env_int("REJECTION_TRACKED_RETENTION_DAYS", 120, 91, 3650),
        "rejection_untracked_days": _env_int("REJECTION_UNTRACKED_RETENTION_DAYS", 14, 2, 3650),
        "statement_timeout_ms": _env_int("LEARNING_HISTORY_RETENTION_STATEMENT_TIMEOUT_MS", 8000, 1000, 30000),
    }


async def _first_id_newer_than(session: Any, days: int) -> int:
    """Smallest decision_log id created within the last ``days`` days.

    ``decision_log.created_at`` has no index (the table holds millions of JSON
    rows), so a date filter alone forces a sequential scan that exceeds the
    statement timeout. Ids grow with time: a binary search over the primary key
    (a few dozen indexed lookups) bounds every delete to an index range instead.
    """
    max_id = int((await session.execute(text("SELECT COALESCE(MAX(id), 0) FROM decision_log"))).scalar() or 0)
    low, high = 0, max_id + 1
    while low < high:
        mid = (low + high) // 2
        row = (
            await session.execute(
                text(
                    "SELECT id, created_at < NOW() - (CAST(:days AS INTEGER) * INTERVAL '1 day') "
                    "FROM decision_log WHERE id >= :mid ORDER BY id LIMIT 1"
                ),
                {"mid": mid, "days": int(days)},
            )
        ).first()
        if row is None or not bool(row[1]):
            high = mid
        else:
            low = int(row[0]) + 1
    return low


async def _delete_batch(session: Any, sql: str, params: dict[str, Any]) -> int:
    result = await session.execute(text(sql), params)
    return int(getattr(result, "rowcount", 0) or 0)


async def run_learning_history_retention_once() -> dict[str, int]:
    """Delete only telemetry outside configured hot-data windows, in bounded batches.

    PostgreSQL can reuse the freed pages for future inserts, which prevents the
    append-only tables from continually extending the volume. This intentionally
    does not run VACUUM FULL or any operation requiring extra disk headroom.
    """
    cfg = retention_config()
    if not cfg["enabled"]:
        return {"decision_log": 0, "rejections_tracked": 0, "rejections_untracked": 0}

    batch_size = int(cfg["batch_size"])
    max_batches = int(cfg["max_batches"])
    totals = {"decision_log": 0, "rejections_tracked": 0, "rejections_untracked": 0}

    statements = (
        (
            "decision_log",
            """
            WITH doomed AS (
                SELECT id FROM decision_log
                WHERE NOT (
                    decision = 'rejected'
                    AND COALESCE(meta->>'layer', '') = 'ml'
                )
                  AND id < CAST(:max_id AS BIGINT)
                  AND created_at < NOW() - (CAST(:days AS INTEGER) * INTERVAL '1 day')
                ORDER BY id
                LIMIT CAST(:limit AS INTEGER)
            )
            DELETE FROM decision_log AS target
            USING doomed
            WHERE target.id = doomed.id
            """,
            int(cfg["decision_days"]),
        ),
        (
            "rejections_tracked",
            """
            WITH doomed AS (
                SELECT id FROM decision_log
                WHERE decision = 'rejected'
                  AND COALESCE(meta->>'layer', '') = 'ml'
                  AND NULLIF(meta->>'outcome_tracked_at', '') IS NOT NULL
                  AND id < CAST(:max_id AS BIGINT)
                  AND created_at < NOW() - (CAST(:days AS INTEGER) * INTERVAL '1 day')
                ORDER BY id
                LIMIT CAST(:limit AS INTEGER)
            )
            DELETE FROM decision_log AS target
            USING doomed
            WHERE target.id = doomed.id
            """,
            int(cfg["rejection_tracked_days"]),
        ),
        (
            "rejections_untracked",
            """
            WITH doomed AS (
                SELECT id FROM decision_log
                WHERE decision = 'rejected'
                  AND COALESCE(meta->>'layer', '') = 'ml'
                  AND NULLIF(meta->>'outcome_tracked_at', '') IS NULL
                  AND id < CAST(:max_id AS BIGINT)
                  AND created_at < NOW() - (CAST(:days AS INTEGER) * INTERVAL '1 day')
                ORDER BY id
                LIMIT CAST(:limit AS INTEGER)
            )
            DELETE FROM decision_log AS target
            USING doomed
            WHERE target.id = doomed.id
            """,
            int(cfg["rejection_untracked_days"]),
        ),
    )

    failed = False
    for key, sql, days in statements:
        # One transaction per category: a timeout in one no longer rolls back the others.
        try:
            async with get_session(
                priority=_retention_db_priority(),
                label="learning_history_retention",
                timeout_seconds=max(10.0, float(os.getenv("LEARNING_HISTORY_DB_TIMEOUT_SECONDS", "60") or 60)),
                drop_if_busy=False,
            ) as session:
                await session.execute(
                    text("SELECT set_config('statement_timeout', :timeout, true)"),
                    {"timeout": f"{int(cfg['statement_timeout_ms'])}ms"},
                )
                max_id = await _first_id_newer_than(session, days)
                for _ in range(max_batches):
                    deleted = await _delete_batch(
                        session, sql, {"days": days, "limit": batch_size, "max_id": max_id}
                    )
                    totals[key] += deleted
                    if deleted < batch_size:
                        break
                await session.commit()
        except Exception as exc:
            failed = True
            logger.warning("[storage_maintenance] retention pass failed category=%s: %s", key, str(exc)[:300])
    if failed and not any(totals.values()):
        return totals

    if any(totals.values()):
        logger.info(
            "[storage_maintenance] pruned decision=%s tracked_rejections=%s untracked_rejections=%s",
            totals["decision_log"],
            totals["rejections_tracked"],
            totals["rejections_untracked"],
        )
    return totals


async def learning_history_maintenance_loop() -> None:
    """Run bounded retention periodically while the maintenance service is alive."""
    cfg = retention_config()
    if not cfg["enabled"]:
        logger.info("[storage_maintenance] disabled")
        return

    interval = int(cfg["interval_seconds"])
    startup_delay = int(cfg["startup_delay_seconds"])
    logger.info(
        "[storage_maintenance] enabled interval=%ss startup_delay=%ss decision_days=%s tracked_rejection_days=%s untracked_rejection_days=%s",
        interval,
        startup_delay,
        cfg["decision_days"],
        cfg["rejection_tracked_days"],
        cfg["rejection_untracked_days"],
    )
    if startup_delay > 0:
        await asyncio.sleep(startup_delay)
    while True:
        try:
            await run_learning_history_retention_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[storage_maintenance] unexpected pass error: %s", exc)
        await asyncio.sleep(interval)
