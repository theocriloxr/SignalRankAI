"""Persistent, per-user paper trading for delivered SignalRankAI signals.

The service is deliberately isolated from broker execution. It consumes only
Telegram-confirmed signal deliveries, creates virtual fills, marks positions to
live market prices, and persists a separate paper-trading ledger.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any, Iterable, Optional
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import IntegrityError

from db.models import (
    Outcome,
    PaperAccount,
    PaperLedgerEntry,
    PaperPosition,
    PaperTradeAttempt,
    Signal,
    SignalDelivery,
    SignalLifecycle,
    User,
)
from core.delivery_state import CONFIRMED_DELIVERY_STATES
from core.production_integrity import evaluate_signal_freshness, signal_thesis_fingerprint
from db.session import NoncriticalWriteDropped, get_session
from utils.timeutils import now_utc_naive

logger = logging.getLogger(__name__)


TERMINAL_OUTCOMES = {
    "tp", "tp1", "tp2", "tp3", "sl", "stop", "stopped", "expired",
    "missed", "cancelled", "closed", "win", "loss", "partial_win",
}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "y"}


def _env_float(name: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        value = float((os.getenv(name) or str(default)).strip())
    except Exception:
        value = float(default)
    if minimum is not None:
        value = max(float(minimum), value)
    if maximum is not None:
        value = min(float(maximum), value)
    return value


def _env_int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(float((os.getenv(name) or str(default)).strip()))
    except Exception:
        value = int(default)
    if minimum is not None:
        value = max(int(minimum), value)
    if maximum is not None:
        value = min(int(maximum), value)
    return value


def _paper_worker_priority() -> str:
    # Full-system staging tests must exercise the paper workflow rather than
    # repeatedly deferring it behind the foreground reservation. Runtime safety
    # sets the ACTIVE marker only after validating the exact acknowledgement and
    # confirming that the Railway environment is non-production.
    if str(os.getenv("FULL_SYSTEM_STAGING_TEST_ACTIVE") or "").strip() == "1":
        return "interactive"
    value = str(os.getenv("PAPER_WORKER_DB_PRIORITY") or "background").strip().lower()
    return value if value in {"interactive", "critical", "background", "analytics"} else "background"


def _paper_db_timeout(default: float = 8.0) -> float:
    return _env_float("PAPER_DB_TIMEOUT_SECONDS", default, 0.5, 60.0)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        value_f = float(value)
        if math.isfinite(value_f):
            return value_f
    except Exception:
        pass
    return float(default)


def parse_targets(raw: Any) -> list[float]:
    if raw is None:
        return []
    value = raw
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            value = json.loads(text)
        except Exception:
            value = [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]
    if isinstance(value, dict):
        ordered: list[Any] = []
        for key in ("tp1", "tp2", "tp3", "target", "price", "value"):
            if key in value:
                ordered.append(value[key])
        value = ordered or list(value.values())
    if not isinstance(value, (list, tuple)):
        value = [value]
    out: list[float] = []
    for item in value:
        if isinstance(item, dict):
            item = item.get("price") or item.get("target") or item.get("tp") or item.get("value")
        parsed = _safe_float(item)
        if parsed > 0:
            out.append(parsed)
    return out[:3]


def canonical_direction(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "long" if text in {"long", "buy", "bull", "bullish"} else "short"


def position_max_age_hours(timeframe: str | None = None) -> float:
    """Policy max age (hours) for an open paper position before it is stale.

    Per-timeframe conservative defaults; override with
    ``PAPER_POSITION_MAX_AGE_HOURS``.  Prevents orphaned positions from
    blocking new signals forever.
    """
    explicit = os.getenv("PAPER_POSITION_MAX_AGE_HOURS")
    if explicit:
        try:
            return max(1.0, float(explicit))
        except (TypeError, ValueError):
            pass
    tf = str(timeframe or "").lower().strip()
    defaults = {
        "1m": 4.0, "3m": 6.0, "5m": 12.0, "15m": 18.0, "30m": 24.0,
        "1h": 48.0, "2h": 72.0, "4h": 120.0, "1d": 336.0, "1w": 720.0,
    }
    return defaults.get(tf, 72.0)


def canonical_asset_class(asset: str, value: Any = None) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "forex": "fx", "equity": "stock", "equities": "stock",
        "stocks": "stock", "indices": "index", "commodities": "commodity",
        "rates": "macro", "yield": "macro", "yields": "macro",
    }
    if text:
        return aliases.get(text, text)
    try:
        from engine.price_fetcher import get_asset_class
        return aliases.get(get_asset_class(asset), get_asset_class(asset))
    except Exception:
        return "unknown"


@dataclass(frozen=True)
class PaperSnapshot:
    telegram_user_id: int | None
    user_id: int
    identity: str
    starting_balance: float
    cash_balance: float
    equity: float
    reserved_cash: float
    unrealized_pnl: float
    realized_pnl: float
    open_positions: int
    closed_positions: int
    auto_trade_enabled: bool
    risk_pct: float
    max_open_positions: int
    min_signal_score: float
    spread_bps: float
    slippage_bps: float
    fee_bps: float
    target_mode: str
    allowed_directions: str
    allowed_asset_classes: list[str]


class PaperTradingService:
    """Database-backed virtual trading service."""

    @staticmethod
    def _default_balance() -> float:
        return _env_float("PAPER_TRADING_START_BALANCE_USD", 10000.0, 50.0, 100_000_000.0)

    @staticmethod
    def _default_auto_enabled() -> bool:
        return _env_bool("PAPER_AUTO_TRADE_DEFAULT_ENABLED", False)

    async def _user_row(
        self,
        session,
        user_id: int,
        *,
        user_identity: str = "telegram",
    ) -> User | None:
        identity = str(user_identity or "telegram").strip().lower()
        criterion = (
            User.id == int(user_id)
            if identity == "platform"
            else User.telegram_user_id == int(user_id)
        )
        return (
            await session.execute(select(User).where(criterion).limit(1))
        ).scalar_one_or_none()

    async def _ensure_account_for_user(self, session, user: User) -> PaperAccount:
        account = (
            await session.execute(
                select(PaperAccount).where(PaperAccount.user_id == int(user.id)).limit(1)
            )
        ).scalar_one_or_none()
        if account is not None:
            return account
        balance = self._default_balance()
        account = PaperAccount(
            user_id=int(user.id),
            starting_balance=balance,
            cash_balance=balance,
            auto_trade_enabled=self._default_auto_enabled(),
            risk_pct=_env_float("PAPER_DEFAULT_RISK_PCT", 1.0, 0.1, 10.0),
            max_open_positions=_env_int("PAPER_DEFAULT_MAX_OPEN_POSITIONS", 5, 1, 100),
            min_signal_score=_env_float("PAPER_DEFAULT_MIN_SIGNAL_SCORE", 0.0, 0.0, 100.0),
            spread_bps=_env_float("PAPER_DEFAULT_SPREAD_BPS", 2.0, 0.0, 500.0),
            slippage_bps=_env_float("PAPER_DEFAULT_SLIPPAGE_BPS", 2.0, 0.0, 500.0),
            fee_bps=_env_float("PAPER_DEFAULT_FEE_BPS", 5.0, 0.0, 500.0),
            target_mode=str(os.getenv("PAPER_DEFAULT_TARGET_MODE") or "TP1").strip().upper(),
            allowed_directions="both",
            allowed_asset_classes=[],
            status="active",
            updated_at=now_utc_naive(),
        )
        session.add(account)
        await session.flush()
        session.add(PaperLedgerEntry(
            account_id=int(account.id),
            user_id=int(user.id),
            entry_type="ACCOUNT_CREATED",
            amount=0.0,
            balance_after=float(balance),
            description="Paper account created",
            meta={"auto_trade_enabled": bool(account.auto_trade_enabled)},
        ))
        return account

    async def ensure_account(
        self,
        user_id: int,
        *,
        session=None,
        user_identity: str = "telegram",
    ) -> PaperAccount | None:
        if session is not None:
            return await self._ensure_account_in_session(
                session,
                int(user_id),
                user_identity=user_identity,
            )
        async with get_session(priority="interactive", label="paper.ensure_account") as owned_session:
            try:
                account = await self._ensure_account_in_session(
                    owned_session,
                    int(user_id),
                    user_identity=user_identity,
                )
                await owned_session.commit()
                return account
            except IntegrityError:
                await owned_session.rollback()
                user = await self._user_row(
                    owned_session,
                    int(user_id),
                    user_identity=user_identity,
                )
                if user is None:
                    return None
                return (
                    await owned_session.execute(
                        select(PaperAccount).where(PaperAccount.user_id == int(user.id)).limit(1)
                    )
                ).scalar_one_or_none()

    async def _ensure_account_in_session(
        self,
        session,
        user_id: int,
        *,
        user_identity: str = "telegram",
    ) -> PaperAccount | None:
        user = await self._user_row(
            session,
            int(user_id),
            user_identity=user_identity,
        )
        if user is None:
            return None
        return await self._ensure_account_for_user(session, user)

    async def snapshot(
        self,
        user_id: int,
        *,
        user_identity: str = "telegram",
    ) -> PaperSnapshot | None:
        identity = str(user_identity or "telegram").strip().lower()
        async with get_session(priority="interactive", label="paper.snapshot") as session:
            user = await self._user_row(
                session,
                int(user_id),
                user_identity=identity,
            )
            if user is None:
                return None
            account = await self.ensure_account(
                int(user_id),
                session=session,
                user_identity=identity,
            )
            if account is None:
                return None
            await session.commit()
            open_rows = (
                await session.execute(
                    select(PaperPosition).where(
                        PaperPosition.user_id == int(account.user_id),
                        PaperPosition.status == "open",
                    )
                )
            ).scalars().all()
            closed_count = int((
                await session.execute(
                    select(func.count(PaperPosition.position_id)).where(
                        PaperPosition.user_id == int(account.user_id),
                        PaperPosition.status == "closed",
                    )
                )
            ).scalar() or 0)
            reserved = sum(_safe_float(row.reserved_cash) for row in open_rows)
            unrealized = sum(_safe_float(row.unrealized_pnl) for row in open_rows)
            equity = _safe_float(account.cash_balance) + reserved + unrealized
            return PaperSnapshot(
                telegram_user_id=(
                    int(user.telegram_user_id)
                    if user.telegram_user_id is not None
                    else None
                ),
                user_id=int(user.id),
                identity=identity,
                starting_balance=_safe_float(account.starting_balance),
                cash_balance=_safe_float(account.cash_balance),
                equity=equity,
                reserved_cash=reserved,
                unrealized_pnl=unrealized,
                realized_pnl=_safe_float(account.realized_pnl),
                open_positions=len(open_rows),
                closed_positions=closed_count,
                auto_trade_enabled=bool(account.auto_trade_enabled),
                risk_pct=_safe_float(account.risk_pct),
                max_open_positions=int(account.max_open_positions or 0),
                min_signal_score=_safe_float(account.min_signal_score),
                spread_bps=_safe_float(account.spread_bps),
                slippage_bps=_safe_float(account.slippage_bps),
                fee_bps=_safe_float(account.fee_bps),
                target_mode=str(account.target_mode or "TP1").upper(),
                allowed_directions=str(account.allowed_directions or "both").lower(),
                allowed_asset_classes=[
                    str(x).lower() for x in (account.allowed_asset_classes or [])
                ],
            )

    async def update_settings(
        self,
        user_id: int,
        *,
        user_identity: str = "telegram",
        **changes: Any,
    ) -> PaperSnapshot | None:
        identity = str(user_identity or "telegram").strip().lower()
        allowed = {
            "auto_trade_enabled", "risk_pct", "max_open_positions", "min_signal_score",
            "spread_bps", "slippage_bps", "fee_bps", "target_mode",
            "allowed_directions", "allowed_asset_classes",
        }
        async with get_session(priority="interactive", label="paper.update_settings") as session:
            user = await self._user_row(
                session,
                int(user_id),
                user_identity=identity,
            )
            if user is None:
                return None
            account = (
                await session.execute(
                    select(PaperAccount)
                    .where(PaperAccount.user_id == int(user.id))
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if account is None:
                account = await self._ensure_account_for_user(session, user)
            changed: dict[str, Any] = {}
            for key, value in changes.items():
                if key not in allowed:
                    continue
                if key == "risk_pct":
                    value = max(0.1, min(10.0, _safe_float(value, 1.0)))
                elif key == "max_open_positions":
                    value = max(1, min(100, int(value)))
                elif key == "min_signal_score":
                    value = max(0.0, min(100.0, _safe_float(value)))
                elif key in {"spread_bps", "slippage_bps", "fee_bps"}:
                    value = max(0.0, min(500.0, _safe_float(value)))
                elif key == "target_mode":
                    value = str(value or "TP1").strip().upper()
                    if value not in {"TP1", "TP2", "TP3"}:
                        raise ValueError("target_mode must be TP1, TP2, or TP3")
                elif key == "allowed_directions":
                    value = str(value or "both").strip().lower()
                    if value not in {"both", "long", "short"}:
                        raise ValueError("allowed_directions must be both, long, or short")
                elif key == "allowed_asset_classes":
                    value = sorted({
                        str(x).strip().lower()
                        for x in (value or [])
                        if str(x).strip()
                    })
                elif key == "auto_trade_enabled":
                    value = bool(value)
                setattr(account, key, value)
                changed[key] = value
            account.updated_at = now_utc_naive()
            session.add(PaperLedgerEntry(
                account_id=int(account.id),
                user_id=int(user.id),
                entry_type="SETTINGS_UPDATED",
                amount=0.0,
                balance_after=_safe_float(account.cash_balance),
                description="Paper settings updated",
                meta={**changed, "identity": identity},
            ))
            await session.commit()
        return await self.snapshot(
            int(user_id),
            user_identity=identity,
        )

    async def reset_account(
        self,
        user_id: int,
        starting_balance: float,
        *,
        user_identity: str = "telegram",
    ) -> PaperSnapshot | None:
        identity = str(user_identity or "telegram").strip().lower()
        balance = max(
            50.0,
            min(
                100_000_000.0,
                _safe_float(starting_balance, self._default_balance()),
            ),
        )
        async with get_session(priority="interactive", label="paper.reset") as session:
            user = await self._user_row(
                session,
                int(user_id),
                user_identity=identity,
            )
            if user is None:
                return None
            account = (
                await session.execute(
                    select(PaperAccount)
                    .where(PaperAccount.user_id == int(user.id))
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if account is None:
                account = await self._ensure_account_for_user(session, user)
            open_count = int((
                await session.execute(
                    select(func.count(PaperPosition.position_id)).where(
                        PaperPosition.user_id == int(user.id),
                        PaperPosition.status == "open",
                    )
                )
            ).scalar() or 0)
            if open_count:
                raise ValueError(
                    "Close or wait for all paper positions before resetting the account"
                )
            await session.execute(
                PaperPosition.__table__.delete().where(
                    PaperPosition.user_id == int(user.id)
                )
            )
            account.starting_balance = balance
            account.cash_balance = balance
            account.realized_pnl = 0.0
            account.updated_at = now_utc_naive()
            session.add(PaperLedgerEntry(
                account_id=int(account.id),
                user_id=int(user.id),
                entry_type="ACCOUNT_RESET",
                amount=0.0,
                balance_after=balance,
                description="Paper account reset",
                meta={"starting_balance": balance, "identity": identity},
            ))
            await session.commit()
        return await self.snapshot(
            int(user_id),
            user_identity=identity,
        )

    async def list_positions(
        self,
        user_id: int,
        *,
        status: str = "open",
        limit: int = 20,
        user_identity: str = "telegram",
    ) -> list[dict[str, Any]]:
        identity = str(user_identity or "telegram").strip().lower()
        async with get_session(priority="interactive", label="paper.list_positions") as session:
            user = await self._user_row(
                session,
                int(user_id),
                user_identity=identity,
            )
            if user is None:
                return []
            query = select(PaperPosition).where(
                PaperPosition.user_id == int(user.id)
            )
            if status:
                query = query.where(
                    PaperPosition.status == str(status).lower()
                )
            rows = (
                await session.execute(
                    query.order_by(PaperPosition.opened_at.desc()).limit(
                        max(1, min(500, int(limit)))
                    )
                )
            ).scalars().all()
            return [self._position_dict(row) for row in rows]

    async def stale_positions(
        self,
        *,
        max_age_hours: float | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Open paper positions older than the policy max-age for their timeframe.

        Orphaned positions must not block new signals forever
        (active-position-blocking remediation): they are reported stale for
        owner review / policy-based closure instead of silently locking assets.
        """
        from datetime import datetime, timedelta, timezone

        async with get_session(priority=_paper_worker_priority(), label="paper.stale_positions", timeout_seconds=_paper_db_timeout(8.0)) as session:
            rows = (
                await session.execute(
                    select(PaperPosition)
                    .where(PaperPosition.status == "open")
                    .order_by(PaperPosition.opened_at.asc())
                    .limit(max(1, min(500, int(limit))))
                )
            ).scalars().all()
        out: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        for row in rows:
            opened_at = getattr(row, "opened_at", None)
            if opened_at is None:
                continue
            opened = opened_at.replace(tzinfo=timezone.utc) if opened_at.tzinfo is None else opened_at
            age_h = (now - opened).total_seconds() / 3600.0
            policy_h = float(max_age_hours) if max_age_hours else position_max_age_hours(getattr(row, "timeframe", None))
            if age_h > policy_h:
                item = self._position_dict(row)
                item["age_hours"] = round(age_h, 2)
                item["max_age_hours"] = policy_h
                item["stale_reason"] = "position_max_age_exceeded"
                out.append(item)
        return out

    @staticmethod
    def _position_dict(row: PaperPosition) -> dict[str, Any]:
        return {
            "position_id": row.position_id,
            "signal_id": row.signal_id,
            "asset": row.asset,
            "asset_class": row.asset_class,
            "timeframe": row.timeframe,
            "direction": row.direction,
            "status": row.status,
            "signal_entry": _safe_float(row.signal_entry),
            "fill_entry": _safe_float(row.fill_entry),
            "current_price": _safe_float(row.current_price),
            "stop_loss": _safe_float(row.stop_loss),
            "take_profits": list(row.take_profits or []),
            "target_price": _safe_float(row.target_price),
            "quantity": _safe_float(row.quantity),
            "notional": _safe_float(row.notional),
            "unrealized_pnl": _safe_float(row.unrealized_pnl),
            "realized_pnl": _safe_float(row.realized_pnl),
            "r_multiple": None if row.r_multiple is None else _safe_float(row.r_multiple),
            "opened_at": row.opened_at,
            "closed_at": row.closed_at,
            "exit_reason": row.exit_reason,
            "meta": dict(row.meta or {}),
        }

    async def performance(
        self,
        user_id: int,
        *,
        user_identity: str = "telegram",
    ) -> dict[str, Any]:
        identity = str(user_identity or "telegram").strip().lower()
        snapshot = await self.snapshot(
            int(user_id),
            user_identity=identity,
        )
        if snapshot is None:
            return {}
        rows = await self.list_positions(
            int(user_id),
            status="closed",
            limit=500,
            user_identity=identity,
        )
        wins = [r for r in rows if _safe_float(r.get("realized_pnl")) > 0]
        losses = [r for r in rows if _safe_float(r.get("realized_pnl")) < 0]
        flat = [
            r for r in rows
            if abs(_safe_float(r.get("realized_pnl"))) < 1e-9
        ]
        net = sum(_safe_float(r.get("realized_pnl")) for r in rows)
        gross_win = sum(_safe_float(r.get("realized_pnl")) for r in wins)
        gross_loss = abs(sum(_safe_float(r.get("realized_pnl")) for r in losses))
        r_values = [
            _safe_float(r.get("r_multiple"))
            for r in rows
            if r.get("r_multiple") is not None
        ]
        return {
            "snapshot": asdict(snapshot),
            "sample_size": len(rows),
            "wins": len(wins),
            "losses": len(losses),
            "flat": len(flat),
            "win_rate_pct": (
                len(wins) / len(rows) * 100.0 if rows else 0.0
            ),
            "net_pnl": net,
            "return_pct": (
                net / snapshot.starting_balance * 100.0
                if snapshot.starting_balance > 0
                else 0.0
            ),
            "profit_factor": (
                gross_win / gross_loss
                if gross_loss > 0
                else (float("inf") if gross_win > 0 else 0.0)
            ),
            "avg_r": (
                sum(r_values) / len(r_values) if r_values else 0.0
            ),
        }

    async def delivered_r_samples(
        self,
        user_id: int,
        *,
        user_identity: str = "telegram",
    ) -> dict[str, Any]:
        """Return terminal R samples from receipts authorized for this identity."""
        identity = str(user_identity or "telegram").strip().lower()
        terminal_statuses = (
            "tp", "tp3", "sl", "invalid", "invalidated", "time_stop",
            "partial_win_be", "missed_entry", "expired",
        )
        partial_statuses = ("tp1", "tp2")
        async with get_session(
            priority="interactive",
            label="paper.simulation_samples",
        ) as session:
            user = await self._user_row(
                session,
                int(user_id),
                user_identity=identity,
            )
            if user is None:
                return {
                    "r_values": [],
                    "first": None,
                    "last": None,
                    "delivered_total": 0,
                    "pending_delivered": 0,
                    "partial_milestones": 0,
                }

            web_union = ""
            if identity == "platform":
                web_union = """
                    UNION
                    SELECT
                        ne.channel_data->>'signal_id' AS signal_id,
                        ne.created_at AS confirmed_at
                    FROM notification_events ne
                    WHERE ne.user_id=:uid
                      AND ne.event_type='signal'
                      AND ne.channel_data->>'channel'='web'
                      AND COALESCE(ne.channel_data->>'signal_id','')<>''
                """
            receipts_cte = f"""
                WITH receipts AS (
                    SELECT DISTINCT
                        sd.signal_id::text AS signal_id,
                        COALESCE(
                            sd.delivery_confirmed_at,
                            sd.delivered_at_utc,
                            sd.delivered_at
                        ) AS confirmed_at
                    FROM signal_deliveries sd
                    WHERE sd.user_id=:uid
                      AND sd.sent_ok IS TRUE
                      AND sd.telegram_chat_id IS NOT NULL
                      AND sd.telegram_message_id IS NOT NULL
                      AND LOWER(COALESCE(sd.delivery_state,'')) IN
                          ('sent','delivered','confirmed','reconciled')
                    {web_union}
                )
            """
            terminal_sql = receipts_cte + """
                SELECT
                    o.signal_id,
                    o.r_multiple,
                    o.closed_at,
                    LOWER(COALESCE(o.status,'')) AS status,
                    r.confirmed_at
                FROM receipts r
                JOIN outcomes o ON o.signal_id=r.signal_id
                WHERE LOWER(COALESCE(o.status,'')) IN
                    ('tp','tp3','sl','invalid','invalidated','time_stop',
                     'partial_win_be','missed_entry','expired')
                  AND o.r_multiple IS NOT NULL
                ORDER BY o.closed_at ASC NULLS LAST
            """
            rows = (
                await session.execute(
                    text(terminal_sql),
                    {"uid": int(user.id)},
                )
            ).all()
            seen: set[str] = set()
            r_values: list[float] = []
            times: list[Any] = []
            for signal_id, r_multiple, closed_at, _status, confirmed_at in rows:
                sid = str(signal_id or "")
                if not sid or sid in seen:
                    continue
                seen.add(sid)
                r_values.append(_safe_float(r_multiple))
                when = closed_at or confirmed_at
                if when is not None:
                    times.append(when)

            delivered_total = int(
                (
                    await session.execute(
                        text(
                            receipts_cte
                            + " SELECT COUNT(DISTINCT signal_id) FROM receipts"
                        ),
                        {"uid": int(user.id)},
                    )
                ).scalar()
                or 0
            )
            partial_milestones = int(
                (
                    await session.execute(
                        text(
                            receipts_cte
                            + """
                            SELECT COUNT(DISTINCT o.signal_id)
                            FROM receipts r
                            JOIN outcomes o ON o.signal_id=r.signal_id
                            WHERE LOWER(COALESCE(o.status,'')) IN ('tp1','tp2')
                            """
                        ),
                        {"uid": int(user.id)},
                    )
                ).scalar()
                or 0
            )
            terminal_count = len(seen)
            return {
                "r_values": r_values,
                "first": min(times) if times else None,
                "last": max(times) if times else None,
                "delivered_total": delivered_total,
                "pending_delivered": max(0, delivered_total - terminal_count),
                "partial_milestones": partial_milestones,
            }

    async def _telegram_delivery_candidates(self, limit: int) -> list[dict[str, Any]]:
        # Fetch a broad window, then enforce the stricter timeframe-specific
        # freshness policy for each candidate. A single 15-minute cutoff caused
        # valid 1d candidates to disappear while older 1h candidates could still
        # be admitted through retries.
        max_age_s = _env_int("PAPER_DISCOVERY_MAX_AGE_SECONDS", 21600, 300, 86400)
        now = now_utc_naive()
        cutoff = now - timedelta(seconds=max_age_s)
        terminal_statuses = tuple(TERMINAL_OUTCOMES - {"tp1", "tp2", "partial_win"})
        async with get_session(
            priority=_paper_worker_priority(),
            label="paper.delivery_candidates",
            timeout_seconds=_paper_db_timeout(8.0),
        ) as session:
            permanent_attempt = select(PaperTradeAttempt.id).where(
                PaperTradeAttempt.user_id == User.id,
                PaperTradeAttempt.signal_id == SignalDelivery.signal_id,
                PaperTradeAttempt.decision == "SKIPPED",
                PaperTradeAttempt.retryable.is_(False),
                PaperTradeAttempt.finalized_at.is_not(None),
            ).exists()
            retry_backoff = select(PaperTradeAttempt.id).where(
                PaperTradeAttempt.user_id == User.id,
                PaperTradeAttempt.signal_id == SignalDelivery.signal_id,
                PaperTradeAttempt.retryable.is_(True),
                PaperTradeAttempt.next_retry_at.is_not(None),
                PaperTradeAttempt.next_retry_at > now,
            ).exists()
            retry_override = select(PaperTradeAttempt.id).where(
                PaperTradeAttempt.user_id == User.id,
                PaperTradeAttempt.signal_id == SignalDelivery.signal_id,
                PaperTradeAttempt.decision == "RETRY_PENDING",
                PaperTradeAttempt.retry_deadline > now,
            ).exists()
            rows = (
                await session.execute(
                    select(
                        SignalDelivery, Signal, User, PaperAccount,
                        PaperPosition.position_id, SignalLifecycle,
                    )
                    .join(Signal, Signal.signal_id == SignalDelivery.signal_id)
                    .join(User, User.id == SignalDelivery.user_id)
                    .outerjoin(PaperAccount, PaperAccount.user_id == User.id)
                    .outerjoin(SignalLifecycle, SignalLifecycle.signal_id == Signal.signal_id)
                    .outerjoin(Outcome, Outcome.signal_id == Signal.signal_id)
                    .outerjoin(
                        PaperPosition,
                        and_(
                            PaperPosition.user_id == User.id,
                            PaperPosition.signal_id == SignalDelivery.signal_id,
                            func.lower(PaperPosition.status).in_(["open", "closed"]),
                        ),
                    )
                    .where(
                        SignalDelivery.sent_ok.is_(True),
                        func.lower(SignalDelivery.delivery_state).in_(tuple(CONFIRMED_DELIVERY_STATES)),
                        SignalDelivery.telegram_chat_id.is_not(None),
                        SignalDelivery.telegram_message_id.is_not(None),
                        SignalDelivery.delivery_confirmed_at.is_not(None),
                        SignalDelivery.delivery_confirmed_at >= cutoff,
                        PaperPosition.position_id.is_(None),
                        or_(Outcome.id.is_(None), ~func.lower(Outcome.status).in_(terminal_statuses)),
                        or_(~permanent_attempt, retry_override),
                        ~retry_backoff,
                    )
                    .order_by(SignalDelivery.delivery_confirmed_at.desc(), SignalDelivery.id.desc())
                    .limit(max(1, min(500, int(limit))))
                )
            ).all()
            out: list[dict[str, Any]] = []
            for delivery, signal, user, account, _, lifecycle in rows:
                out.append({
                    "delivery_id": int(delivery.id),
                    "receipt_channel": "telegram",
                    "receipt_reference": str(delivery.id),
                    "telegram_user_id": (
                        int(user.telegram_user_id)
                        if user.telegram_user_id is not None
                        else None
                    ),
                    "user_id": int(user.id),
                    "signal_id": str(signal.signal_id),
                    "display_id": str(getattr(signal, "display_id", "") or ""),
                    "asset": str(signal.asset),
                    "asset_class": canonical_asset_class(str(signal.asset), signal.asset_class),
                    "timeframe": str(signal.timeframe or ""),
                    "direction": canonical_direction(signal.direction),
                    "entry": _safe_float(signal.entry),
                    "stop_loss": _safe_float(signal.stop_loss),
                    "take_profits": parse_targets(signal.take_profit),
                    "score": _safe_float(signal.score),
                    "generated_at": delivery.generated_at_utc or signal.created_at,
                    "signal_age_at_delivery_seconds": delivery.signal_age_at_delivery_seconds,
                    "thesis_fingerprint": getattr(signal, "thesis_fingerprint", None) or signal_thesis_fingerprint({
                        "asset": signal.asset,
                        "direction": signal.direction,
                        "strategy_name": signal.strategy_name,
                        "regime": signal.regime,
                        "entry": signal.entry,
                        "timeframe": signal.timeframe,
                    }),
                    "confirmed_at": delivery.delivery_confirmed_at,
                    "retry_deadline": (delivery.generated_at_utc or signal.created_at) + timedelta(
                        seconds=evaluate_signal_freshness(
                            timeframe=signal.timeframe,
                            generated_at=delivery.generated_at_utc or signal.created_at,
                            now=now,
                            purpose="paper",
                        ).max_age_seconds
                    ),
                    "account_exists": account is not None,
                    "lifecycle_state": str(getattr(lifecycle, "state", "") or ""),
                    "entry_touched_at": getattr(lifecycle, "entry_touched_at", None),
                })
            return out
    async def _web_delivery_candidates(self, limit: int) -> list[dict[str, Any]]:
        """Discover gated web receipts without manufacturing Telegram deliveries."""
        max_age_s = _env_int(
            "PAPER_DISCOVERY_MAX_AGE_SECONDS",
            21600,
            300,
            86400,
        )
        now = now_utc_naive()
        cutoff = now - timedelta(seconds=max_age_s)
        terminal_statuses = (
            "tp", "tp3", "sl", "stop", "stopped", "expired", "missed",
            "cancelled", "closed", "win", "loss", "partial_win",
            "invalid", "invalidated", "time_stop", "partial_win_be",
            "missed_entry",
        )
        status_sql = ",".join(f"'{item}'" for item in terminal_statuses)
        sql = f"""
            SELECT
                ne.notification_id,
                ne.user_id,
                ne.created_at AS confirmed_at,
                u.telegram_user_id,
                s.signal_id,
                s.display_id,
                s.asset,
                s.asset_class,
                s.timeframe,
                s.direction,
                s.entry,
                s.stop_loss,
                s.take_profit,
                s.score,
                s.created_at AS generated_at,
                s.thesis_fingerprint,
                s.strategy_name,
                s.regime,
                pa.id AS account_id,
                sl.state AS lifecycle_state,
                sl.entry_touched_at
            FROM notification_events ne
            JOIN users u ON u.id=ne.user_id
            JOIN signals s
              ON s.signal_id=ne.channel_data->>'signal_id'
            LEFT JOIN paper_accounts pa ON pa.user_id=u.id
            LEFT JOIN signal_lifecycles sl ON sl.signal_id=s.signal_id
            LEFT JOIN outcomes o ON o.signal_id=s.signal_id
            LEFT JOIN paper_positions pp
              ON pp.user_id=u.id
             AND pp.signal_id=s.signal_id
             AND LOWER(pp.status) IN ('open','closed')
            WHERE ne.event_type='signal'
              AND ne.channel_data->>'channel'='web'
              AND ne.created_at >= :cutoff
              AND COALESCE(u.is_blocked,FALSE) IS FALSE
              AND COALESCE(u.is_suspended,FALSE) IS FALSE
              AND pp.position_id IS NULL
              AND (o.id IS NULL OR LOWER(COALESCE(o.status,'')) NOT IN ({status_sql}))
              AND NOT EXISTS (
                    SELECT 1
                    FROM paper_trade_attempts pta
                    WHERE pta.user_id=u.id
                      AND pta.signal_id=s.signal_id
                      AND pta.decision='SKIPPED'
                      AND pta.retryable IS FALSE
                      AND pta.finalized_at IS NOT NULL
                      AND NOT EXISTS (
                            SELECT 1
                            FROM paper_trade_attempts override_attempt
                            WHERE override_attempt.user_id=u.id
                              AND override_attempt.signal_id=s.signal_id
                              AND override_attempt.decision='RETRY_PENDING'
                              AND override_attempt.retry_deadline > :now
                      )
              )
              AND NOT EXISTS (
                    SELECT 1
                    FROM paper_trade_attempts backoff
                    WHERE backoff.user_id=u.id
                      AND backoff.signal_id=s.signal_id
                      AND backoff.retryable IS TRUE
                      AND backoff.next_retry_at IS NOT NULL
                      AND backoff.next_retry_at > :now
              )
            ORDER BY ne.created_at DESC, ne.notification_id DESC
            LIMIT :limit
        """
        async with get_session(
            priority=_paper_worker_priority(),
            label="paper.web_delivery_candidates",
            timeout_seconds=_paper_db_timeout(8.0),
        ) as session:
            rows = (
                await session.execute(
                    text(sql),
                    {
                        "cutoff": cutoff,
                        "now": now,
                        "limit": max(1, min(500, int(limit))),
                    },
                )
            ).mappings().all()
            await session.rollback()

        out: list[dict[str, Any]] = []
        for row in rows:
            generated_at = row.get("generated_at")
            freshness = evaluate_signal_freshness(
                timeframe=row.get("timeframe"),
                generated_at=generated_at,
                now=now,
                purpose="paper",
            )
            confirmed_at = row.get("confirmed_at")
            age_seconds = None
            try:
                if confirmed_at is not None and generated_at is not None:
                    age_seconds = max(
                        0,
                        int((confirmed_at - generated_at).total_seconds()),
                    )
            except Exception:
                age_seconds = None
            out.append(
                {
                    "delivery_id": None,
                    "receipt_channel": "web",
                    "receipt_reference": str(row["notification_id"]),
                    "telegram_user_id": (
                        int(row["telegram_user_id"])
                        if row.get("telegram_user_id") is not None
                        else None
                    ),
                    "user_id": int(row["user_id"]),
                    "signal_id": str(row["signal_id"]),
                    "display_id": str(row.get("display_id") or ""),
                    "asset": str(row["asset"]),
                    "asset_class": canonical_asset_class(
                        str(row["asset"]),
                        row.get("asset_class"),
                    ),
                    "timeframe": str(row.get("timeframe") or ""),
                    "direction": canonical_direction(row.get("direction")),
                    "entry": _safe_float(row.get("entry")),
                    "stop_loss": _safe_float(row.get("stop_loss")),
                    "take_profits": parse_targets(row.get("take_profit")),
                    "score": _safe_float(row.get("score")),
                    "generated_at": generated_at,
                    "signal_age_at_delivery_seconds": age_seconds,
                    "thesis_fingerprint": (
                        row.get("thesis_fingerprint")
                        or signal_thesis_fingerprint(
                            {
                                "asset": row.get("asset"),
                                "direction": row.get("direction"),
                                "strategy_name": row.get("strategy_name"),
                                "regime": row.get("regime"),
                                "entry": row.get("entry"),
                                "timeframe": row.get("timeframe"),
                            }
                        )
                    ),
                    "confirmed_at": confirmed_at,
                    "retry_deadline": (
                        generated_at + timedelta(seconds=freshness.max_age_seconds)
                        if generated_at is not None
                        else confirmed_at
                    ),
                    "account_exists": row.get("account_id") is not None,
                    "lifecycle_state": str(
                        row.get("lifecycle_state") or ""
                    ),
                    "entry_touched_at": row.get("entry_touched_at"),
                }
            )
        return out

    async def _delivery_candidates(self, limit: int) -> list[dict[str, Any]]:
        """Merge Telegram proof and gated web receipts by canonical user/signal."""
        batch = max(1, min(500, int(limit)))
        telegram_rows, web_rows = await asyncio.gather(
            self._telegram_delivery_candidates(batch),
            self._web_delivery_candidates(batch),
        )
        merged: dict[tuple[int, str], dict[str, Any]] = {}
        # Web goes first; Telegram overwrites it when both exist because it has
        # an addressable delivery row and therefore richer historical evidence.
        for candidate in [*web_rows, *telegram_rows]:
            key = (
                int(candidate["user_id"]),
                str(candidate["signal_id"]),
            )
            merged[key] = candidate
        ordered = sorted(
            merged.values(),
            key=lambda row: row.get("confirmed_at") or now_utc_naive(),
            reverse=True,
        )
        return ordered[:batch]

    async def process_new_deliveries(self, *, limit: int = 100) -> dict[str, int]:
        candidates = await self._delivery_candidates(limit)
        if not candidates:
            return {"candidates": 0, "opened": 0, "skipped": 0, "failed": 0}
        assets = sorted({c["asset"] for c in candidates if c.get("asset")})
        prices: dict[str, Optional[float]] = {}
        try:
            from engine.price_fetcher import get_live_price_batch
            prices = await get_live_price_batch(assets, max_concurrent=_env_int("PAPER_PRICE_CONCURRENCY", 4, 1, 20))
        except Exception as exc:
            logger.warning("[paper] live price batch failed; new paper entries will be deferred: %s", exc)
        result = {"candidates": len(candidates), "opened": 0, "skipped": 0, "deferred": 0, "failed": 0}
        for candidate in candidates:
            try:
                status = await self._open_candidate(candidate, prices.get(candidate["asset"]))
                if status not in {"opened", "skipped", "deferred"}:
                    status = "failed"
                result[status] += 1
            except Exception:
                result["failed"] += 1
                logger.exception("[paper] candidate processing failed delivery=%s", candidate.get("delivery_id"))
        return result

    async def _record_attempt(
        self,
        session,
        *,
        account: PaperAccount,
        user: User,
        candidate: dict[str, Any],
        decision: str,
        reason: str,
        retryable: bool,
        market_price: float | None = None,
        sizing: Any = None,
        finalized: bool = False,
        next_retry_seconds: int | None = None,
        meta: dict[str, Any] | None = None,
    ) -> PaperTradeAttempt:
        now = now_utc_naive()
        previous_attempt = (
            await session.execute(
                select(PaperTradeAttempt).where(
                    PaperTradeAttempt.user_id == int(user.id),
                    PaperTradeAttempt.signal_id == str(candidate["signal_id"]),
                ).order_by(PaperTradeAttempt.attempt_number.desc()).limit(1)
            )
        ).scalar_one_or_none()
        attempt_number = int(getattr(previous_attempt, "attempt_number", 0) or 0) + 1
        first_attempt_at = getattr(previous_attempt, "first_attempt_at", None) or now
        retry_deadline = candidate.get("retry_deadline")
        retry_delay = int(next_retry_seconds if next_retry_seconds is not None else os.getenv("PAPER_ENTRY_RETRY_SECONDS", "15"))
        next_retry_at = now + timedelta(seconds=max(1, retry_delay)) if retryable else None
        if retry_deadline is not None and next_retry_at is not None and next_retry_at >= retry_deadline:
            retryable = False
            next_retry_at = None
            decision = "SKIPPED"
            reason = "paper_entry_retry_deadline_expired"
            finalized = True
        delivery_id = candidate.get("delivery_id")
        receipt_channel = str(
            candidate.get("receipt_channel")
            or ("telegram" if delivery_id is not None else "web")
        ).strip().lower()
        receipt_reference = str(
            candidate.get("receipt_reference")
            or (delivery_id if delivery_id is not None else candidate.get("signal_id"))
            or ""
        ).strip()
        attempt = PaperTradeAttempt(
            attempt_id=str(uuid4()),
            account_id=int(account.id),
            user_id=int(user.id),
            signal_id=str(candidate["signal_id"]),
            delivery_id=(
                int(delivery_id)
                if delivery_id is not None
                else None
            ),
            receipt_channel=receipt_channel,
            receipt_reference=receipt_reference[:64] or None,
            idempotency_key=(
                f"paper:{receipt_channel}:{receipt_reference}:"
                f"{attempt_number}:{decision.lower()}"
            )[:128],
            decision=str(decision).upper(),
            reason=str(reason)[:128],
            retryable=bool(retryable),
            attempt_number=attempt_number,
            market_price=_safe_float(market_price) if market_price is not None else None,
            available_cash=_safe_float(account.cash_balance),
            risk_amount=float(getattr(sizing, "risk_amount", 0) or 0) if sizing is not None else None,
            calculated_quantity=float(getattr(sizing, "quantity", 0) or 0) if sizing is not None else None,
            calculated_notional=float(getattr(sizing, "notional", 0) or 0) if sizing is not None else None,
            calculated_fee=float(getattr(sizing, "entry_fee", 0) or 0) if sizing is not None else None,
            required_cash=float(getattr(sizing, "total_required", 0) or 0) if sizing is not None else None,
            sizing_policy_version=str(getattr(sizing, "policy_version", "paper-fee-reserve-v2")),
            first_attempt_at=first_attempt_at,
            last_attempt_at=now,
            next_retry_at=next_retry_at,
            retry_deadline=retry_deadline,
            finalized_at=now if finalized else None,
            meta=dict(meta or {}),
            created_at=now,
            updated_at=now,
        )
        session.add(attempt)
        session.add(PaperLedgerEntry(
            account_id=int(account.id),
            user_id=int(user.id),
            entry_type=f"PAPER_{str(decision).upper()}",
            amount=0.0,
            balance_after=_safe_float(account.cash_balance),
            description=f"Paper candidate {str(decision).lower()}: {reason}",
            meta={
                "attempt_id": attempt.attempt_id,
                "signal_id": candidate.get("signal_id"),
                "delivery_id": candidate.get("delivery_id"),
                "receipt_channel": receipt_channel,
                "receipt_reference": receipt_reference,
                "reason": reason,
                "retryable": bool(retryable),
            },
        ))
        await session.flush()
        return attempt

    async def _notify_paper_decision(
        self,
        *,
        telegram_user_id: int | None,
        candidate: dict[str, Any],
        decision: str,
        reason: str,
        fill: float | None = None,
        sizing: Any = None,
        risk_pct: float | None = None,
        stop: float | None = None,
        target: float | None = None,
        remaining_cash: float | None = None,
        position_id: str | None = None,
        attempt_id: str | None = None,
        execution_evidence: dict[str, Any] | None = None,
    ) -> None:
        if decision == "DEFERRED":
            return
        actionable_reasons = {
            "score_below_paper_minimum", "direction_not_allowed",
            "asset_class_not_allowed", "max_open_positions",
            "incomplete_signal_levels", "paper_entry_no_longer_valid",
            "paper_entry_retry_deadline_expired", "auto_trade_disabled",
            "signal_stale", "generated_at_missing", "duplicate_open_asset",
            "max_open_positions_asset_class", "max_total_exposure",
            "max_open_risk", "paper_daily_loss_limit",
            "entry_deviation_too_large", "uncalibrated_signal",
            "profile_preference_mismatch",
            "profile_trading_mode_excludes_paper",
            "profile_daily_trade_limit", "profile_unavailable",
        }
        if decision != "OPENED" and reason not in actionable_reasons:
            return

        signal_ref = str(
            candidate.get("display_id")
            or candidate.get("signal_id")
            or ""
        )
        if decision == "OPENED":
            try:
                from core.paper_sizing import paper_risk_report_text

                risk_report = (
                    paper_risk_report_text(sizing)
                    if sizing is not None
                    else (
                        f"Requested risk budget: {float(risk_pct or 0):.2f}%\n"
                        "Actual stop risk: unavailable\n"
                        "Position-size cap: unknown"
                    )
                )
            except Exception:
                risk_report = (
                    f"Requested risk budget: {float(risk_pct or 0):.2f}%\n"
                    "Actual stop risk: unavailable\n"
                    "Position-size cap: unknown"
                )
            message_text = (
                "📄 Paper Trade Opened\n\n"
                f"Asset: {candidate.get('asset')}\n"
                f"Direction: {str(candidate.get('direction') or '').upper()}\n"
                f"📌 Signal ID: {signal_ref}\n\n"
                f"Virtual fill: {float(fill or 0):.8g}\n"
                f"Virtual size: {float(getattr(sizing, 'quantity', 0) or 0):.8g}\n"
                f"{risk_report}\n"
                f"Stop Loss: {float(stop or 0):.8g}\n"
                f"Selected target: {float(target or 0):.8g}\n"
                f"Entry fee: ${float(getattr(sizing, 'entry_fee', 0) or 0):.4f}\n"
                f"Remaining virtual cash: ${float(remaining_cash or 0):,.2f}\n\n"
                "Execution evidence:\n"
                f"- Paper position: {position_id}\n"
                f"- Receipt: {candidate.get('receipt_channel') or 'telegram'}:"
                f"{candidate.get('receipt_reference') or candidate.get('delivery_id')}\n"
                f"- Attempt: {attempt_id}\n"
                f"- Canonical position count: "
                f"{int((execution_evidence or {}).get('position_count') or 0)}\n"
                "- Auto-management: ACTIVE for this confirmed paper position\n\n"
                "This uses virtual funds only."
            )
        else:
            message_text = (
                "⚠️ Paper Trade Not Opened\n\n"
                f"Asset: {candidate.get('asset')}\n"
                f"📌 Signal ID: {signal_ref}\n\n"
                f"Reason: {reason.replace('_', ' ')}\n\n"
                "Review your paper settings and signal status."
            )

        canonical_user_id = int(candidate.get("user_id") or 0)
        if canonical_user_id > 0:
            try:
                event_key = (
                    attempt_id
                    or position_id
                    or str(candidate.get("receipt_reference") or reason)
                )
                notification_id = str(
                    uuid5(
                        NAMESPACE_URL,
                        f"signalrank:web-paper:{canonical_user_id}:"
                        f"{candidate.get('signal_id')}:{decision}:{event_key}",
                    )
                )
                async with get_session(
                    priority="interactive",
                    label="paper.web_notification",
                    timeout_seconds=_paper_db_timeout(6.0),
                ) as session:
                    allowed = (
                        await session.execute(
                            text(
                                """
                                SELECT 1
                                FROM users u
                                LEFT JOIN notification_preferences np
                                  ON np.user_id=u.id
                                WHERE u.id=:uid
                                  AND COALESCE(u.is_blocked,FALSE) IS FALSE
                                  AND COALESCE(u.is_suspended,FALSE) IS FALSE
                                  AND COALESCE(np.web_enabled,TRUE) IS TRUE
                                LIMIT 1
                                """
                            ),
                            {"uid": canonical_user_id},
                        )
                    ).scalar_one_or_none()
                    if allowed is not None:
                        await session.execute(
                            text(
                                """
                                INSERT INTO notification_events(
                                    notification_id,user_id,event_type,title,body,
                                    severity,channel_data,created_at
                                )
                                VALUES(
                                    :nid,:uid,'paper_trade',:title,:body,:severity,
                                    CAST(:channel_data AS JSONB),NOW()
                                )
                                ON CONFLICT(notification_id) DO NOTHING
                                """
                            ),
                            {
                                "nid": notification_id,
                                "uid": canonical_user_id,
                                "title": (
                                    f"Paper trade {decision.lower()}: "
                                    f"{candidate.get('asset')}"
                                )[:200],
                                "body": message_text,
                                "severity": (
                                    "info" if decision == "OPENED" else "warning"
                                ),
                                "channel_data": json.dumps(
                                    {
                                        "channel": "web",
                                        "surface": "paper_trading",
                                        "signal_id": candidate.get("signal_id"),
                                        "decision": decision,
                                        "reason": reason,
                                        "position_id": position_id,
                                        "attempt_id": attempt_id,
                                        "receipt_channel": candidate.get(
                                            "receipt_channel"
                                        ),
                                        "receipt_reference": candidate.get(
                                            "receipt_reference"
                                        ),
                                    },
                                    separators=(",", ":"),
                                    default=str,
                                ),
                            },
                        )
                        await session.commit()
            except Exception as exc:
                logger.warning(
                    "[paper_web_notification_failed] user=%s signal=%s "
                    "decision=%s error=%s",
                    canonical_user_id,
                    candidate.get("signal_id"),
                    decision,
                    type(exc).__name__,
                    exc_info=True,
                )

        if telegram_user_id is None:
            return
        try:
            from config import config
            from telegram import Bot

            token = str(config.TELEGRAM_BOT_TOKEN or "").strip()
            if not token:
                return
            async with Bot(token=token) as bot:
                await bot.send_message(
                    chat_id=int(telegram_user_id),
                    text=message_text,
                )
        except Exception as exc:
            logger.warning(
                "[paper_notification_failed] user=%s signal=%s decision=%s error=%s",
                telegram_user_id,
                candidate.get("signal_id"),
                decision,
                type(exc).__name__,
            )

    async def _open_candidate(self, candidate: dict[str, Any], market_price: float | None) -> str:
        from core.execution_claims import execution_destination_lock

        telegram_id = candidate.get("telegram_user_id")
        lock_user_id = (
            int(telegram_id)
            if telegram_id is not None
            else -(1_000_000_000_000 + int(candidate["user_id"]))
        )
        async with execution_destination_lock(
            lock_user_id,
            str(candidate["signal_id"]),
        ) as claimed:
            if not claimed:
                logger.warning(
                    "[paper_candidate] execution destination lock unavailable user=%s signal=%s",
                    candidate.get("telegram_user_id"), candidate.get("signal_id"),
                )
                return "deferred"
            return await self._open_candidate_locked(candidate, market_price)

    async def _open_candidate_locked(self, candidate: dict[str, Any], market_price: float | None) -> str:
        notify: dict[str, Any] | None = None
        result_status = "failed"
        async with get_session(
            priority=_paper_worker_priority(), label="paper.open_candidate", timeout_seconds=_paper_db_timeout(10.0)
        ) as session:
            user = (
                await session.execute(select(User).where(User.id == int(candidate["user_id"])).limit(1))
            ).scalar_one_or_none()
            if user is None:
                return "skipped"
            account = (
                await session.execute(
                    select(PaperAccount).where(PaperAccount.user_id == int(user.id)).with_for_update()
                )
            ).scalar_one_or_none()
            if account is None:
                account = await self._ensure_account_for_user(session, user)
            if account is None:
                return "skipped"
            execution_mode = str(getattr(user, "execution_mode", "manual") or "manual").strip().lower()
            if execution_mode in {"auto", "copy", "copy_trade", "live"}:
                logger.info(
                    "[paper_candidate] skipped broker execution mode user=%s signal=%s mode=%s",
                    user.telegram_user_id, candidate.get("signal_id"), execution_mode,
                )
                return "skipped"
            if account.status != "active" or not bool(account.auto_trade_enabled):
                await self._record_attempt(
                    session, account=account, user=user, candidate=candidate,
                    decision="SKIPPED", reason="auto_trade_disabled", retryable=False, finalized=True,
                )
                await session.commit()
                notify = {"decision": "SKIPPED", "reason": "auto_trade_disabled"}
                result_status = "skipped"
            else:
                existing = (
                    await session.execute(
                        select(PaperPosition.position_id).where(
                            PaperPosition.user_id == int(user.id),
                            PaperPosition.signal_id == str(candidate["signal_id"]),
                            func.lower(PaperPosition.status).in_(["open", "closed"]),
                        ).limit(1)
                    )
                ).scalar_one_or_none()
                if existing:
                    return "skipped"
                from services.execution_evidence import (
                    get_platform_execution_evidence,
                )

                evidence_before = await get_platform_execution_evidence(
                    session,
                    user_id=int(user.id),
                    signal_id=str(candidate["signal_id"]),
                )
                if (
                    not evidence_before.get("access_proven")
                    or evidence_before.get("position_count")
                ):
                    logger.warning(
                        "[paper_candidate] blocked by canonical evidence "
                        "user=%s signal=%s evidence=%s",
                        user.id,
                        candidate.get("signal_id"),
                        evidence_before,
                    )
                    return "skipped"
                try:
                    from services.user_intelligence import (
                        get_platform_user_trading_preferences,
                        signal_matches_preferences,
                    )
                    profile_prefs = await get_platform_user_trading_preferences(
                        session,
                        int(user.id),
                    )
                except Exception as profile_error:
                    logger.warning(
                        "[paper_candidate] profile load failed user=%s signal=%s error=%s",
                        user.telegram_user_id,
                        candidate.get("signal_id"),
                        type(profile_error).__name__,
                    )
                    profile_prefs = None

                open_rows = (await session.execute(
                    select(PaperPosition).where(
                        PaperPosition.user_id == int(user.id),
                        func.lower(PaperPosition.status) == "open",
                    ).with_for_update()
                )).scalars().all()
                open_count = len(open_rows)
                skip_reason = ""
                profile_reason = ""
                require_profile = str(os.getenv("PAPER_REQUIRE_USER_PROFILE", "1")).strip().lower() in {
                    "1", "true", "yes", "on",
                }
                if profile_prefs is None and require_profile:
                    skip_reason = "profile_unavailable"
                elif profile_prefs is not None:
                    trading_mode = str(getattr(profile_prefs, "trading_mode", "paper") or "paper").lower()
                    if trading_mode not in {"paper", "both"}:
                        skip_reason = "profile_trading_mode_excludes_paper"
                    else:
                        pref_ok, profile_reason = signal_matches_preferences(candidate, profile_prefs)
                        if not pref_ok:
                            skip_reason = "profile_preference_mismatch"
                freshness = evaluate_signal_freshness(
                    timeframe=candidate.get("timeframe"),
                    generated_at=candidate.get("generated_at"),
                    now=now_utc_naive(),
                    purpose="paper",
                )
                if not freshness.ok:
                    skip_reason = freshness.reason
                effective_max_positions = int(account.max_open_positions or 0)
                if profile_prefs is not None:
                    effective_max_positions = min(
                        effective_max_positions,
                        max(1, int(getattr(profile_prefs, "max_concurrent_positions", effective_max_positions) or effective_max_positions)),
                    )
                if open_count >= effective_max_positions:
                    skip_reason = skip_reason or "max_open_positions"
                day_start = now_utc_naive().replace(hour=0, minute=0, second=0, microsecond=0)
                if profile_prefs is not None:
                    opened_today = int((await session.execute(
                        select(func.count(PaperPosition.position_id)).where(
                            PaperPosition.user_id == int(user.id),
                            PaperPosition.opened_at >= day_start,
                        )
                    )).scalar_one() or 0)
                    if opened_today >= max(0, int(getattr(profile_prefs, "max_daily_trades", 0) or 0)) > 0:
                        skip_reason = skip_reason or "profile_daily_trade_limit"
                realized_today = float((await session.execute(
                    select(func.coalesce(func.sum(PaperPosition.realized_pnl), 0.0)).where(
                        PaperPosition.user_id == int(user.id),
                        func.lower(PaperPosition.status) == "closed",
                        PaperPosition.closed_at >= day_start,
                    )
                )).scalar_one() or 0.0)
                configured_daily_loss_pct = _env_float(
                    "PAPER_MAX_DAILY_LOSS_PCT", 5.0, 0.1, 100.0
                )
                profile_daily_loss_pct = (
                    max(
                        0.1,
                        _safe_float(getattr(profile_prefs, "max_daily_loss_pct", configured_daily_loss_pct)),
                    )
                    if profile_prefs is not None
                    else configured_daily_loss_pct
                )
                effective_daily_loss_pct = min(configured_daily_loss_pct, profile_daily_loss_pct)
                daily_loss_limit = _safe_float(account.starting_balance) * effective_daily_loss_pct / 100.0
                if realized_today <= -daily_loss_limit:
                    skip_reason = skip_reason or "paper_daily_loss_limit"
                if _safe_float(candidate.get("score")) < _safe_float(account.min_signal_score):
                    skip_reason = skip_reason or "score_below_paper_minimum"
                direction = canonical_direction(candidate.get("direction"))
                allowed_direction = str(account.allowed_directions or "both").lower()
                if allowed_direction not in {"both", direction}:
                    skip_reason = skip_reason or "direction_not_allowed"
                asset_class = canonical_asset_class(candidate.get("asset"), candidate.get("asset_class"))
                asset = str(candidate.get("asset") or "").upper().strip()
                if any(str(row.asset or "").upper().strip() == asset for row in open_rows):
                    skip_reason = skip_reason or "duplicate_open_asset"
                max_per_class = _env_int("PAPER_MAX_OPEN_POSITIONS_PER_ASSET_CLASS", 2, 1, 20)
                class_open_count = sum(
                    1 for row in open_rows
                    if canonical_asset_class(str(row.asset or ""), row.asset_class) == asset_class
                )
                if class_open_count >= max_per_class:
                    skip_reason = skip_reason or "max_open_positions_asset_class"
                allowed_classes = {str(x).lower() for x in (account.allowed_asset_classes or [])}
                if allowed_classes and asset_class not in allowed_classes:
                    skip_reason = skip_reason or "asset_class_not_allowed"
                entry = _safe_float(candidate.get("entry"))
                stop = _safe_float(candidate.get("stop_loss"))
                targets = parse_targets(candidate.get("take_profits"))
                if entry <= 0 or stop <= 0 or not targets:
                    skip_reason = skip_reason or "incomplete_signal_levels"
                if skip_reason:
                    await self._record_attempt(
                        session, account=account, user=user, candidate=candidate,
                        decision="SKIPPED", reason=skip_reason, retryable=False,
                        market_price=market_price, finalized=True,
                        meta={"profile_reason": profile_reason} if profile_reason else None,
                    )
                    await session.commit()
                    notify = {"decision": "SKIPPED", "reason": skip_reason}
                    result_status = "skipped"
                else:
                    lifecycle_state = str(candidate.get("lifecycle_state") or "").strip().lower()
                    if lifecycle_state == "watching_for_entry" and candidate.get("entry_touched_at") is None:
                        await self._record_attempt(
                            session, account=account, user=user, candidate=candidate,
                            decision="DEFERRED", reason="watching_for_entry", retryable=True,
                            market_price=market_price,
                        )
                        await session.commit()
                        result_status = "deferred"
                    else:
                        live = _safe_float(market_price)
                        if live <= 0:
                            await self._record_attempt(
                                session, account=account, user=user, candidate=candidate,
                                decision="DEFERRED", reason="live_price_unavailable", retryable=True,
                            )
                            await session.commit()
                            result_status = "deferred"
                        else:
                            entry_deviation_bps = abs(live - entry) / max(entry, 1e-12) * 10000.0
                            max_entry_deviation_bps = _env_float(
                                "PAPER_MAX_ENTRY_DEVIATION_BPS", 25.0, 1.0, 500.0
                            )
                            if entry_deviation_bps > max_entry_deviation_bps:
                                await self._record_attempt(
                                    session, account=account, user=user, candidate=candidate,
                                    decision="SKIPPED", reason="entry_deviation_too_large",
                                    retryable=False, market_price=market_price, finalized=True,
                                    meta={"entry_deviation_bps": entry_deviation_bps,
                                          "maximum_bps": max_entry_deviation_bps},
                                )
                                await session.commit()
                                notify = {"decision": "SKIPPED", "reason": "entry_deviation_too_large"}
                                result_status = "skipped"
                                live = 0.0
                            if live <= 0:
                                pass
                            else:
                                bps = (_safe_float(account.spread_bps) + _safe_float(account.slippage_bps)) / 10000.0
                                fill = live * (1.0 + bps if direction == "long" else 1.0 - bps)
                                risk_per_unit = abs(fill - stop)
                                target_idx = {"TP1": 0, "TP2": 1, "TP3": 2}.get(str(account.target_mode or "TP1").upper(), 0)
                                target = targets[min(target_idx, len(targets) - 1)]
                                valid_geometry = (stop < fill < target) if direction == "long" else (target < fill < stop)
                            if live > 0 and (risk_per_unit <= 0 or not valid_geometry):
                                reason = "invalid_risk_distance" if risk_per_unit <= 0 else "paper_entry_no_longer_valid"
                                await self._record_attempt(
                                    session, account=account, user=user, candidate=candidate,
                                    decision="SKIPPED", reason=reason, retryable=False,
                                    market_price=market_price, finalized=True,
                                )
                                await session.commit()
                                notify = {"decision": "SKIPPED", "reason": reason}
                                result_status = "skipped"
                            elif live > 0:
                                from core.paper_sizing import calculate_paper_position_size

                                cash = _safe_float(account.cash_balance)
                                max_notional_pct = _env_float("PAPER_MAX_NOTIONAL_PCT", 20.0, 1.0, 50.0)
                                try:
                                    effective_risk_pct = _safe_float(account.risk_pct)
                                    if profile_prefs is not None:
                                        effective_risk_pct = min(
                                            effective_risk_pct,
                                            max(0.01, _safe_float(getattr(profile_prefs, "risk_per_trade_pct", effective_risk_pct))),
                                        )
                                    sizing = calculate_paper_position_size(
                                        cash=cash,
                                        risk_pct=effective_risk_pct,
                                        risk_per_unit=risk_per_unit,
                                        fill=fill,
                                        max_notional_pct=max_notional_pct,
                                        fee_bps=account.fee_bps,
                                        tolerance=os.getenv("PAPER_CASH_TOLERANCE", "0.00000001"),
                                    )
                                except ValueError as exc:
                                    reason = str(exc)
                                    await self._record_attempt(
                                        session, account=account, user=user, candidate=candidate,
                                        decision="SKIPPED", reason=reason, retryable=False,
                                        market_price=market_price, finalized=True,
                                    )
                                    await session.commit()
                                    notify = {"decision": "SKIPPED", "reason": reason}
                                    result_status = "skipped"
                                else:
                                    quantity = float(sizing.quantity)
                                    notional = float(sizing.notional)
                                    entry_fee = float(sizing.entry_fee)
                                    starting_balance = max(_safe_float(account.starting_balance), 1e-9)
                                    existing_exposure = sum(_safe_float(row.notional) for row in open_rows)
                                    max_total_exposure_pct = _env_float(
                                        "PAPER_MAX_TOTAL_EXPOSURE_PCT", 80.0, 5.0, 100.0
                                    )
                                    projected_exposure_pct = (
                                        (existing_exposure + notional) / starting_balance * 100.0
                                    )
                                    if projected_exposure_pct > max_total_exposure_pct:
                                        await self._record_attempt(
                                            session, account=account, user=user, candidate=candidate,
                                            decision="SKIPPED", reason="max_total_exposure",
                                            retryable=False, market_price=market_price,
                                            sizing=sizing, finalized=True,
                                            meta={"projected_exposure_pct": projected_exposure_pct,
                                                  "maximum_pct": max_total_exposure_pct},
                                        )
                                        await session.commit()
                                        notify = {"decision": "SKIPPED", "reason": "max_total_exposure"}
                                        result_status = "skipped"
                                        quantity = 0.0
                                    existing_open_risk = sum(
                                        abs(_safe_float(row.fill_entry) - _safe_float(row.stop_loss))
                                        * _safe_float(row.quantity)
                                        for row in open_rows
                                    )
                                    projected_open_risk_pct = (
                                        (existing_open_risk + (risk_per_unit * quantity))
                                        / starting_balance
                                        * 100.0
                                    )
                                    max_open_risk_pct = _env_float(
                                        "PAPER_MAX_OPEN_RISK_PCT", 3.0, 0.1, 25.0
                                    )
                                    if quantity > 0 and projected_open_risk_pct > max_open_risk_pct:
                                        await self._record_attempt(
                                            session, account=account, user=user, candidate=candidate,
                                            decision="SKIPPED", reason="max_open_risk",
                                            retryable=False, market_price=market_price,
                                            sizing=sizing, finalized=True,
                                            meta={"projected_open_risk_pct": projected_open_risk_pct,
                                                  "maximum_pct": max_open_risk_pct},
                                        )
                                        await session.commit()
                                        notify = {"decision": "SKIPPED", "reason": "max_open_risk"}
                                        result_status = "skipped"
                                        quantity = 0.0
                                    if quantity > 0:
                                        position = PaperPosition(
                                            position_id=str(uuid4()), account_id=int(account.id), user_id=int(user.id),
                                            signal_id=str(candidate["signal_id"]),
                                            delivery_id=(
                                                int(candidate["delivery_id"])
                                                if candidate.get("delivery_id") is not None
                                                else None
                                            ),
                                            asset=str(candidate["asset"]), asset_class=asset_class,
                                            timeframe=str(candidate.get("timeframe") or ""), direction=direction,
                                            status="open", signal_entry=entry, fill_entry=fill, current_price=live,
                                            stop_loss=stop, take_profits=targets, target_price=target,
                                            quantity=quantity, notional=notional, reserved_cash=notional,
                                            entry_fee=entry_fee, exit_fee=0.0, unrealized_pnl=0.0, realized_pnl=0.0,
                                            opened_at=now_utc_naive(),
                                            source=(
                                                "web_signal_receipt"
                                                if str(candidate.get("receipt_channel") or "") == "web"
                                                else "delivered_signal"
                                            ),
                                            meta={
                                                "score": candidate.get("score"), "price_source": "live",
                                                "receipt_channel": candidate.get("receipt_channel") or "telegram",
                                                "receipt_reference": candidate.get("receipt_reference"),
                                                "confirmed_at": str(candidate.get("confirmed_at") or ""),
                                                "risk_pct": float(effective_risk_pct),
                                                "requested_risk_pct": float(sizing.requested_risk_pct),
                                                "requested_risk_amount": float(sizing.risk_amount),
                                                "actual_risk_pct": float(sizing.actual_risk_pct),
                                                "actual_risk_amount": float(sizing.actual_risk_amount),
                                                "risk_per_unit": float(sizing.risk_per_unit),
                                                "uncapped_quantity": float(sizing.uncapped_quantity),
                                                "size_cap_applied": bool(sizing.size_cap_applied),
                                                "size_cap_reason": sizing.size_cap_reason,
                                                "available_cash_before": float(sizing.available_cash_before),
                                                "available_cash_after": float(sizing.available_cash_after),
                                                "margin_required": float(sizing.margin_required),
                                                "leverage": 1.0,
                                                "fees": float(sizing.fees),
                                                "slippage": float(_safe_float(account.slippage_bps) / 10000.0 * live),
                                                "user_trade_profile": getattr(profile_prefs, "trade_profile", "all") if profile_prefs is not None else "all",
                                                "user_risk_profile": getattr(profile_prefs, "risk_profile", "balanced") if profile_prefs is not None else "balanced",
                                                "profile_verified": profile_prefs is not None,
                                                "target_mode": str(account.target_mode or "TP1").upper(),
                                                "sizing_policy_version": sizing.policy_version,
                                                "max_notional_pct": max_notional_pct,
                                                "thesis_fingerprint": candidate.get("thesis_fingerprint"),
                                                "freshness_age_seconds": freshness.age_seconds,
                                                "freshness_max_age_seconds": freshness.max_age_seconds,
                                                "exit_fee_accounting": "deducted_from_final_proceeds",
                                            },
                                        )
                                        account.cash_balance = cash - float(sizing.total_required)
                                        if account.cash_balance < -float(os.getenv("PAPER_CASH_TOLERANCE", "0.00000001")):
                                            raise RuntimeError("paper_cash_balance_would_be_negative")
                                        account.updated_at = now_utc_naive()
                                        session.add(position)
                                        await session.flush()
                                        session.add(PaperLedgerEntry(
                                            account_id=int(account.id), user_id=int(user.id), position_id=position.position_id,
                                            entry_type="POSITION_OPENED", amount=-float(sizing.total_required),
                                            balance_after=_safe_float(account.cash_balance),
                                            description=f"Opened paper {direction.upper()} {candidate['asset']}",
                                            meta={
                                                "fill": fill, "quantity": quantity, "entry_fee": entry_fee,
                                                "sizing_policy_version": sizing.policy_version,
                                            },
                                        ))
                                        attempt = await self._record_attempt(
                                            session, account=account, user=user, candidate=candidate,
                                            decision="OPENED", reason="eligible_confirmed_delivery", retryable=False,
                                            market_price=market_price, sizing=sizing, finalized=True,
                                            meta={
                                                "position_id": position.position_id,
                                                "requested_risk_pct": float(sizing.requested_risk_pct),
                                                "actual_risk_pct": float(sizing.actual_risk_pct),
                                                "actual_risk_amount": float(sizing.actual_risk_amount),
                                                "risk_per_unit": float(sizing.risk_per_unit),
                                                "size_cap_applied": bool(sizing.size_cap_applied),
                                                "size_cap_reason": sizing.size_cap_reason,
                                            },
                                        )
                                        execution_evidence = await get_platform_execution_evidence(
                                            session,
                                            user_id=int(user.id),
                                            signal_id=str(candidate["signal_id"]),
                                            expected_reference=str(position.position_id),
                                        )
                                        if not execution_evidence.get("exactly_one"):
                                            raise RuntimeError("paper_execution_evidence_not_exactly_one")
                                        try:
                                            await session.commit()
                                        except IntegrityError:
                                            await session.rollback()
                                            return "skipped"
                                        result_status = "opened"
                                        notify = {
                                            "decision": "OPENED", "reason": "eligible_confirmed_delivery",
                                            "fill": fill, "sizing": sizing, "risk_pct": float(effective_risk_pct),
                                            "stop": stop, "target": target, "remaining_cash": account.cash_balance,
                                            "position_id": str(position.position_id),
                                            "attempt_id": str(attempt.attempt_id),
                                            "execution_evidence": execution_evidence,
                                        }
                                        logger.info(
                                            "[paper_candidate] user_id=%s signal_id=%s delivery_id=%s asset=%s "
                                            "decision=OPENED cash=%.4f risk_pct=%.4f risk_amount=%.4f fill=%.8f "
                                            "stop=%.8f quantity=%.10f notional=%.4f entry_fee=%.4f target=%.8f",
                                            user.telegram_user_id, candidate["signal_id"], candidate["delivery_id"],
                                            candidate["asset"], cash, _safe_float(account.risk_pct),
                                            float(sizing.risk_amount), fill, stop, quantity, notional, entry_fee, target,
                                        )
        if notify is not None:
            await self._notify_paper_decision(
                telegram_user_id=(
                    int(candidate["telegram_user_id"])
                    if candidate.get("telegram_user_id") is not None
                    else None
                ),
                candidate=candidate,
                **notify,
            )
        if result_status != "opened":
            logger.info(
                "[paper_candidate] user_id=%s signal_id=%s delivery_id=%s asset=%s decision=%s reason=%s",
                candidate.get("telegram_user_id"), candidate.get("signal_id"), candidate.get("delivery_id"),
                candidate.get("asset"), result_status.upper(), (notify or {}).get("reason", "retry_pending"),
            )
        return result_status

    async def _record_skipped(
        self, session, account: PaperAccount, user: User, candidate: dict[str, Any],
        reason: str, market_price: float | None,
    ) -> None:
        """Compatibility adapter: skipped decisions now live in the attempt ledger."""
        await self._record_attempt(
            session, account=account, user=user, candidate=candidate,
            decision="SKIPPED", reason=reason, retryable=False,
            market_price=market_price, finalized=True,
        )
    async def list_attempts(
        self,
        user_id: int,
        *,
        decision: str | None = None,
        limit: int = 20,
        user_identity: str = "telegram",
    ) -> list[dict[str, Any]]:
        identity = str(user_identity or "telegram").strip().lower()
        async with get_session(priority="interactive", label="paper.activity") as session:
            user = await self._user_row(
                session,
                int(user_id),
                user_identity=identity,
            )
            if user is None:
                return []
            query = (
                select(PaperTradeAttempt, Signal)
                .join(Signal, Signal.signal_id == PaperTradeAttempt.signal_id)
                .where(PaperTradeAttempt.user_id == int(user.id))
            )
            if decision:
                query = query.where(
                    PaperTradeAttempt.decision == str(decision).upper()
                )
            rows = (
                await session.execute(
                    query.order_by(PaperTradeAttempt.created_at.desc()).limit(
                        max(1, min(100, int(limit)))
                    )
                )
            ).all()
            return [
                {
                    "attempt_id": attempt.attempt_id,
                    "signal_id": attempt.signal_id,
                    "display_id": str(
                        getattr(signal, "display_id", "")
                        or attempt.signal_id[:12]
                    ),
                    "asset": signal.asset,
                    "decision": attempt.decision,
                    "reason": attempt.reason,
                    "retryable": bool(attempt.retryable),
                    "attempt_number": int(attempt.attempt_number or 0),
                    "receipt_channel": str(
                        getattr(attempt, "receipt_channel", "telegram")
                        or "telegram"
                    ),
                    "receipt_reference": getattr(
                        attempt,
                        "receipt_reference",
                        None,
                    ),
                    "created_at": attempt.created_at,
                    "next_retry_at": attempt.next_retry_at,
                    "retry_deadline": attempt.retry_deadline,
                }
                for attempt, signal in rows
            ]

    async def status_detail(
        self,
        user_id: int,
        *,
        user_identity: str = "telegram",
    ) -> dict[str, Any] | None:
        identity = str(user_identity or "telegram").strip().lower()
        snapshot = await self.snapshot(
            int(user_id),
            user_identity=identity,
        )
        if snapshot is None:
            return None
        activity = await self.list_attempts(
            int(user_id),
            limit=100,
            user_identity=identity,
        )
        counts: dict[str, int] = {}
        for row in activity:
            key = str(row["decision"]).lower()
            counts[key] = counts.get(key, 0) + 1
        return {
            "snapshot": asdict(snapshot),
            "globally_available": _env_bool("PAPER_TRADING_ENABLED", True),
            "worker_last_scan": getattr(self, "_last_cycle_at", None),
            "worker_last_result": getattr(self, "_last_cycle_result", {}),
            "last_decision": activity[0] if activity else None,
            "recent_counts": counts,
        }

    async def request_retry(
        self,
        user_id: int,
        signal_reference: str,
        *,
        user_identity: str = "telegram",
    ) -> tuple[bool, str]:
        from db.signal_reference import SignalReferenceError, resolve_signal_reference

        identity = str(user_identity or "telegram").strip().lower()
        now = now_utc_naive()
        async with get_session(
            priority="interactive",
            label="paper.retry",
        ) as session:
            try:
                if identity == "platform":
                    resolved = await resolve_signal_reference(
                        session,
                        signal_reference,
                        canonical_user_id=int(user_id),
                        require_delivery_proof=True,
                    )
                else:
                    resolved = await resolve_signal_reference(
                        session,
                        signal_reference,
                        telegram_user_id=int(user_id),
                        require_delivery_proof=True,
                    )
            except SignalReferenceError as exc:
                return False, str(exc)

            user = await self._user_row(
                session,
                int(user_id),
                user_identity=identity,
            )
            if user is None:
                return False, "paper account user not found"
            account = (
                await session.execute(
                    select(PaperAccount)
                    .where(PaperAccount.user_id == int(user.id))
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if account is None or not bool(account.auto_trade_enabled):
                return False, "automatic paper trading is off"

            signal_id = str(resolved.signal.signal_id)
            actual = (
                await session.execute(
                    select(PaperPosition.position_id).where(
                        PaperPosition.user_id == int(user.id),
                        PaperPosition.signal_id == signal_id,
                        func.lower(PaperPosition.status).in_(["open", "closed"]),
                    ).limit(1)
                )
            ).scalar_one_or_none()
            if actual:
                return False, "a paper position already exists"

            delivery = (
                await session.execute(
                    select(SignalDelivery).where(
                        SignalDelivery.user_id == int(user.id),
                        SignalDelivery.signal_id == signal_id,
                        SignalDelivery.sent_ok.is_(True),
                        SignalDelivery.telegram_chat_id.is_not(None),
                        SignalDelivery.telegram_message_id.is_not(None),
                        SignalDelivery.delivery_confirmed_at.is_not(None),
                        func.lower(SignalDelivery.delivery_state).in_(
                            tuple(CONFIRMED_DELIVERY_STATES)
                        ),
                    ).limit(1)
                )
            ).scalar_one_or_none()

            receipt_channel = "telegram"
            receipt_reference: str | None = None
            delivery_id: int | None = None
            confirmed_at = None
            generated_at = resolved.signal.created_at
            if delivery is not None:
                delivery_id = int(delivery.id)
                receipt_reference = str(delivery.id)
                confirmed_at = delivery.delivery_confirmed_at
                generated_at = delivery.generated_at_utc or resolved.signal.created_at
            elif identity == "platform":
                web_receipt = (
                    await session.execute(
                        text(
                            """
                            SELECT notification_id,created_at
                            FROM notification_events
                            WHERE user_id=:uid
                              AND event_type='signal'
                              AND channel_data->>'channel'='web'
                              AND channel_data->>'signal_id'=:sid
                            ORDER BY created_at DESC
                            LIMIT 1
                            """
                        ),
                        {"uid": int(user.id), "sid": signal_id},
                    )
                ).mappings().first()
                if web_receipt is not None:
                    receipt_channel = "web"
                    receipt_reference = str(web_receipt["notification_id"])
                    confirmed_at = web_receipt["created_at"]

            if not receipt_reference:
                return False, "confirmed delivery proof is missing"

            freshness = evaluate_signal_freshness(
                timeframe=resolved.signal.timeframe,
                generated_at=generated_at,
                now=now,
                purpose="paper",
            )
            deadline = generated_at + timedelta(
                seconds=freshness.max_age_seconds
            )
            if not freshness.ok or deadline <= now:
                return False, "paper entry freshness deadline expired"

            terminal_statuses = tuple(
                TERMINAL_OUTCOMES - {"tp1", "tp2", "partial_win"}
            )
            terminal = await session.scalar(
                select(Outcome.id).where(
                    Outcome.signal_id == signal_id,
                    func.lower(Outcome.status).in_(terminal_statuses),
                ).limit(1)
            )
            if terminal is not None:
                return False, "signal already has a terminal outcome"

            candidate = {
                "signal_id": signal_id,
                "delivery_id": delivery_id,
                "receipt_channel": receipt_channel,
                "receipt_reference": receipt_reference,
                "retry_deadline": deadline,
                "asset": resolved.signal.asset,
                "user_id": int(user.id),
                "telegram_user_id": (
                    int(user.telegram_user_id)
                    if user.telegram_user_id is not None
                    else None
                ),
                "confirmed_at": confirmed_at,
            }
            await self._record_attempt(
                session,
                account=account,
                user=user,
                candidate=candidate,
                decision="RETRY_PENDING",
                reason="manual_retry_requested",
                retryable=True,
                next_retry_seconds=1,
                meta={
                    "requested_by": int(user_id),
                    "user_identity": identity,
                },
            )
            await session.commit()
            return True, "retry queued"

    async def _open_position_snapshots(self, limit: int) -> list[dict[str, Any]]:
        async with get_session(priority=_paper_worker_priority(), label="paper.open_snapshots", timeout_seconds=_paper_db_timeout(8.0)) as session:
            rows = (
                await session.execute(
                    select(PaperPosition.position_id, PaperPosition.asset)
                    .where(PaperPosition.status == "open")
                    .order_by(PaperPosition.updated_at.asc())
                    .limit(max(1, min(2000, int(limit))))
                )
            ).all()
            return [{"position_id": str(pid), "asset": str(asset)} for pid, asset in rows]

    async def mark_to_market(self, *, limit: int = 500) -> dict[str, int]:
        snapshots = await self._open_position_snapshots(limit)
        if not snapshots:
            return {"positions": 0, "updated": 0, "closed": 0, "failed": 0}
        assets = sorted({row["asset"] for row in snapshots})
        try:
            from engine.price_fetcher import get_live_price_batch
            prices = await get_live_price_batch(assets, max_concurrent=_env_int("PAPER_PRICE_CONCURRENCY", 4, 1, 20))
        except Exception as exc:
            logger.warning("[paper] mark-to-market prices unavailable: %s", exc)
            prices = {}
        result = {"positions": len(snapshots), "updated": 0, "closed": 0, "failed": 0}
        for item in snapshots:
            price = _safe_float(prices.get(item["asset"]))
            if price <= 0:
                continue
            try:
                closed = await self._mark_one(item["position_id"], price)
                result["closed" if closed else "updated"] += 1
            except Exception:
                result["failed"] += 1
                logger.exception("[paper] mark-to-market failed position=%s", item["position_id"])
        return result

    async def _mark_one(
        self, position_id: str, current_price: float, *, force_exit_reason: str | None = None,
    ) -> bool:
        async with get_session(priority=_paper_worker_priority(), label="paper.mark_one", timeout_seconds=_paper_db_timeout(10.0)) as session:
            position = (
                await session.execute(
                    select(PaperPosition).where(PaperPosition.position_id == str(position_id)).with_for_update()
                )
            ).scalar_one_or_none()
            if position is None or position.status != "open":
                return False
            account = (
                await session.execute(
                    select(PaperAccount).where(PaperAccount.id == int(position.account_id)).with_for_update()
                )
            ).scalar_one_or_none()
            if account is None:
                return False
            direction = canonical_direction(position.direction)
            quantity = _safe_float(position.quantity)
            fill = _safe_float(position.fill_entry)
            gross = (current_price - fill) * quantity if direction == "long" else (fill - current_price) * quantity
            position.current_price = current_price
            position.unrealized_pnl = gross
            position.updated_at = now_utc_naive()
            exit_reason: str | None = str(force_exit_reason or "").strip().upper() or None
            target = _safe_float(position.target_price)
            stop = _safe_float(position.stop_loss)
            if exit_reason is None and direction == "long":
                if target > 0 and current_price >= target:
                    exit_reason = str((position.meta or {}).get("target_mode") or "TP")
                elif stop > 0 and current_price <= stop:
                    exit_reason = "SL"
            elif exit_reason is None:
                if target > 0 and current_price <= target:
                    exit_reason = str((position.meta or {}).get("target_mode") or "TP")
                elif stop > 0 and current_price >= stop:
                    exit_reason = "SL"
            if exit_reason is None:
                await session.commit()
                return False
            exit_notional = quantity * current_price
            exit_fee = exit_notional * (_safe_float(account.fee_bps) / 10000.0)
            net_pnl = gross - _safe_float(position.entry_fee) - exit_fee
            risk_amount = abs(fill - stop) * quantity
            r_multiple = net_pnl / risk_amount if risk_amount > 0 else 0.0
            account.cash_balance = _safe_float(account.cash_balance) + _safe_float(position.reserved_cash) + gross - exit_fee
            account.realized_pnl = _safe_float(account.realized_pnl) + net_pnl
            account.updated_at = now_utc_naive()
            position.status = "closed"
            position.exit_fee = exit_fee
            position.realized_pnl = net_pnl
            position.unrealized_pnl = 0.0
            position.r_multiple = r_multiple
            position.closed_at = now_utc_naive()
            position.exit_reason = exit_reason
            session.add(PaperLedgerEntry(
                account_id=int(account.id),
                user_id=int(position.user_id),
                position_id=position.position_id,
                entry_type="POSITION_CLOSED",
                amount=_safe_float(position.reserved_cash) + gross - exit_fee,
                balance_after=_safe_float(account.cash_balance),
                description=f"Closed paper {position.asset} at {exit_reason}",
                meta={"exit_price": current_price, "net_pnl": net_pnl, "r_multiple": r_multiple},
            ))
            await session.commit()
            logger.info(
                "[paper_auto_close] position=%s signal=%s asset=%s reason=%s pnl=%.4f r=%.3f",
                position.position_id, position.signal_id, position.asset, exit_reason, net_pnl, r_multiple,
            )
            return True

    async def close_all_positions(
        self,
        user_id: int,
        *,
        reason: str = "MANUAL_CLOSE_ALL",
        allow_last_mark_fallback: bool = False,
        user_identity: str = "telegram",
    ) -> dict[str, int]:
        """Close every open virtual position at a fresh live quote."""
        identity = str(user_identity or "telegram").strip().lower()
        async with get_session(
            priority="interactive",
            label="paper.close_all.list",
        ) as session:
            user = await self._user_row(
                session,
                int(user_id),
                user_identity=identity,
            )
            if user is None:
                return {"open": 0, "closed": 0, "failed": 0}
            rows = (
                await session.execute(
                    select(
                        PaperPosition.position_id,
                        PaperPosition.asset,
                        PaperPosition.current_price,
                        PaperPosition.updated_at,
                    ).where(
                        PaperPosition.user_id == int(user.id),
                        func.lower(PaperPosition.status) == "open",
                    )
                )
            ).all()
        if not rows:
            return {"open": 0, "closed": 0, "failed": 0}
        assets = sorted({
            str(asset)
            for _, asset, _current_price, _updated_at in rows
        })
        try:
            from engine.price_fetcher import get_live_price_batch

            prices = await get_live_price_batch(
                assets,
                max_concurrent=_env_int(
                    "PAPER_PRICE_CONCURRENCY",
                    4,
                    1,
                    20,
                ),
            )
        except Exception:
            logger.exception(
                "[paper_close_all] quote batch failed user=%s identity=%s",
                user_id,
                identity,
            )
            prices = {}
        result = {
            "open": len(rows),
            "closed": 0,
            "failed": 0,
            "last_mark_fallback": 0,
        }
        max_last_mark_age = _env_int(
            "PAPER_CLOSE_ALL_LAST_MARK_MAX_AGE_SECONDS",
            300,
            30,
            3600,
        )
        now = now_utc_naive()
        for position_id, asset, last_mark, last_updated_at in rows:
            price = _safe_float(prices.get(str(asset)))
            if price <= 0 and allow_last_mark_fallback:
                try:
                    mark_age = (
                        (now - last_updated_at).total_seconds()
                        if last_updated_at
                        else float("inf")
                    )
                except Exception:
                    mark_age = float("inf")
                if (
                    _safe_float(last_mark) > 0
                    and mark_age <= max_last_mark_age
                ):
                    price = _safe_float(last_mark)
                    result["last_mark_fallback"] += 1
                    logger.warning(
                        "[paper_close_all] using fresh last mark "
                        "position=%s asset=%s age_s=%.1f",
                        position_id,
                        asset,
                        mark_age,
                    )
            if price <= 0:
                result["failed"] += 1
                continue
            try:
                closed = await self._mark_one(
                    str(position_id),
                    price,
                    force_exit_reason=str(
                        reason or "MANUAL_CLOSE_ALL"
                    ),
                )
                result["closed" if closed else "failed"] += 1
            except Exception:
                result["failed"] += 1
                logger.exception(
                    "[paper_close_all] position=%s failed",
                    position_id,
                )
        return result

    async def loop(self, stop_event: asyncio.Event) -> None:
        interval = _env_float("PAPER_TRADING_WORKER_INTERVAL_SECONDS", 20.0, 5.0, 3600.0)
        delivery_limit = _env_int("PAPER_TRADING_DELIVERY_BATCH_SIZE", 100, 1, 500)
        mark_limit = _env_int("PAPER_TRADING_MARK_BATCH_SIZE", 500, 1, 2000)
        logger.info(
            "[paper_worker] started interval=%.1fs auto_default=%s delivery_batch=%s mark_batch=%s",
            interval, self._default_auto_enabled(), delivery_limit, mark_limit,
        )
        last_deferred_log = 0.0
        while not stop_event.is_set():
            opened = {"candidates": 0, "opened": 0, "skipped": 0, "deferred": 0, "failed": 0}
            marked = {"positions": 0, "updated": 0, "closed": 0, "failed": 0}

            # Delivery processing and mark-to-market are isolated so DB pressure
            # in one phase cannot suppress the other phase for the whole cycle.
            try:
                opened = await self.process_new_deliveries(limit=delivery_limit)
            except NoncriticalWriteDropped as exc:
                now_mono = time.monotonic()
                if now_mono - last_deferred_log >= 60.0:
                    logger.info("[paper_worker] delivery phase deferred by DB admission: %s", exc)
                    last_deferred_log = now_mono
            except Exception as exc:
                logger.exception("[paper_worker] delivery phase failed: %s", exc)

            try:
                marked = await self.mark_to_market(limit=mark_limit)
            except NoncriticalWriteDropped as exc:
                now_mono = time.monotonic()
                if now_mono - last_deferred_log >= 60.0:
                    logger.info("[paper_worker] mark phase deferred by DB admission: %s", exc)
                    last_deferred_log = now_mono
            except Exception as exc:
                logger.exception("[paper_worker] mark phase failed: %s", exc)

            self._last_cycle_at = now_utc_naive()
            self._last_cycle_result = {"openings": dict(opened), "marking": dict(marked)}
            logger.info(
                "[paper_worker_cycle] candidates=%s opened=%s skipped=%s deferred=%s failed=%s "
                "marked=%s closed=%s",
                opened.get("candidates", 0), opened.get("opened", 0), opened.get("skipped", 0),
                opened.get("deferred", 0), opened.get("failed", 0), marked.get("updated", 0),
                marked.get("closed", 0),
            )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue


paper_trading_service = PaperTradingService()


__all__ = [
    "PaperSnapshot", "PaperTradingService", "paper_trading_service",
    "canonical_asset_class", "canonical_direction", "parse_targets",
]
