"""Prop-account dashboard: limit usage, trading days and target progress (CX-PROP-04, 30 Oct 2026).

Everything is computed from the account's own records: its policy and the
broker-proven ledger (equity snapshots, realized P&L, fills). Daily loss and
total drawdown use the same formulas and effective limits as the execution
gate (core/account_policy.py), so the meters show what the gate enforces.

Profit target, minimum trading days and starting balance are *objectives* the
account owner enters from their firm's rules. They are stored on the
connection, never in the risk policy, and no gate reads them: editing them
cannot change what orders are allowed, so it does not reset certification.
Nothing is invented: a missing objective or missing equity data is reported
as unavailable, never as zero.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from core.account_policy import _effective_limit

OBJECTIVE_KEYS = ("starting_balance", "profit_target_pct", "min_trading_days")
SNAPSHOT_TYPES = ("equity_snapshot", "balance_snapshot")
STALE_AFTER_SECONDS = 900
HISTORY_DAYS = 180


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return out if out.is_finite() else None


def validate_objectives(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return normalized objectives; unknown keys or out-of-range values are refused."""
    payload = dict(raw or {})
    unknown = sorted(set(payload) - set(OBJECTIVE_KEYS))
    if unknown:
        raise ValueError("unknown_objective:" + ",".join(unknown))
    out: dict[str, Any] = {}
    if payload.get("starting_balance") not in (None, ""):
        value = _dec(payload["starting_balance"])
        if value is None or value <= 0 or value > Decimal("1e12"):
            raise ValueError("invalid_starting_balance")
        out["starting_balance"] = str(value)
    if payload.get("profit_target_pct") not in (None, ""):
        value = _dec(payload["profit_target_pct"])
        if value is None or value <= 0 or value > 1:
            raise ValueError("invalid_profit_target_pct")  # a fraction: 0.08 means 8 %
        out["profit_target_pct"] = str(value)
    if payload.get("min_trading_days") not in (None, ""):
        try:
            days = int(payload["min_trading_days"])
        except (TypeError, ValueError):
            raise ValueError("invalid_min_trading_days") from None
        if days < 0 or days > 365:
            raise ValueError("invalid_min_trading_days")
        out["min_trading_days"] = days
    return out


def _zone(name: str | None) -> ZoneInfo | timezone:
    try:
        return ZoneInfo(str(name or "UTC"))
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc


def _when(row: Mapping[str, Any]) -> datetime:
    stamp = row.get("provider_timestamp") or row.get("created_at")
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)


def _ratio(used: Decimal | None, limit: Decimal | None) -> str | None:
    if used is None or limit is None or limit <= 0:
        return None
    return str((used / limit).quantize(Decimal("0.0001")))


def summarize(policy: Mapping[str, Any], entries: list[Mapping[str, Any]], objectives: Mapping[str, Any],
              now: datetime) -> dict[str, Any]:
    """Pure computation over one account's policy, ledger rows and objectives."""
    zone = _zone(policy.get("reset_timezone"))
    local_now = now.astimezone(zone)
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    unavailable: list[str] = []

    snapshots = sorted(
        ((_when(e), _dec(e.get("equity")) or _dec(e.get("balance")))
         for e in entries if e.get("entry_type") in SNAPSHOT_TYPES),
        key=lambda pair: pair[0])
    snapshots = [(when, value) for when, value in snapshots if value is not None and value > 0]
    current = peak = day_start_equity = first = None
    latest_at = None
    if snapshots:
        first, current = snapshots[0][1], snapshots[-1][1]
        latest_at = snapshots[-1][0]
        peak = max(value for _, value in snapshots)
        before_today = [value for when, value in snapshots if when < day_start]
        today = [value for when, value in snapshots if when >= day_start]
        day_start_equity = before_today[-1] if before_today else (today[0] if today else None)
    else:
        unavailable.append("no_equity_snapshots")
    stale = latest_at is None or (now - latest_at).total_seconds() > STALE_AFTER_SECONDS
    if snapshots and stale:
        unavailable.append("latest_snapshot_stale")

    realized_today = sum((_dec(e.get("realized_pnl")) or _dec(e.get("amount")) or Decimal("0"))
                         for e in entries if e.get("entry_type") == "realized_pnl" and _when(e) >= day_start)
    daily_loss = drawdown = None
    if current and day_start_equity and peak:
        # Same formulas as core.account_policy.evaluate_account_policy.
        daily_loss = max(Decimal("0"), (day_start_equity - current) / day_start_equity,
                         -Decimal(realized_today) / day_start_equity)
        drawdown = max(Decimal("0"), (peak - current) / peak)

    buffer = _dec(policy.get("safety_buffer_pct")) or Decimal("0")
    daily_limit = _effective_limit(_dec(policy.get("max_daily_loss_pct")) or Decimal("0"),
                                   _dec(policy.get("external_max_daily_loss_pct")), buffer)
    drawdown_limit = _effective_limit(_dec(policy.get("max_total_drawdown_pct")) or Decimal("0"),
                                      _dec(policy.get("external_max_total_drawdown_pct")), buffer)

    fill_days = sorted({_when(e).astimezone(zone).date().isoformat() for e in entries if e.get("entry_type") == "fill"})
    starting = _dec(objectives.get("starting_balance"))
    starting_source = "objective" if starting else ("first_snapshot" if first else None)
    starting = starting or first
    target = _dec(objectives.get("profit_target_pct"))
    progress = (current - starting) / starting if current and starting else None
    min_days = objectives.get("min_trading_days")

    def text(value: Decimal | None, places: str = "0.000001") -> str | None:
        return str(value.quantize(Decimal(places))) if value is not None else None

    return {
        "account_mode": policy.get("account_mode"),
        "prop_firm": policy.get("prop_firm"),
        "prop_phase": policy.get("prop_phase"),
        "certified": bool(policy.get("certified")),
        "frozen": bool(policy.get("frozen")),
        "currency": policy.get("currency"),
        "reset_timezone": str(policy.get("reset_timezone") or "UTC"),
        "evidence": {"snapshots": len(snapshots), "latest_snapshot_at": latest_at.isoformat() if latest_at else None,
                     "stale": stale, "stale_after_seconds": STALE_AFTER_SECONDS},
        "equity": {"current": text(current, "0.01"), "day_start": text(day_start_equity, "0.01"),
                   "peak": text(peak, "0.01"), "starting": text(starting, "0.01"), "starting_source": starting_source},
        "daily_loss": {"used_pct": text(daily_loss), "limit_pct": text(daily_limit),
                       "used_of_limit": _ratio(daily_loss, daily_limit)},
        "total_drawdown": {"used_pct": text(drawdown), "limit_pct": text(drawdown_limit),
                           "used_of_limit": _ratio(drawdown, drawdown_limit)},
        "trading_days": {"count": len(fill_days), "minimum": min_days, "last_trading_day": fill_days[-1] if fill_days else None},
        "profit_target": {"target_pct": text(target), "progress_pct": text(progress),
                          "progress_of_target": _ratio(progress, target) if progress is not None and progress > 0 else
                          ("0.0000" if progress is not None and target else None)},
        "objectives": dict(objectives),
        "unavailable": unavailable,
        "note": "Loss and drawdown use the execution gate's formulas and effective limits. Objectives are display-only.",
    }


async def prop_dashboard(user_id: int, connection_id: str, *, now: datetime | None = None) -> dict[str, Any]:
    from db.models import TradingAccountLedgerEntry
    from db.session import get_session
    from services.account_policies import _owned_connection, get_account_policy

    policy = await get_account_policy(int(user_id), connection_id)  # LookupError when absent
    moment = now or datetime.now(timezone.utc)
    since = (moment - timedelta(days=HISTORY_DAYS)).replace(tzinfo=None)
    async with get_session(label="prop_dashboard.read", timeout_seconds=8.0) as session:
        connection = await _owned_connection(session, user_id=int(user_id), connection_id=connection_id)
        rows = (await session.execute(
            select(TradingAccountLedgerEntry)
            .where(TradingAccountLedgerEntry.user_id == int(user_id),
                   TradingAccountLedgerEntry.connection_id == str(connection_id),
                   TradingAccountLedgerEntry.entry_type.in_(SNAPSHOT_TYPES + ("realized_pnl", "fill")),
                   TradingAccountLedgerEntry.created_at >= since)
            .order_by(TradingAccountLedgerEntry.created_at)
        )).scalars().all()
        objectives = dict((connection.meta or {}).get("prop_objectives") or {})
        # Read before rollback: rollback expires loaded rows.
        entries = [{"entry_type": r.entry_type, "equity": r.equity, "balance": r.balance, "amount": r.amount,
                    "realized_pnl": r.realized_pnl, "provider_timestamp": r.provider_timestamp,
                    "created_at": r.created_at} for r in rows]
        await session.rollback()
    return {"connection_id": str(connection_id), **summarize(policy, entries, objectives, moment)}


async def set_prop_objectives(user_id: int, connection_id: str, raw: Mapping[str, Any]) -> dict[str, Any]:
    """Store display-only objectives on the connection; the risk policy is untouched."""
    from db.session import get_session
    from services.account_policies import _owned_connection
    from utils.timeutils import now_utc_naive

    objectives = validate_objectives(raw)
    async with get_session(label="prop_dashboard.objectives", timeout_seconds=8.0) as session:
        connection = await _owned_connection(session, user_id=int(user_id), connection_id=connection_id, lock=True)
        meta = dict(connection.meta or {})
        meta["prop_objectives"] = objectives
        connection.meta = meta
        connection.updated_at = now_utc_naive()
        await session.commit()
    return objectives


__all__ = ["OBJECTIVE_KEYS", "prop_dashboard", "set_prop_objectives", "summarize", "validate_objectives"]
