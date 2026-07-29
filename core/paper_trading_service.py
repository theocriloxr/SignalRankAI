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
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError

from db.models import (
    Outcome,
    PaperAccount,
    PaperLedgerEntry,
    PaperPosition,
    Signal,
    SignalDelivery,
    User,
)
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
    telegram_user_id: int
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
        return _env_bool("PAPER_AUTO_TRADE_DEFAULT_ENABLED", True)

    async def _user_row(self, session, telegram_user_id: int) -> User | None:
        return (
            await session.execute(
                select(User).where(User.telegram_user_id == int(telegram_user_id)).limit(1)
            )
        ).scalar_one_or_none()

    async def ensure_account(self, telegram_user_id: int, *, session=None) -> PaperAccount | None:
        if session is not None:
            return await self._ensure_account_in_session(session, int(telegram_user_id))
        async with get_session(priority="interactive", label="paper.ensure_account") as owned_session:
            try:
                account = await self._ensure_account_in_session(owned_session, int(telegram_user_id))
                await owned_session.commit()
                return account
            except IntegrityError:
                await owned_session.rollback()
                user = await self._user_row(owned_session, int(telegram_user_id))
                if user is None:
                    return None
                return (
                    await owned_session.execute(
                        select(PaperAccount).where(PaperAccount.user_id == int(user.id)).limit(1)
                    )
                ).scalar_one_or_none()

    async def _ensure_account_in_session(self, session, telegram_user_id: int) -> PaperAccount | None:
        user = await self._user_row(session, int(telegram_user_id))
        if user is None:
            return None
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

    async def snapshot(self, telegram_user_id: int) -> PaperSnapshot | None:
        async with get_session(priority="interactive", label="paper.snapshot") as session:
            account = await self.ensure_account(int(telegram_user_id), session=session)
            if account is None:
                return None
            # Persist a newly created account before returning a snapshot.
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
                telegram_user_id=int(telegram_user_id),
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
                allowed_asset_classes=[str(x).lower() for x in (account.allowed_asset_classes or [])],
            )

    async def update_settings(self, telegram_user_id: int, **changes: Any) -> PaperSnapshot | None:
        allowed = {
            "auto_trade_enabled", "risk_pct", "max_open_positions", "min_signal_score",
            "spread_bps", "slippage_bps", "fee_bps", "target_mode",
            "allowed_directions", "allowed_asset_classes",
        }
        async with get_session(priority="interactive", label="paper.update_settings") as session:
            user = await self._user_row(session, int(telegram_user_id))
            if user is None:
                return None
            account = (
                await session.execute(
                    select(PaperAccount).where(PaperAccount.user_id == int(user.id)).with_for_update()
                )
            ).scalar_one_or_none()
            if account is None:
                account = await self.ensure_account(int(telegram_user_id), session=session)
            if account is None:
                return None
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
                    value = sorted({str(x).strip().lower() for x in (value or []) if str(x).strip()})
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
                meta=changed,
            ))
            await session.commit()
        return await self.snapshot(int(telegram_user_id))

    async def reset_account(self, telegram_user_id: int, starting_balance: float) -> PaperSnapshot | None:
        balance = max(50.0, min(100_000_000.0, _safe_float(starting_balance, self._default_balance())))
        async with get_session(priority="interactive", label="paper.reset") as session:
            user = await self._user_row(session, int(telegram_user_id))
            if user is None:
                return None
            account = (
                await session.execute(
                    select(PaperAccount).where(PaperAccount.user_id == int(user.id)).with_for_update()
                )
            ).scalar_one_or_none()
            if account is None:
                account = await self.ensure_account(int(telegram_user_id), session=session)
            if account is None:
                return None
            open_count = int((
                await session.execute(
                    select(func.count(PaperPosition.position_id)).where(
                        PaperPosition.user_id == int(user.id),
                        PaperPosition.status == "open",
                    )
                )
            ).scalar() or 0)
            if open_count:
                raise ValueError("Close or wait for all paper positions before resetting the account")
            await session.execute(
                PaperPosition.__table__.delete().where(PaperPosition.user_id == int(user.id))
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
                meta={"starting_balance": balance},
            ))
            await session.commit()
        return await self.snapshot(int(telegram_user_id))

    async def list_positions(self, telegram_user_id: int, *, status: str = "open", limit: int = 20) -> list[dict[str, Any]]:
        async with get_session(priority="interactive", label="paper.list_positions") as session:
            user = await self._user_row(session, int(telegram_user_id))
            if user is None:
                return []
            query = select(PaperPosition).where(PaperPosition.user_id == int(user.id))
            if status:
                query = query.where(PaperPosition.status == str(status).lower())
            rows = (
                await session.execute(
                    query.order_by(PaperPosition.opened_at.desc()).limit(max(1, min(100, int(limit))))
                )
            ).scalars().all()
            return [self._position_dict(row) for row in rows]

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

    async def performance(self, telegram_user_id: int) -> dict[str, Any]:
        snapshot = await self.snapshot(int(telegram_user_id))
        if snapshot is None:
            return {}
        rows = await self.list_positions(int(telegram_user_id), status="closed", limit=500)
        wins = [r for r in rows if _safe_float(r.get("realized_pnl")) > 0]
        losses = [r for r in rows if _safe_float(r.get("realized_pnl")) < 0]
        flat = [r for r in rows if abs(_safe_float(r.get("realized_pnl"))) < 1e-9]
        net = sum(_safe_float(r.get("realized_pnl")) for r in rows)
        gross_win = sum(_safe_float(r.get("realized_pnl")) for r in wins)
        gross_loss = abs(sum(_safe_float(r.get("realized_pnl")) for r in losses))
        r_values = [_safe_float(r.get("r_multiple")) for r in rows if r.get("r_multiple") is not None]
        return {
            "snapshot": asdict(snapshot),
            "sample_size": len(rows),
            "wins": len(wins),
            "losses": len(losses),
            "flat": len(flat),
            "win_rate_pct": (len(wins) / len(rows) * 100.0) if rows else 0.0,
            "net_pnl": net,
            "return_pct": (net / snapshot.starting_balance * 100.0) if snapshot.starting_balance > 0 else 0.0,
            "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0),
            "avg_r": (sum(r_values) / len(r_values)) if r_values else 0.0,
        }

    async def delivered_r_samples(self, telegram_user_id: int) -> dict[str, Any]:
        async with get_session(priority="interactive", label="paper.simulation_samples") as session:
            user = await self._user_row(session, int(telegram_user_id))
            if user is None:
                return {"r_values": [], "first": None, "last": None}
            rows = (
                await session.execute(
                    select(
                        Outcome.signal_id,
                        Outcome.r_multiple,
                        Outcome.closed_at,
                        SignalDelivery.delivery_confirmed_at,
                    )
                    .join(SignalDelivery, SignalDelivery.signal_id == Outcome.signal_id)
                    .where(
                        SignalDelivery.user_id == int(user.id),
                        SignalDelivery.sent_ok.is_(True),
                        func.upper(SignalDelivery.delivery_state).in_(["CONFIRMED", "RECONCILED", "DELIVERED"]),
                        Outcome.r_multiple.is_not(None),
                    )
                    .order_by(Outcome.closed_at.asc().nulls_last())
                )
            ).all()
            seen: set[str] = set()
            r_values: list[float] = []
            times: list[Any] = []
            for signal_id, r_multiple, closed_at, confirmed_at in rows:
                sid = str(signal_id or "")
                if not sid or sid in seen:
                    continue
                seen.add(sid)
                r_values.append(_safe_float(r_multiple))
                when = closed_at or confirmed_at
                if when is not None:
                    times.append(when)
            return {
                "r_values": r_values,
                "first": min(times) if times else None,
                "last": max(times) if times else None,
            }

    async def _delivery_candidates(self, limit: int) -> list[dict[str, Any]]:
        max_age_s = _env_int("PAPER_AUTO_ENTRY_MAX_AGE_SECONDS", 900, 30, 86400)
        cutoff = now_utc_naive() - timedelta(seconds=max_age_s)
        async with get_session(priority=_paper_worker_priority(), label="paper.delivery_candidates", timeout_seconds=_paper_db_timeout(8.0)) as session:
            rows = (
                await session.execute(
                    select(SignalDelivery, Signal, User, PaperAccount, PaperPosition.position_id)
                    .join(Signal, Signal.signal_id == SignalDelivery.signal_id)
                    .join(User, User.id == SignalDelivery.user_id)
                    .outerjoin(PaperAccount, PaperAccount.user_id == User.id)
                    .outerjoin(
                        PaperPosition,
                        and_(
                            PaperPosition.user_id == User.id,
                            PaperPosition.signal_id == SignalDelivery.signal_id,
                        ),
                    )
                    .where(
                        SignalDelivery.sent_ok.is_(True),
                        func.upper(SignalDelivery.delivery_state).in_(["CONFIRMED", "RECONCILED", "DELIVERED"]),
                        SignalDelivery.delivery_confirmed_at.is_not(None),
                        SignalDelivery.delivery_confirmed_at >= cutoff,
                        PaperPosition.position_id.is_(None),
                    )
                    .order_by(SignalDelivery.id.asc())
                    .limit(max(1, min(500, int(limit))))
                )
            ).all()
            out: list[dict[str, Any]] = []
            for delivery, signal, user, account, _ in rows:
                out.append({
                    "delivery_id": int(delivery.id),
                    "telegram_user_id": int(user.telegram_user_id),
                    "user_id": int(user.id),
                    "signal_id": str(signal.signal_id),
                    "asset": str(signal.asset),
                    "asset_class": canonical_asset_class(str(signal.asset), signal.asset_class),
                    "timeframe": str(signal.timeframe or ""),
                    "direction": canonical_direction(signal.direction),
                    "entry": _safe_float(signal.entry),
                    "stop_loss": _safe_float(signal.stop_loss),
                    "take_profits": parse_targets(signal.take_profit),
                    "score": _safe_float(signal.score),
                    "confirmed_at": delivery.delivery_confirmed_at,
                    "account_exists": account is not None,
                })
            return out

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
            logger.warning("[paper] live price batch failed; new paper entries will be skipped: %s", exc)
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

    async def _open_candidate(self, candidate: dict[str, Any], market_price: float | None) -> str:
        async with get_session(priority=_paper_worker_priority(), label="paper.open_candidate", timeout_seconds=_paper_db_timeout(10.0)) as session:
            user = (
                await session.execute(
                    select(User).where(User.id == int(candidate["user_id"])).limit(1)
                )
            ).scalar_one_or_none()
            if user is None:
                return "skipped"
            account = (
                await session.execute(
                    select(PaperAccount).where(PaperAccount.user_id == int(user.id)).with_for_update()
                )
            ).scalar_one_or_none()
            if account is None:
                account = await self.ensure_account(int(user.telegram_user_id), session=session)
            if account is None or account.status != "active" or not bool(account.auto_trade_enabled):
                return "skipped"
            existing = (
                await session.execute(
                    select(PaperPosition.position_id).where(
                        PaperPosition.user_id == int(user.id),
                        PaperPosition.signal_id == str(candidate["signal_id"]),
                    ).limit(1)
                )
            ).scalar_one_or_none()
            if existing:
                return "skipped"
            open_count = int((
                await session.execute(
                    select(func.count(PaperPosition.position_id)).where(
                        PaperPosition.user_id == int(user.id),
                        PaperPosition.status == "open",
                    )
                )
            ).scalar() or 0)
            skip_reason = ""
            if open_count >= int(account.max_open_positions or 0):
                skip_reason = "max_open_positions"
            if _safe_float(candidate.get("score")) < _safe_float(account.min_signal_score):
                skip_reason = skip_reason or "score_below_paper_minimum"
            direction = canonical_direction(candidate.get("direction"))
            allowed_direction = str(account.allowed_directions or "both").lower()
            if allowed_direction not in {"both", direction}:
                skip_reason = skip_reason or "direction_not_allowed"
            asset_class = canonical_asset_class(candidate.get("asset"), candidate.get("asset_class"))
            allowed_classes = {str(x).lower() for x in (account.allowed_asset_classes or [])}
            if allowed_classes and asset_class not in allowed_classes:
                skip_reason = skip_reason or "asset_class_not_allowed"

            entry = _safe_float(candidate.get("entry"))
            stop = _safe_float(candidate.get("stop_loss"))
            targets = parse_targets(candidate.get("take_profits"))
            if entry <= 0 or stop <= 0 or not targets:
                skip_reason = skip_reason or "incomplete_signal_levels"
            if skip_reason:
                await self._record_skipped(session, account, user, candidate, skip_reason, market_price)
                await session.commit()
                return "skipped"

            live = _safe_float(market_price)
            if live <= 0:
                # Transient provider failure is not a strategy rejection. Leave the
                # delivery unconsumed so the worker can retry while it is fresh.
                return "deferred"
            bps = (_safe_float(account.spread_bps) + _safe_float(account.slippage_bps)) / 10000.0
            fill = live * (1.0 + bps if direction == "long" else 1.0 - bps)
            risk_per_unit = abs(fill - stop)
            if risk_per_unit <= 0:
                await self._record_skipped(session, account, user, candidate, "invalid_risk_distance", market_price)
                await session.commit()
                return "skipped"
            cash = _safe_float(account.cash_balance)
            risk_amount = cash * (_safe_float(account.risk_pct, 1.0) / 100.0)
            quantity = risk_amount / risk_per_unit
            max_notional_pct = _env_float("PAPER_MAX_NOTIONAL_PCT", 100.0, 1.0, 100.0)
            max_notional = cash * (max_notional_pct / 100.0)
            quantity = min(quantity, max_notional / fill if fill > 0 else 0.0)
            notional = quantity * fill
            entry_fee = notional * (_safe_float(account.fee_bps) / 10000.0)
            if quantity <= 0 or notional + entry_fee > cash:
                await self._record_skipped(session, account, user, candidate, "insufficient_virtual_cash", market_price)
                await session.commit()
                return "skipped"
            target_idx = {"TP1": 0, "TP2": 1, "TP3": 2}.get(str(account.target_mode or "TP1").upper(), 0)
            target = targets[min(target_idx, len(targets) - 1)]
            valid_geometry = (stop < fill < target) if direction == "long" else (target < fill < stop)
            if not valid_geometry:
                await self._record_skipped(session, account, user, candidate, "paper_entry_no_longer_valid", market_price)
                await session.commit()
                return "skipped"
            position = PaperPosition(
                position_id=str(uuid4()),
                account_id=int(account.id),
                user_id=int(user.id),
                signal_id=str(candidate["signal_id"]),
                delivery_id=int(candidate["delivery_id"]),
                asset=str(candidate["asset"]),
                asset_class=asset_class,
                timeframe=str(candidate.get("timeframe") or ""),
                direction=direction,
                status="open",
                signal_entry=entry,
                fill_entry=fill,
                current_price=live,
                stop_loss=stop,
                take_profits=targets,
                target_price=target,
                quantity=quantity,
                notional=notional,
                reserved_cash=notional,
                entry_fee=entry_fee,
                exit_fee=0.0,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                opened_at=now_utc_naive(),
                source="delivered_signal",
                meta={
                    "score": candidate.get("score"),
                    "price_source": "live",
                    "confirmed_at": str(candidate.get("confirmed_at") or ""),
                    "risk_pct": _safe_float(account.risk_pct),
                    "target_mode": str(account.target_mode or "TP1").upper(),
                },
            )
            account.cash_balance = cash - notional - entry_fee
            account.updated_at = now_utc_naive()
            session.add(position)
            await session.flush()
            session.add(PaperLedgerEntry(
                account_id=int(account.id),
                user_id=int(user.id),
                position_id=position.position_id,
                entry_type="POSITION_OPENED",
                amount=-(notional + entry_fee),
                balance_after=_safe_float(account.cash_balance),
                description=f"Opened paper {direction.upper()} {candidate['asset']}",
                meta={"fill": fill, "quantity": quantity, "entry_fee": entry_fee},
            ))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return "skipped"
            logger.info(
                "[paper_auto_open] user=%s signal=%s asset=%s direction=%s fill=%.8f quantity=%.8f target=%.8f",
                user.telegram_user_id, candidate["signal_id"], candidate["asset"], direction, fill, quantity, target,
            )
            return "opened"

    async def _record_skipped(self, session, account: PaperAccount, user: User, candidate: dict[str, Any], reason: str, market_price: float | None) -> None:
        position = PaperPosition(
            position_id=str(uuid4()),
            account_id=int(account.id),
            user_id=int(user.id),
            signal_id=str(candidate["signal_id"]),
            delivery_id=int(candidate["delivery_id"]),
            asset=str(candidate["asset"]),
            asset_class=canonical_asset_class(candidate.get("asset"), candidate.get("asset_class")),
            timeframe=str(candidate.get("timeframe") or ""),
            direction=canonical_direction(candidate.get("direction")),
            status="skipped",
            signal_entry=_safe_float(candidate.get("entry")),
            fill_entry=_safe_float(market_price, _safe_float(candidate.get("entry"))),
            current_price=_safe_float(market_price, _safe_float(candidate.get("entry"))),
            stop_loss=_safe_float(candidate.get("stop_loss")),
            take_profits=parse_targets(candidate.get("take_profits")),
            target_price=None,
            quantity=0.0,
            notional=0.0,
            reserved_cash=0.0,
            entry_fee=0.0,
            exit_fee=0.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            opened_at=now_utc_naive(),
            closed_at=now_utc_naive(),
            exit_reason=str(reason),
            source="delivered_signal",
            meta={"score": candidate.get("score"), "skip_reason": str(reason)},
        )
        session.add(position)
        session.add(PaperLedgerEntry(
            account_id=int(account.id),
            user_id=int(user.id),
            position_id=position.position_id,
            entry_type="SIGNAL_SKIPPED",
            amount=0.0,
            balance_after=_safe_float(account.cash_balance),
            description=f"Paper signal skipped: {reason}",
            meta={"signal_id": candidate.get("signal_id"), "asset": candidate.get("asset")},
        ))

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

    async def _mark_one(self, position_id: str, current_price: float) -> bool:
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
            exit_reason: str | None = None
            target = _safe_float(position.target_price)
            stop = _safe_float(position.stop_loss)
            if direction == "long":
                if target > 0 and current_price >= target:
                    exit_reason = str((position.meta or {}).get("target_mode") or "TP")
                elif stop > 0 and current_price <= stop:
                    exit_reason = "SL"
            else:
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

            if opened.get("opened") or marked.get("closed"):
                logger.info("[paper_worker] cycle openings=%s marking=%s", opened, marked)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue


paper_trading_service = PaperTradingService()


__all__ = [
    "PaperSnapshot", "PaperTradingService", "paper_trading_service",
    "canonical_asset_class", "canonical_direction", "parse_targets",
]
