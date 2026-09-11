from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from sqlalchemy import text

from db.session import get_session

logger = logging.getLogger(__name__)


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
        "batch_size": _env_int("LEARNING_HISTORY_RETENTION_BATCH_SIZE", 5000, 100, 25000),
        "max_batches": _env_int("LEARNING_HISTORY_RETENTION_MAX_BATCHES", 4, 1, 20),
        "decision_days": _env_int("DECISION_LOG_RETENTION_DAYS", 30, 1, 3650),
        "rejection_tracked_days": _env_int("REJECTION_TRACKED_RETENTION_DAYS", 120, 91, 3650),
        "rejection_untracked_days": _env_int("REJECTION_UNTRACKED_RETENTION_DAYS", 14, 2, 3650),
        "statement_timeout_ms": _env_int("LEARNING_HISTORY_RETENTION_STATEMENT_TIMEOUT_MS", 8000, 1000, 30000),
    }


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
                WHERE created_at < NOW() - (CAST(:days AS INTEGER) * INTERVAL '1 day')
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
                SELECT id FROM ml_rejected_signals
                WHERE outcome_tracked_at IS NOT NULL
                  AND created_at < NOW() - (CAST(:days AS INTEGER) * INTERVAL '1 day')
                ORDER BY id
                LIMIT CAST(:limit AS INTEGER)
            )
            DELETE FROM ml_rejected_signals AS target
            USING doomed
            WHERE target.id = doomed.id
            """,
            int(cfg["rejection_tracked_days"]),
        ),
        (
            "rejections_untracked",
            """
            WITH doomed AS (
                SELECT id FROM ml_rejected_signals
                WHERE outcome_tracked_at IS NULL
                  AND created_at < NOW() - (CAST(:days AS INTEGER) * INTERVAL '1 day')
                ORDER BY id
                LIMIT CAST(:limit AS INTEGER)
            )
            DELETE FROM ml_rejected_signals AS target
            USING doomed
            WHERE target.id = doomed.id
            """,
            int(cfg["rejection_untracked_days"]),
        ),
    )

    try:
        async with get_session(priority="background", label="learning_history_retention", timeout_seconds=10.0) as session:
            await session.execute(
                text("SET LOCAL statement_timeout = :timeout"),
                {"timeout": f"{int(cfg['statement_timeout_ms'])}ms"},
            )
            for key, sql, days in statements:
                for _ in range(max_batches):
                    deleted = await _delete_batch(session, sql, {"days": days, "limit": batch_size})
                    totals[key] += deleted
                    if deleted < batch_size:
                        break
            await session.commit()
    except Exception as exc:
        logger.warning("[storage_maintenance] retention pass failed: %s", exc)
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
    logger.info(
        "[storage_maintenance] enabled interval=%ss decision_days=%s tracked_rejection_days=%s untracked_rejection_days=%s",
        interval,
        cfg["decision_days"],
        cfg["rejection_tracked_days"],
        cfg["rejection_untracked_days"],
    )
    while True:
        try:
            await run_learning_history_retention_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[storage_maintenance] unexpected pass error: %s", exc)
        await asyncio.sleep(interval)
