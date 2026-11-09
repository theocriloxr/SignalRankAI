"""Where the ML model stands, recorded so it survives container restarts (9 Nov 2026).

Owner request: "fix the ML model". Production served the 29 Sep champion for six
weeks; on live candidates its median probability was 1% (crypto) and 3%
(others), far below the realised TP1 rates. Why it was not replaced could not
be established: ``sr grep`` only sees the current container's log, and a
training run leaves no durable trace when it is skipped (an active challenger
holding the forward-proof lease), rejected (offline quality or champion
comparison) or promoted only to candidate (promotion stays an owner decision,
``/ml_candidate_promote CONFIRM``).

This module records the outcome of every training run and the champion's age
in Redis state. ``/readyz`` shows them (``ml_lifecycle``, informational) and
the owner-alert loop warns when the champion is stale, naming the reason.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

LAST_RUN_KEY = "signalrankai:ml:last_training_run"
CHAMPION_KEY = "signalrankai:ml:champion_status"
_KEEP_PREFIXES = ("[ml_training_run]", "[ml_external_replay]", "[ml_temporal_split]", "[ml_dataset]",
                  "[ml_quality", "[ml_champion", "[ml_promotion", "[ml_schema")


class _RunCapture(logging.Handler):
    """Keeps the trainer's own decision lines for one run (bounded)."""

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:
            return
        if message.startswith(_KEEP_PREFIXES) and len(self.lines) < 40:
            self.lines.append(message[:400])


def summarise(lines: list[str], ok: bool | None) -> dict[str, Any]:
    """The decisive line of a run: the last one with a status=."""
    status_line = next((line for line in reversed(lines) if "status=" in line), "")
    status = "unknown"
    reason = ""
    for part in status_line.split():
        if part.startswith("status="):
            status = part.split("=", 1)[1]
        elif part.startswith("reason="):
            reason = part.split("=", 1)[1]
    if ok is True and status == "unknown":
        status = "completed"
    return {"status": status, "reason": reason, "decisive_line": status_line[:400]}


async def run_and_record(train_main, *args, **kwargs):
    """Run ``ml.train_model.main`` and record its outcome; returns what main returned."""
    capture = _RunCapture()
    train_logger = logging.getLogger("ml.train_model")
    train_logger.addHandler(capture)
    previous_level = train_logger.level
    if not train_logger.isEnabledFor(logging.INFO):
        train_logger.setLevel(logging.INFO)
    started = datetime.now(timezone.utc)
    result = None
    error = None
    try:
        result = await train_main(*args, **kwargs)
        return result
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:300]
        raise
    finally:
        train_logger.removeHandler(capture)
        train_logger.setLevel(previous_level)
        record = {
            "started_at": started.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "returned": None if result is None else bool(result),
            "error": error,
            **summarise(capture.lines, None if result is None else bool(result)),
            "lines": capture.lines[-12:],
        }
        try:
            from core.redis_state import state

            state.set_sync(LAST_RUN_KEY, json.dumps(record, default=str), ex=60 * 86400)
        except Exception:
            logger.debug("[ml_lifecycle] last run not recorded", exc_info=True)


def record_champion(status: dict[str, Any]) -> None:
    """Called where the champion's integrity status is computed (readiness)."""
    trained_at = str(status.get("trained_at") or "")
    if not trained_at:
        return
    try:
        from core.redis_state import state

        state.set_sync(CHAMPION_KEY, json.dumps({"trained_at": trained_at,
                                                  "version": status.get("version"),
                                                  "validated": status.get("validated"),
                                                  "seen_at": datetime.now(timezone.utc).isoformat()}),
                       ex=30 * 86400)
    except Exception:
        logger.debug("[ml_lifecycle] champion status not recorded", exc_info=True)


def _load(key: str) -> dict[str, Any]:
    try:
        from core.redis_state import state

        raw = state.get_sync(key)
    except Exception:
        return {}
    if not raw:
        return {}
    try:
        value = json.loads(raw) if isinstance(raw, (str, bytes)) else dict(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def champion_age_days(trained_at: str | None, *, now: datetime | None = None) -> float | None:
    if not trained_at:
        return None
    try:
        stamp = datetime.fromisoformat(str(trained_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return round(((now or datetime.now(timezone.utc)) - stamp).total_seconds() / 86400.0, 1)


def stale_after_days() -> float:
    try:
        return max(1.0, float(os.getenv("ML_CHAMPION_STALE_DAYS", "14") or 14))
    except ValueError:
        return 14.0


def explain(last_run: dict[str, Any]) -> str:
    """Plain-language reason the champion was not replaced by the last run."""
    reason = str(last_run.get("reason") or "")
    status = str(last_run.get("status") or "")
    line = str(last_run.get("decisive_line") or "")
    if "active_candidate_forward_lease" in reason or "active_candidate_forward_lease" in line:
        if "status_detail=eligible" in line:
            return ("a challenger passed forward proof and is waiting for your approval: "
                    "send /ml_candidate_promote CONFIRM")
        return "a challenger is still collecting forward evidence (training waits up to 48 h)"
    if status == "candidate_only" or "insufficient_live_proof" in reason:
        return "too few delivered outcomes to promote (ML_MIN_LIVE_PROOF_ROWS)"
    if "insufficient" in reason:
        return f"not enough training data ({reason})"
    if "quality" in reason or "champion" in reason or "noninferior" in line:
        return f"the new model failed a promotion check ({reason or status})"
    if last_run.get("error"):
        return f"training crashed: {last_run['error']}"
    if not last_run:
        return "no training run recorded since this check was added"
    return f"last run: {status}{(' ' + reason) if reason else ''}"


def lifecycle_status(*, now: datetime | None = None) -> dict[str, Any]:
    champion = _load(CHAMPION_KEY)
    last_run = _load(LAST_RUN_KEY)
    age = champion_age_days(champion.get("trained_at"), now=now)
    limit = stale_after_days()
    return {
        "ok": True,  # informational: the model is advisory and never blocks readiness
        "required": False,
        "champion_trained_at": champion.get("trained_at"),
        "champion_age_days": age,
        "stale": age is not None and age > limit,
        "stale_after_days": limit,
        "last_training_run": {k: last_run.get(k) for k in ("status", "reason", "finished_at", "returned", "error")}
        if last_run else None,
        "why_not_replaced": explain(last_run),
    }
