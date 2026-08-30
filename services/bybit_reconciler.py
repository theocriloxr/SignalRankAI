"""Worker-owned reconciliation for SignalRankAI-managed Bybit positions."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from db.models import BrokerExecution, RuntimeState, User
from db.session import get_session
from services.bybit_client import BybitCredentials, BybitError, BybitV5Client
from services.security import decrypt_secret
from services.execution_quota import release_user_execution_quota
from utils.timeutils import now_utc_naive

logger = logging.getLogger(__name__)

_TERMINAL_ORDER_REJECTS = {"rejected", "cancelled", "deactivated"}
_FILLED_ORDER_STATES = {"filled", "partiallyfilled"}


def _state_key(telegram_user_id: int) -> str:
    return f"broker_exchange:{int(telegram_user_id)}:bybit"


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _created_ms(row: BrokerExecution) -> int:
    created = row.created_at or now_utc_naive()
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return max(0, int(created.timestamp() * 1000) - 60_000)


async def _credentials(telegram_user_id: int) -> BybitCredentials | None:
    async with get_session(label="bybit.reconcile.credentials", timeout_seconds=6.0) as session:
        state = await session.get(RuntimeState, _state_key(int(telegram_user_id)))
    value = dict(getattr(state, "value", {}) or {}) if state is not None else {}
    key = decrypt_secret(str(value.get("api_key_enc") or ""))
    secret = decrypt_secret(str(value.get("api_secret_enc") or ""))
    if not key or not secret:
        return None
    return BybitCredentials(str(key), str(secret), bool(value.get("sandbox", True)))


async def _mark(row_id: int, *, status: str, error: str | None = None, meta: dict[str, Any] | None = None,
                realized_pnl_pct: float | None = None, closed: bool = False) -> None:
    async with get_session(label="bybit.reconcile.write", timeout_seconds=8.0) as session:
        row = (
            await session.execute(
                select(BrokerExecution).where(BrokerExecution.id == int(row_id)).with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            return
        row.status = str(status)
        row.error_code = str(error or "")[:128] or None
        row.updated_at = now_utc_naive()
        if meta:
            row.meta = {**dict(row.meta or {}), **meta}
        if realized_pnl_pct is not None:
            row.realized_pnl_pct = float(realized_pnl_pct)
        if closed:
            row.closed_at = now_utc_naive()
        await session.commit()


async def reconcile_bybit_executions_once(*, limit: int = 100) -> dict[str, int]:
    """Reconcile non-terminal Bybit executions; all uncertainty remains fail-closed."""
    stats = {"fetched": 0, "open": 0, "closed": 0, "rejected": 0, "errors": 0}
    async with get_session(label="bybit.reconcile.scan", timeout_seconds=8.0) as session:
        rows = (
            await session.execute(
                select(BrokerExecution, User.telegram_user_id)
                .join(User, User.id == BrokerExecution.user_id)
                .where(
                    BrokerExecution.provider == "bybit",
                    BrokerExecution.status.in_(("reserved", "submitting", "ambiguous", "confirmed", "open", "reconciliation_pending")),
                )
                .order_by(BrokerExecution.created_at.asc())
                .limit(max(1, int(limit)))
            )
        ).all()
    stats["fetched"] = len(rows)

    for execution, telegram_user_id in rows:
        try:
            creds = await _credentials(int(telegram_user_id))
            if creds is None:
                await _mark(int(execution.id), status=str(execution.status), error="credentials_unavailable")
                stats["errors"] += 1
                continue
            client = BybitV5Client(creds)
            order = await client.get_order(
                symbol=str(execution.symbol),
                order_id=str(execution.provider_order_id or "") or None,
                order_link_id=str(execution.provider_client_order_id or "") or None,
            )
            order_status = str((order or {}).get("orderStatus") or "").strip().lower()
            if order_status in _TERMINAL_ORDER_REJECTS:
                await _mark(int(execution.id), status=order_status, error=f"bybit_order_{order_status}", closed=True)
                await release_user_execution_quota(int(execution.user_id))
                stats["rejected"] += 1
                continue

            positions = await client.get_positions(symbol=str(execution.symbol))
            active = next((item for item in positions if _as_float(item.get("size")) > 0), None)
            if active is not None:
                await _mark(
                    int(execution.id), status="open",
                    meta={
                        "order_status": order_status or None,
                        "position_size": active.get("size"),
                        "avg_entry_price": active.get("avgPrice"),
                        "position_idx": active.get("positionIdx"),
                        "last_reconciled_at": now_utc_naive().isoformat(),
                    },
                )
                stats["open"] += 1
                continue

            # Never infer closure before the entry order was filled or the row was previously open.
            if order_status not in _FILLED_ORDER_STATES and str(execution.status) != "open":
                await _mark(
                    int(execution.id), status=str(execution.status),
                    meta={"order_status": order_status or None, "last_reconciled_at": now_utc_naive().isoformat()},
                )
                continue

            closed_rows = await client.get_closed_pnl(
                symbol=str(execution.symbol), start_time_ms=_created_ms(execution), limit=20,
            )
            closed = next(
                (
                    item for item in closed_rows
                    if int(_as_float(item.get("updatedTime") or item.get("createdTime"))) >= _created_ms(execution)
                ),
                None,
            )
            if closed is None:
                await _mark(
                    int(execution.id), status="reconciliation_pending",
                    meta={"order_status": order_status or None, "last_reconciled_at": now_utc_naive().isoformat()},
                )
                stats["errors"] += 1
                continue
            pnl = _as_float(closed.get("closedPnl"))
            entry_value = abs(_as_float(closed.get("cumEntryValue")))
            pnl_pct = (pnl / entry_value * 100.0) if entry_value > 0 else 0.0
            await _mark(
                int(execution.id), status="closed", realized_pnl_pct=pnl_pct, closed=True,
                meta={
                    "closed_pnl": pnl,
                    "closed_pnl_pct": pnl_pct,
                    "avg_exit_price": closed.get("avgExitPrice"),
                    "close_order_id": closed.get("orderId"),
                    "last_reconciled_at": now_utc_naive().isoformat(),
                },
            )
            stats["closed"] += 1
        except BybitError as exc:
            logger.warning("Bybit reconciliation provider error execution=%s: %s", execution.id, exc)
            stats["errors"] += 1
        except Exception:
            logger.exception("Bybit reconciliation failed execution=%s", execution.id)
            stats["errors"] += 1
    return stats


async def bybit_reconciliation_loop(stop_event: asyncio.Event) -> None:
    interval = max(15, int(os.getenv("BYBIT_RECONCILIATION_INTERVAL_SECONDS", "30") or 30))
    batch = max(1, int(os.getenv("BYBIT_RECONCILIATION_BATCH_SIZE", "100") or 100))
    logger.info("[bybit_reconciler] started interval=%ss batch=%s", interval, batch)
    while not stop_event.is_set():
        try:
            stats = await reconcile_bybit_executions_once(limit=batch)
            if stats["fetched"]:
                logger.info("[bybit_reconciler] %s", stats)
        except Exception:
            logger.exception("[bybit_reconciler] iteration failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue


__all__ = ["bybit_reconciliation_loop", "reconcile_bybit_executions_once"]
