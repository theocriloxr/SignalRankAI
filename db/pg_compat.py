from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict

from db.session import get_session
from db.session import get_database_url_or_none
from utils.async_runner import run_sync

logger = logging.getLogger(__name__)


def _run(coro, *, timeout: float | None = None):
    # Use run_sync shim which safely runs coroutines when an event loop
    # may already be active. This avoids RuntimeError in environments
    # where parts of the app already have a running loop.
    return run_sync(coro, timeout=timeout)


def _signal_store_context(signal: Dict[str, Any]) -> dict[str, Any]:
    targets = signal.get("take_profit") or signal.get("targets") or []
    tp1 = None
    try:
        if isinstance(targets, (list, tuple)) and targets:
            tp1 = targets[0]
        elif isinstance(targets, str) and targets.strip():
            import json
            parsed = json.loads(targets)
            if isinstance(parsed, list) and parsed:
                tp1 = parsed[0]
    except Exception:
        tp1 = signal.get("tp1")
    return {
        "asset": signal.get("asset") or signal.get("symbol"),
        "direction": signal.get("direction"),
        "timeframe": signal.get("timeframe"),
        "score": signal.get("score"),
        "fingerprint": signal.get("fingerprint") or signal.get("signal_fingerprint"),
        "entry": signal.get("entry"),
        "stop_loss": signal.get("stop_loss") or signal.get("stop"),
        "tp1": signal.get("tp1") or tp1,
    }


def postgres_enabled() -> bool:
    # Use get_database_url_or_none() so that a missing DATABASE_URL returns
    # False (safe) instead of raising ValueError (which propagates through
    # bool() and crashes the caller).
    return bool(get_database_url_or_none())


def get_all_user_ids_compat() -> list[int]:
    """Postgres-only. Returns all telegram user IDs."""
    if not postgres_enabled():
        raise RuntimeError("DATABASE_URL not configured. Postgres is required.")

    async def _impl() -> list[int]:
        from db.pg_features import list_all_user_telegram_ids

        async with get_session() as session:
            ids = await list_all_user_telegram_ids(session)
            return ids

    return _run(_impl())


def store_signal_compat(signal: Dict[str, Any]) -> str:
    """Postgres-only. Store a signal and return its ID.

    This is a critical path: if it fails, final signals never reach delivery.
    It therefore uses the critical DB gate and a dedicated timeout instead of
    the generic background-write timeout.
    """
    if not postgres_enabled():
        raise RuntimeError("DATABASE_URL not configured. Postgres is required.")

    ctx = _signal_store_context(signal)
    timeout_s = float(os.getenv("SIGNAL_STORE_TIMEOUT_SECONDS", "45") or 45)
    retries = int(os.getenv("SIGNAL_STORE_RETRY_ATTEMPTS", "1") or 1)

    async def _impl() -> str:
        from db.pg_features import SignalDedupBlocked, get_or_create_signal
        from db.session import get_session, run_with_db_retry

        dedup_hours = signal.get("dedup_hours", signal.get("_dedup_hours"))
        if dedup_hours is None:
            try:
                dedup_hours = int((os.getenv("SIGNAL_DEDUP_HOURS") or "24").strip())
            except Exception:
                dedup_hours = 24
        else:
            try:
                dedup_hours = int(dedup_hours)
            except Exception:
                dedup_hours = 24

        wait_started = time.monotonic()
        async with get_session(critical=True) as session:
            db_wait_ms = int((time.monotonic() - wait_started) * 1000)
            exec_started = time.monotonic()
            try:
                async def _op():
                    return await get_or_create_signal(session, signal, dedup_hours=dedup_hours)

                s = await run_with_db_retry(
                    _op,
                    retries=max(0, retries),
                    base_delay_s=0.25,
                    max_delay_s=1.0,
                )
            except SignalDedupBlocked as exc:
                logger.warning(
                    "[store_signal] blocked reason=%s asset=%s timeframe=%s direction=%s signal_id=%s",
                    getattr(exc, "reason", str(exc)),
                    ctx.get("asset"),
                    ctx.get("timeframe"),
                    ctx.get("direction"),
                    getattr(exc, "signal_id", None),
                )
                return str(exc.signal_id or "")
            await session.commit()
            db_exec_ms = int((time.monotonic() - exec_started) * 1000)
            logger.info(
                "[store_signal] stored signal_id=%s asset=%s tf=%s dir=%s score=%s db_wait_ms=%s db_exec_ms=%s",
                getattr(s, "signal_id", None),
                ctx.get("asset"),
                ctx.get("timeframe"),
                ctx.get("direction"),
                ctx.get("score"),
                db_wait_ms,
                db_exec_ms,
            )
            return str(s.signal_id)

    try:
        return _run(_impl(), timeout=timeout_s)
    except Exception as exc:
        logger.exception(
            "[store_signal] failed asset=%s direction=%s timeframe=%s score=%s fingerprint=%s entry=%s stop_loss=%s tp1=%s store_stage=store_signal_compat timeout_seconds=%s exception_type=%s message=%s",
            ctx.get("asset"),
            ctx.get("direction"),
            ctx.get("timeframe"),
            ctx.get("score"),
            ctx.get("fingerprint"),
            ctx.get("entry"),
            ctx.get("stop_loss"),
            ctx.get("tp1"),
            timeout_s,
            type(exc).__name__,
            str(exc),
        )
        raise
