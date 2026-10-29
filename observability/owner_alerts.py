"""Owner alerts for the failures that stopped signals in October 2026.

The engine loop hung for six days (22–28 Oct) while every service reported
Online, and nobody was told. These alerts reach the owner on Telegram:

- ``engine_stalled``: sent by the engine's own stall watchdog, before it exits.
- ``engine_silent``: sent by the worker when the engine heartbeat is missing,
  stale or not healthy, so a dead or frozen engine process is still reported.
- ``provider_outage``: sent by the engine's outage job (``engine.core``).
- ``queue_age``: sent by the worker when a delivery queue holds old work.

Each alert is de-duplicated across processes through
``claim_health_notification``, ends with its runbook line, and carries only
operational facts (no tokens, user data or exception text from requests).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger("observability.owner_alerts")

RUNBOOK = {
    "engine_stalled": (
        "Runbook: the engine log shows the stuck call's stack. A dedicated engine exits "
        "with code 70 and Railway restarts it; if no new cycle appears within 10 minutes, "
        "restart the engine service and check Postgres and Redis."
    ),
    "engine_silent": (
        "Runbook: open /readyz and the engine service logs. 'missing' means no engine is "
        "publishing (crashed, not deployed or wrong Redis); 'stalled' or an old heartbeat "
        "means the loop is stuck: restart the engine service. 'skipped' names why cycles end early."
    ),
    "provider_outage": (
        "Runbook: the engine log's provider failure reason names the cause (missing key, "
        "HTTP status, rate limit, region block). Check the provider's key, plan and status page; "
        "signals for affected assets pause until it recovers."
    ),
    "queue_age": (
        "Runbook: confirm the worker service is running and its logs show the relay or consumer "
        "loop; check Postgres and Redis health. Old items are delivered when the consumer "
        "recovers; do not delete queue rows."
    ),
}

HEALTHY_ENGINE_STATUSES = {"started", "market_data_fetched", "pipeline_in_progress", "completed"}


def _float_env(name: str, default: float, minimum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)) or default)
    except ValueError:
        return default
    return max(minimum, value) if value == value else default


def _owner_ids() -> list[int]:
    try:
        from config import OWNER_IDS

        return sorted(int(owner) for owner in (OWNER_IDS or []))
    except Exception:
        return []


def _telegram_post(bot_token: str, chat_id: int, text: str) -> bool:
    import requests

    response = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )
    return bool(getattr(response, "ok", False))


def send_owner_alert(
    event_type: str,
    evidence: dict[str, Any],
    text: str,
    *,
    ttl_seconds: int = 3600,
    post: Callable[[str, int, str], bool] | None = None,
) -> int:
    """Send one de-duplicated owner alert; returns how many owners were reached."""
    bot_token = str(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    owners = _owner_ids()
    if not bot_token or not owners:
        logger.warning("[owner_alert] %s not sent: no bot token or owner ids configured", event_type)
        return 0
    from core.health_notifications import claim_health_notification

    claimed, _ = claim_health_notification(event_type, evidence, ttl_seconds=ttl_seconds)
    if not claimed:
        return 0
    message = f"{text}\n\n{RUNBOOK.get(event_type, '')}".strip()
    sender = post or _telegram_post
    reached = 0
    for owner in owners:
        try:
            reached += 1 if sender(bot_token, owner, message) else 0
        except Exception as exc:
            logger.warning("[owner_alert] %s delivery failed: %s", event_type, type(exc).__name__)
    logger.info("[owner_alert] %s sent to %d of %d owners", event_type, reached, len(owners))
    return reached


def engine_stall_alert(details: dict[str, Any], *, post: Callable[[str, int, str], bool] | None = None) -> int:
    """Called by the stall watchdog with the stalled heartbeat it publishes."""
    stage = str(details.get("stall_stage") or "unknown")
    age_minutes = float(details.get("stall_age_seconds") or 0) / 60.0
    action = "exiting so Railway restarts it" if details.get("stall_action") == "exit" else "left running (shared process)"
    text = (
        f"🛑 Engine stalled: no progress for {age_minutes:.0f} min at stage '{stage}'; {action}. "
        "No signals are produced while it is stuck."
    )
    evidence = {"stage": stage, "deployment": str(os.getenv("RAILWAY_DEPLOYMENT_ID") or "local")}
    return send_owner_alert("engine_stalled", evidence, text, ttl_seconds=1800, post=post)


def engine_heartbeat_finding(raw: Any, *, now: datetime | None = None) -> dict[str, Any] | None:
    """Return a finding when the ``engine:last_cycle`` heartbeat is unhealthy, else ``None``."""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    try:
        cycle = raw if isinstance(raw, dict) else json.loads(str(raw or "{}"))
    except ValueError:
        cycle = {}
    if not isinstance(cycle, dict):
        cycle = {}
    silent_after = _float_env("OWNER_ALERT_ENGINE_SILENT_SECONDS", 900.0, 300.0)
    status = str(cycle.get("status") or "missing")
    stamp_raw = cycle.get("completed_at") or cycle.get("started_at")
    if not stamp_raw:
        return {"status": "missing", "age_seconds": None, "limit_seconds": silent_after}
    try:
        stamp = datetime.fromisoformat(str(stamp_raw).replace("Z", "+00:00"))
    except ValueError:
        return {"status": "unreadable", "age_seconds": None, "limit_seconds": silent_after}
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    age = max(0.0, ((now or datetime.now(timezone.utc)) - stamp).total_seconds())
    if status in HEALTHY_ENGINE_STATUSES and age <= silent_after:
        return None
    if status == "skipped" and age <= silent_after:
        return None  # alive; readiness already names the skip reason
    finding = {"status": status, "age_seconds": round(age), "limit_seconds": silent_after}
    if status == "stalled":
        finding["stall_stage"] = str(cycle.get("stall_stage") or "unknown")
    return finding


def engine_silent_alert(finding: dict[str, Any], *, post: Callable[[str, int, str], bool] | None = None) -> int:
    age = finding.get("age_seconds")
    age_text = "no heartbeat at all" if age is None else f"last heartbeat {float(age) / 60.0:.0f} min ago"
    detail = f" at stage '{finding['stall_stage']}'" if finding.get("stall_stage") else ""
    text = f"⚠️ Engine not producing signals: status '{finding['status']}'{detail}, {age_text}."
    # One alert per status per hour; a recovery and a new failure alert again.
    return send_owner_alert("engine_silent", {"status": finding["status"]}, text, ttl_seconds=3600, post=post)


async def event_outbox_oldest_age_seconds() -> tuple[float | None, int]:
    """Age of the oldest undelivered ``event_outbox`` row and the backlog size (read-only)."""
    from sqlalchemy import text

    from db.session import get_session

    async with get_session(
        priority="background", label="owner_alerts.outbox_age", timeout_seconds=2.0, drop_if_busy=True
    ) as session:
        row = (
            await session.execute(
                text(
                    "SELECT EXTRACT(EPOCH FROM (NOW() - MIN(created_at))), COUNT(*) FROM event_outbox "
                    "WHERE status IN ('pending','claimed','failed')"
                )
            )
        ).first()
        await session.rollback()
    if not row or row[1] in (None, 0):
        return None, 0
    return (float(row[0]) if row[0] is not None else None), int(row[1])


async def queue_age_findings() -> list[dict[str, Any]]:
    """Queues whose oldest unprocessed item is older than ``OWNER_ALERT_QUEUE_AGE_SECONDS``."""
    limit = _float_env("OWNER_ALERT_QUEUE_AGE_SECONDS", 300.0, 60.0)
    findings: list[dict[str, Any]] = []
    try:
        age, backlog = await event_outbox_oldest_age_seconds()
        if age is not None and age > limit:
            findings.append({"queue": "event_outbox", "age_seconds": round(age), "backlog": backlog,
                             "limit_seconds": limit})
    except Exception as exc:
        logger.debug("[owner_alert] event_outbox age unavailable: %s", type(exc).__name__)
    try:
        from core.redis_streams import telegram_update_stream

        stream = telegram_update_stream()
        if stream.configured:
            age = await stream.oldest_unprocessed_age_seconds()
            if age is not None and age > limit:
                findings.append({"queue": "telegram_updates", "age_seconds": round(age), "backlog": None,
                                 "limit_seconds": limit})
    except Exception as exc:
        logger.debug("[owner_alert] telegram stream age unavailable: %s", type(exc).__name__)
    return findings


def queue_age_alert(finding: dict[str, Any], *, post: Callable[[str, int, str], bool] | None = None) -> int:
    backlog = f", {finding['backlog']} items waiting" if finding.get("backlog") else ""
    text = (
        f"⏳ Queue backing up: {finding['queue']} oldest item is "
        f"{float(finding['age_seconds']) / 60.0:.0f} min old (limit {float(finding['limit_seconds']) / 60.0:.0f} min){backlog}."
    )
    return send_owner_alert("queue_age", {"queue": finding["queue"]}, text, ttl_seconds=3600, post=post)


async def run_checks_once(*, read_heartbeat: Callable[[], Any] | None = None) -> dict[str, Any]:
    """One worker pass: engine heartbeat and queue ages. Returns what was found."""
    import asyncio

    if read_heartbeat is None:
        from core.redis_state import state

        def read_heartbeat() -> Any:
            return state.get_sync("engine:last_cycle")

    raw = await asyncio.wait_for(asyncio.to_thread(read_heartbeat), timeout=5.0)
    engine = engine_heartbeat_finding(raw)
    if engine is not None:
        await asyncio.to_thread(engine_silent_alert, engine)
    queues = await queue_age_findings()
    for finding in queues:
        await asyncio.to_thread(queue_age_alert, finding)
    return {"engine": engine, "queues": queues}


__all__ = [
    "RUNBOOK",
    "engine_heartbeat_finding",
    "engine_silent_alert",
    "engine_stall_alert",
    "queue_age_alert",
    "queue_age_findings",
    "run_checks_once",
    "send_owner_alert",
]
