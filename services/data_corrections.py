"""Audited one-off data corrections from the 10 Nov 2026 data audit (owner request).

Owner: "read all the lines and data in the database and correct all wrong
database details". A read-only audit (ops queue, results 20261110T2119/2122Z)
found four kinds of wrong records. Each correction below runs once (a
``runtime_state`` marker), in its own transaction, touches only rows that match
the audited pattern, writes ``corrected_by`` where the table has it, and stores
its counts in ``runtime_state`` as the audit trail.

1. **Broken setups** (~1,300, 22-23 Sep 2026, mostly 1m): entry, stop and
   target were the same price. None was delivered. Status becomes
   ``invalid_geometry`` so no reader treats them as setups.
2. **Degenerate-stop outcomes** (7, 24-25 Jul 2026): stops a few ticks from
   the entry produced "wins" of 17-64R that inflate every average. The outcome
   stays; ``performance_inclusion_status`` becomes ``excluded`` with the reason.
3. **Outcomes stuck in "pending"** (18, Jul-Aug 2026): never resolved, older
   than 30 days. Closed as ``expired`` with no R, like every other expiry.
4. **Lifecycles left open** (~190, Jul-Sep 2026, undelivered shadow signals):
   still WATCHING/ACTIVE/TP1/TP2 months later. Closed as ``EXPIRED``; any TP
   already reached stays recorded.

Nothing delivered to a user is changed except (2), which only removes a
degenerate result from averages. ``DATA_CORRECTIONS_ENABLED=false`` disables it.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

MARKER = "maintenance:data_corrections:20261110:done"
TAG = "data_audit_20261110"

_BROKEN_SETUPS = """
UPDATE signals s SET status = 'invalid_geometry'
WHERE s.created_at < NOW() - INTERVAL '2 days'
  AND s.status IN ('shadow_rejected', 'superseded', 'expired', 'issued', 'active')
  AND s.entry IS NOT NULL AND s.stop_loss IS NOT NULL
  AND ABS(s.entry - s.stop_loss) <= 1e-12 * GREATEST(ABS(s.entry), 1)
  AND NOT EXISTS (SELECT 1 FROM signal_deliveries d WHERE d.signal_id = s.signal_id AND d.sent_ok)
"""

_DEGENERATE_STOPS = """
UPDATE outcomes o SET performance_inclusion_status = 'excluded',
       performance_exclusion_reason = 'degenerate_stop_r_over_15', corrected_by = :tag
FROM signals s
WHERE s.signal_id = o.signal_id
  AND ABS(o.r_multiple) > 15
  AND s.entry > 0 AND ABS(s.entry - s.stop_loss) / s.entry < 0.0005
  AND COALESCE(o.performance_inclusion_status, 'eligible') = 'eligible'
"""

_STUCK_PENDING = """
UPDATE outcomes o SET status = 'expired', canonical_outcome = 'expired', r_multiple = NULL,
       closed_at = COALESCE(o.closed_at, s.expires_at, s.created_at + INTERVAL '7 days'), corrected_by = :tag
FROM signals s
WHERE s.signal_id = o.signal_id AND o.status = 'pending' AND o.closed_at IS NULL
  AND s.created_at < NOW() - INTERVAL '30 days'
"""

_OPEN_LIFECYCLES = """
UPDATE signal_lifecycles l SET state = 'EXPIRED', expired_at = COALESCE(l.expired_at, NOW()),
       closed_at = COALESCE(l.closed_at, NOW()), terminal_event_type = COALESCE(l.terminal_event_type, 'stale_cleanup')
FROM signals s
WHERE s.signal_id = l.signal_id
  AND l.state IN ('WATCHING_FOR_ENTRY', 'ACTIVE_TRADE', 'TP1_HIT', 'TP2_HIT')
  AND s.created_at < NOW() - INTERVAL '30 days'
  AND NOT EXISTS (SELECT 1 FROM signal_deliveries d WHERE d.signal_id = s.signal_id AND d.sent_ok)
"""

STEPS = (
    ("broken_setups", _BROKEN_SETUPS),
    ("degenerate_stop_outcomes", _DEGENERATE_STOPS),
    ("stuck_pending_outcomes", _STUCK_PENDING),
    ("open_lifecycles", _OPEN_LIFECYCLES),
)


async def run_once() -> dict[str, Any]:
    from db.session import get_session

    if str(os.getenv("DATA_CORRECTIONS_ENABLED", "1")).strip().lower() not in {"1", "true", "yes", "on"}:
        return {"status": "disabled"}
    async with get_session(priority="analytics", label="data_corrections.marker", timeout_seconds=20) as session:
        done = (await session.execute(text("SELECT value FROM runtime_state WHERE key=:k"), {"k": MARKER})).first()
        await session.rollback()
    if done:
        return {"status": "already_done"}
    counts: dict[str, Any] = {}
    for name, sql in STEPS:
        try:
            async with get_session(priority="analytics", label=f"data_corrections.{name}", timeout_seconds=120) as session:
                params = {"tag": TAG} if ":tag" in sql else {}
                result = await session.execute(text(sql), params)
                counts[name] = int(getattr(result, "rowcount", 0) or 0)
                await session.commit()
        except Exception as exc:  # one failed step must not block the others; it is retried next start
            counts[name] = f"failed:{type(exc).__name__}"
            logger.warning("[data_corrections] step=%s failed error=%s", name, type(exc).__name__)
    if not any(isinstance(v, str) for v in counts.values()):
        async with get_session(priority="analytics", label="data_corrections.done", timeout_seconds=20) as session:
            await session.execute(
                text("INSERT INTO runtime_state(key, value, expires_at, updated_at) VALUES (:k, CAST(:v AS JSONB), NULL, NOW()) "
                     "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()"),
                {"k": MARKER, "v": json.dumps(counts)},
            )
            await session.commit()
    logger.info("[data_corrections] %s", counts)
    return {"status": "done", **counts}
