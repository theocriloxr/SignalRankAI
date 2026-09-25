"""Worker-owned reconciliation for SignalRankAI-managed MetaApi MT4/MT5 trades.

Closure is accepted only when MetaApi deal history proves a closing deal for the
exact broker order/position identity and the matching position is no longer
open. Symbol-only or time-only matching is never used for final attribution.
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from sqlalchemy import select

from db.models import MT5Execution
from db.session import get_session
from services.mt5_client import (
    get_account_info,
    get_history_deals_by_position,
    get_history_deals_by_ticket,
    get_open_positions_snapshot,
)
from utils.timeutils import now_utc_naive

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = {
    "closed",
    "cancelled",
    "rejected",
    "failed",
    "tp",
    "tp1",
    "tp2",
    "tp3",
    "sl",
    "be",
    "breakeven",
}
_CLOSING_ENTRY_TYPES = {
    "DEAL_ENTRY_OUT",
    "DEAL_ENTRY_OUT_BY",
    "DEAL_ENTRY_INOUT",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _decimal(value: Any) -> Decimal:
    try:
        parsed = Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
    return parsed if parsed.is_finite() else Decimal("0")


def _refs(row: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for key in (
        "id",
        "ticket",
        "dealId",
        "deal_id",
        "orderId",
        "order_id",
        "positionId",
        "position_id",
    ):
        value = _text(row.get(key))
        if value:
            result.add(value)
    return result


def _deal_id(deal: dict[str, Any]) -> str:
    for key in ("id", "dealId", "deal_id", "ticket"):
        value = _text(deal.get(key))
        if value:
            return value
    return ""


def _position_ref(deals: Iterable[dict[str, Any]], fallback: str) -> str:
    for deal in deals:
        for key in ("positionId", "position_id"):
            value = _text(deal.get(key))
            if value:
                return value
    return _text(fallback)


def _merge_deals(*groups: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for raw in group:
            if not isinstance(raw, dict):
                continue
            deal = dict(raw)
            identity = _deal_id(deal)
            key = identity or repr(sorted(deal.items()))
            if key in seen:
                continue
            seen.add(key)
            merged.append(deal)
    return merged


def _exact_deals(
    deals: Iterable[dict[str, Any]],
    *,
    order_ref: str,
    position_ref: str,
) -> list[dict[str, Any]]:
    allowed = {_text(order_ref), _text(position_ref)}
    allowed.discard("")
    return [
        dict(deal)
        for deal in deals
        if isinstance(deal, dict) and bool(_refs(deal) & allowed)
    ]


def _closing_deals(deals: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(deal)
        for deal in deals
        if _text(deal.get("entryType") or deal.get("entry_type")).upper()
        in _CLOSING_ENTRY_TYPES
    ]


def _deal_time(deal: dict[str, Any]) -> datetime | None:
    raw = deal.get("time") or deal.get("timestamp")
    if raw in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # MetaApi's canonical "time" is UTC. brokerTime should only be used as
        # a last-resort display timestamp and never for freshness decisions.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _financial_summary(deals: Iterable[dict[str, Any]]) -> dict[str, Decimal]:
    profit = Decimal("0")
    commission = Decimal("0")
    swap = Decimal("0")
    fees = Decimal("0")
    for deal in deals:
        profit += _decimal(deal.get("profit"))
        commission += _decimal(deal.get("commission"))
        swap += _decimal(deal.get("swap"))
        fees += _decimal(deal.get("fee") or deal.get("fees"))
    return {
        "profit": profit,
        "commission": commission,
        "swap": swap,
        "fees": fees,
        "net": profit + commission + swap + fees,
    }


def _ledger_events(
    deals: Iterable[dict[str, Any]],
    *,
    execution: MT5Execution,
    position_ref: str,
    currency: str,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for deal in deals:
        deal_id = _deal_id(deal)
        if not deal_id:
            # Provider event identity is mandatory for idempotent persistence.
            continue
        order_ref = _text(deal.get("orderId") or deal.get("order_id")) or execution.order_id
        deal_position = (
            _text(deal.get("positionId") or deal.get("position_id"))
            or position_ref
            or None
        )
        common = {
            "correlation_id": f"mt5_execution:{execution.id}",
            "order_ref": order_ref,
            "fill_ref": deal_id,
            "position_ref": deal_position,
            "currency": currency,
            "provider_timestamp": deal.get("time"),
            "metadata": {
                "symbol": deal.get("symbol") or execution.symbol,
                "entry_type": deal.get("entryType") or deal.get("entry_type"),
                "deal_type": deal.get("type"),
                "price": deal.get("price"),
                "volume": deal.get("volume"),
                "broker_time": deal.get("brokerTime"),
            },
        }
        events.append(
            {
                **common,
                "entry_type": "fill",
                "source_event_id": f"deal:{deal_id}:fill",
            }
        )

        profit = _decimal(deal.get("profit"))
        if profit != 0:
            events.append(
                {
                    **common,
                    "entry_type": "realized_pnl",
                    "source_event_id": f"deal:{deal_id}:profit",
                    "amount": profit,
                    "realized_pnl": profit,
                }
            )

        commission = _decimal(deal.get("commission"))
        if commission != 0:
            events.append(
                {
                    **common,
                    "entry_type": "commission",
                    "source_event_id": f"deal:{deal_id}:commission",
                    "amount": commission,
                    "commission": commission,
                }
            )

        swap = _decimal(deal.get("swap"))
        if swap != 0:
            events.append(
                {
                    **common,
                    "entry_type": "swap",
                    "source_event_id": f"deal:{deal_id}:swap",
                    "amount": swap,
                    "swap": swap,
                }
            )

        fee = _decimal(deal.get("fee") or deal.get("fees"))
        if fee != 0:
            events.append(
                {
                    **common,
                    "entry_type": "fee",
                    "source_event_id": f"deal:{deal_id}:fee",
                    "amount": fee,
                    "fees": fee,
                }
            )
    return events


async def _provider_deals(
    execution: MT5Execution,
) -> tuple[list[dict[str, Any]] | None, str]:
    """Resolve complete deal history from exact provider identifiers only."""
    order_ref = _text(execution.order_id)
    if not order_ref:
        return [], ""

    ticket_deals = await get_history_deals_by_ticket(
        str(execution.metaapi_account_id),
        order_ref,
    )
    if ticket_deals is None:
        return None, ""

    position_ref = _position_ref(ticket_deals, order_ref)
    position_deals = await get_history_deals_by_position(
        str(execution.metaapi_account_id),
        position_ref,
    )
    if position_deals is None:
        return None, position_ref

    merged = _merge_deals(ticket_deals, position_deals)
    exact = _exact_deals(
        merged,
        order_ref=order_ref,
        position_ref=position_ref,
    )
    return exact, position_ref


async def _persist_reconciliation(
    execution: MT5Execution,
    *,
    deals: list[dict[str, Any]],
    position_ref: str,
    active_refs: set[str],
    currency: str,
) -> str:
    from services.trading_account_ledger import _append_account_ledger_in_session

    closing = _closing_deals(deals)
    active = bool(active_refs & ({_text(execution.order_id), _text(position_ref)} - {""}))
    summary = _financial_summary(deals)
    now = now_utc_naive()

    async with get_session(label="mt5.reconcile.write", timeout_seconds=8.0) as session:
        row = (
            await session.execute(
                select(MT5Execution)
                .where(MT5Execution.id == int(execution.id))
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            return "missing"
        if str(row.status or "").strip().lower() in _TERMINAL_STATUSES:
            return "terminal"

        if row.connection_id:
            for event in _ledger_events(
                deals,
                execution=row,
                position_ref=position_ref,
                currency=currency,
            ):
                await _append_account_ledger_in_session(
                    session,
                    user_id=int(row.user_id),
                    connection_id=str(row.connection_id),
                    provider="metaapi",
                    **event,
                )

        meta = {
            **dict(row.meta or {}),
            "provider_position_id": position_ref or None,
            "last_reconciled_at": now.isoformat(),
            "provider_deal_count": len(deals),
            "provider_gross_profit": str(summary["profit"]),
            "provider_commission": str(summary["commission"]),
            "provider_swap": str(summary["swap"]),
            "provider_fees": str(summary["fees"]),
        }

        if active:
            row.status = "open"
            row.meta = meta
            await session.commit()
            return "open"

        if not closing:
            row.meta = {
                **meta,
                "reconciliation_state": "awaiting_exact_closing_deal",
            }
            await session.commit()
            return "pending"

        closed_times = [
            value for value in (_deal_time(deal) for deal in closing) if value is not None
        ]
        row.status = "closed"
        row.realized_pnl = float(summary["net"])
        row.closed_at = (
            max(closed_times).replace(tzinfo=None)
            if closed_times
            else now
        )
        row.meta = {
            **meta,
            "reconciliation_state": "closed_by_exact_provider_deal",
            "realized_pnl_net": str(summary["net"]),
        }
        await session.commit()
        return "closed"


async def reconcile_mt5_executions_once(*, limit: int = 100) -> dict[str, int]:
    """Reconcile non-terminal MT4/MT5 executions from MetaApi broker history."""
    stats = {
        "fetched": 0,
        "open": 0,
        "closed": 0,
        "pending": 0,
        "errors": 0,
    }
    async with get_session(label="mt5.reconcile.scan", timeout_seconds=8.0) as session:
        rows = (
            await session.execute(
                select(MT5Execution)
                .where(
                    MT5Execution.connection_id.is_not(None),
                    MT5Execution.order_id.is_not(None),
                    MT5Execution.status.notin_(tuple(_TERMINAL_STATUSES)),
                )
                .order_by(MT5Execution.executed_at.asc())
                .limit(max(1, min(int(limit), 500)))
            )
        ).scalars().all()
        for row in rows:
            session.expunge(row)
        await session.rollback()

    stats["fetched"] = len(rows)
    grouped: dict[str, list[MT5Execution]] = defaultdict(list)
    for row in rows:
        grouped[str(row.metaapi_account_id)].append(row)

    for account_id, executions in grouped.items():
        try:
            positions = await get_open_positions_snapshot(account_id)
            if positions is None:
                stats["errors"] += len(executions)
                continue
            active_refs: set[str] = set()
            for position in positions:
                active_refs.update(_refs(position))

            account_info = await get_account_info(account_id)
            if not isinstance(account_info, dict):
                stats["errors"] += len(executions)
                continue
            currency = _text(account_info.get("currency")).upper() or "USD"

            for execution in executions:
                try:
                    deals, position_ref = await _provider_deals(execution)
                    if deals is None:
                        stats["errors"] += 1
                        continue
                    state = await _persist_reconciliation(
                        execution,
                        deals=deals,
                        position_ref=position_ref,
                        active_refs=active_refs,
                        currency=currency,
                    )
                    if state in stats:
                        stats[state] += 1
                except Exception:
                    logger.exception(
                        "MT5 reconciliation failed execution=%s",
                        execution.id,
                    )
                    stats["errors"] += 1
        except Exception:
            logger.exception("MT5 reconciliation failed account=%s", account_id)
            stats["errors"] += len(executions)

    return stats


async def mt5_reconciliation_loop(stop_event: asyncio.Event) -> None:
    interval = max(
        15,
        int(os.getenv("MT5_RECONCILIATION_INTERVAL_SECONDS", "30") or 30),
    )
    batch = max(
        1,
        int(os.getenv("MT5_RECONCILIATION_BATCH_SIZE", "100") or 100),
    )
    logger.info(
        "[mt5_reconciler] started interval=%ss batch=%s",
        interval,
        batch,
    )
    while not stop_event.is_set():
        try:
            stats = await reconcile_mt5_executions_once(limit=batch)
            if stats["fetched"]:
                logger.info("[mt5_reconciler] %s", stats)
        except Exception:
            logger.exception("[mt5_reconciler] iteration failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue


__all__ = [
    "mt5_reconciliation_loop",
    "reconcile_mt5_executions_once",
]
