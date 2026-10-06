"""Shared profile lifecycle serialization, short approval leases and worker loops."""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from typing import Any, Mapping

from sqlalchemy import text

LIFECYCLE_LOCK_SQL = "SELECT pg_advisory_xact_lock(hashtext('signalrankai_adaptive_health'))"
LEASE_VERSION = "adaptive-health-lease-v1"
MAXIMUM_LEASE_SECONDS = 630
logger = logging.getLogger(__name__)


def health_interval_seconds() -> float:
    value = float(os.getenv("ADAPTIVE_HEALTH_INTERVAL_SECONDS", "60"))
    if not math.isfinite(value) or not 15 <= value <= 300:
        raise ValueError("adaptive_health_interval_must_be_15_to_300_seconds")
    return value


async def lock_profile_lifecycle(session: Any) -> None:
    # Publication and deactivation share this transaction lock, so an older
    # publisher cannot overwrite a suspension after reading an approved row.
    await session.execute(text(LIFECYCLE_LOCK_SQL))


def approval_lease(profile_id: str) -> dict[str, Any]:
    issued = time.time()
    return {"version": LEASE_VERSION, "profile_id": profile_id, "issued_at": issued,
            "expires_at": issued + 2 * health_interval_seconds() + 30}


def approval_lease_valid(payload: Mapping[str, Any]) -> bool:
    lease = payload.get("health_lease")
    if not isinstance(lease, dict) or lease.get("version") != LEASE_VERSION:
        return False
    if not payload.get("profile_id") or lease.get("profile_id") != payload.get("profile_id"):
        return False
    issued, expires = lease.get("issued_at"), lease.get("expires_at")
    if isinstance(issued, bool) or not isinstance(issued, (int, float)) or not math.isfinite(issued):
        return False
    if isinstance(expires, bool) or not isinstance(expires, (int, float)) or not math.isfinite(expires):
        return False
    current = time.time()
    return issued <= current + 5 and current < expires and 0 < expires - issued <= MAXIMUM_LEASE_SECONDS


async def profile_health_loop(stop: asyncio.Event) -> None:
    """Refresh profile health independently of optimization and training pauses."""
    from core.redis_state import state
    from .learning import monitor_profile_health

    interval = health_interval_seconds()
    while not stop.is_set():
        report = {"checked_at_epoch": time.time(), "interval_seconds": interval,
                  "evidence_scope": "confirmed_signal_delivery_outcomes", "broker_fills_certified": False}
        try:
            result = await monitor_profile_health()
            report.update(status="COMPLETED", **result)
            logger.info("[adaptive_health] completed suspended=%s published=%s",
                        result.get("suspended_assets"), result.get("published"))
        except Exception as exc:
            # Do not renew an approval after a failed DB/monitor iteration.
            report.update(status="ERROR", error_type=type(exc).__name__)
            logger.warning("[adaptive_health] failed error_type=%s; existing leases will expire", type(exc).__name__)
        state.set_sync("adaptive:health:last_check", json.dumps(report), ex=math.ceil(interval * 2 + 30))
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


def health_monitor_snapshot(state_store: Any) -> dict[str, Any]:
    """Bounded operator diagnostics; a successful check is not an edge certificate."""
    try:
        raw = state_store.get_sync("adaptive:health:last_check")
        if not isinstance(raw, str) or not raw or len(raw) > 65_536:
            raise ValueError("health_report_unavailable")
        report = json.loads(raw)
        if not isinstance(report, dict) or report.get("status") not in {"COMPLETED", "ERROR"}:
            raise ValueError("health_report_invalid")
        issued, interval = report["checked_at_epoch"], report["interval_seconds"]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
               for v in (issued, interval)) or not 15 <= interval <= 300:
            raise ValueError("health_report_clock_invalid")
        age = time.time() - issued
        fresh = -5 <= age <= interval * 2 + 30
        return {**report, "fresh": fresh, "age_seconds": max(0, age), "broker_fills_certified": False,
                "status": report["status"] if fresh else "STALE"}
    except Exception:
        return {"status": "UNAVAILABLE", "fresh": False, "broker_fills_certified": False}


async def adaptive_learning_loop(stop: asyncio.Event) -> None:
    """Canonical bounded challenger loop, shared by analytics and legacy worker."""
    from .learning import AdaptiveLearningWorker

    interval = max(3600, int(os.getenv("ADAPTIVE_LEARNING_INTERVAL_SECONDS", "21600") or 21600))
    railway = any(os.getenv(key) for key in ("RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_ID", "RAILWAY_ENVIRONMENT"))
    delay = float(os.getenv("ADAPTIVE_LEARNING_STARTUP_DELAY_SECONDS", "300" if railway else "0"))
    if not math.isfinite(delay) or not 0 <= delay <= 3600:
        raise ValueError("invalid_adaptive_learning_startup_delay")
    if delay:
        try:
            await asyncio.wait_for(stop.wait(), timeout=delay)
            return
        except asyncio.TimeoutError:
            pass
    worker = AdaptiveLearningWorker()
    while not stop.is_set():
        try:
            result = await worker.run_once()
            logger.info("[adaptive_learning] completed result=%s", result)
        except Exception as exc:
            logger.warning("[adaptive_learning] iteration failed error_type=%s", type(exc).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
