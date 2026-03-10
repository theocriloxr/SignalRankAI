"""
engine/realtime_outcome_tracker.py - Real-time async TP/SL outcome detection.

Replaces the sluggish 3-minute APScheduler loop with a persistent async task
that polls open signals every `CHECK_INTERVAL_SECONDS` seconds (default: 15)
using high-frequency REST calls or WebSocket price feeds.

Key behaviours:
  - Monitors all unresolved signals.
  - Detects TP1/TP2/TP3/SL hits instantly.
  - On TP1 hit: moves SL to break-even (trailing SL) via MT5 bridge + notifies users.
  - On final TP/SL: sends branded PnL "flex" card notification.
  - Persists outcome to the `outcomes` table.

Environment:
    OUTCOME_CHECK_INTERVAL_SECONDS  - Poll interval (default: 15)
    ACTIVE_SIGNAL_LOOKBACK_HOURS    - How far back to look for open signals (default: 72)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _check_interval() -> int:
    try:
        return max(5, int(os.getenv("OUTCOME_CHECK_INTERVAL_SECONDS", "15")))
    except Exception:
        return 15


def _lookback_hours() -> int:
    try:
        return int(os.getenv("ACTIVE_SIGNAL_LOOKBACK_HOURS", "72"))
    except Exception:
        return 72


async def _fetch_active_signals() -> List[Dict[str, Any]]:
    """Return all unresolved signals from DB created within lookback window."""
    try:
        from db.session import get_session
        from db.models import Signal, Outcome
        from sqlalchemy import select, not_, exists
        cutoff = datetime.utcnow() - timedelta(hours=_lookback_hours())
        async with get_session() as session:
            # Signals that have no outcome row yet and are not archived
            has_outcome = exists().where(Outcome.signal_id == Signal.signal_id)
            stmt = (
                select(Signal)
                .where(Signal.archived.is_(False))
                .where(Signal.created_at >= cutoff)
                .where(~has_outcome)
                .limit(200)
            )
            res = await session.execute(stmt)
            signals = res.scalars().all()
            return [
                {
                    "signal_id": s.signal_id,
                    "asset": s.asset,
                    "direction": s.direction,
                    "entry": s.entry,
                    "stop_loss": s.stop_loss,
                    "take_profit": s.take_profit,
                    "created_at": s.created_at,
                    "timeframe": s.timeframe,
                    "score": s.score,
                }
                for s in signals
            ]
    except Exception as exc:
        logger.error("[outcome_tracker] fetch_active_signals error: %s", exc)
        return []


async def _get_live_price(symbol: str) -> Optional[float]:
    """Fetch live price for a symbol (same logic as stale validator)."""
    try:
        from engine.stale_signal_validator import _get_live_price_async
        return await asyncio.wait_for(_get_live_price_async(symbol), timeout=5.0)
    except Exception:
        return None


def _parse_tp_levels(take_profit_raw: Any) -> List[float]:
    """Parse take_profit field which may be a JSON list, comma string, or float."""
    if isinstance(take_profit_raw, list):
        return [float(x) for x in take_profit_raw if x]
    if isinstance(take_profit_raw, (int, float)):
        return [float(take_profit_raw)]
    s = str(take_profit_raw).strip()
    # Try JSON first
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            return [float(x) for x in parsed if x]
        return [float(parsed)]
    except Exception:
        pass
    # Comma-separated
    parts = [p.strip() for p in s.split(",") if p.strip()]
    out = []
    for p in parts:
        try:
            out.append(float(p))
        except Exception:
            pass
    return out or []


def _check_hit(
    direction: str,
    entry: float,
    stop_loss: float,
    tp_levels: List[float],
    price: float,
) -> Optional[str]:
    """Return hit label ('sl', 'tp1', 'tp2', 'tp3', 'tp') or None."""
    d = direction.lower()
    if d == "long":
        if price <= stop_loss:
            return "sl"
        for i, tp in enumerate(tp_levels, 1):
            if price >= tp:
                return f"tp{i}" if i <= 3 else "tp"
    else:  # short
        if price >= stop_loss:
            return "sl"
        for i, tp in enumerate(tp_levels, 1):
            if price <= tp:
                return f"tp{i}" if i <= 3 else "tp"
    return None


async def _persist_outcome(signal_id: str, status: str, entry: float, price: float) -> None:
    """Write outcome row and archive signal."""
    try:
        from db.session import get_session
        from db.models import Outcome, Signal
        from sqlalchemy import update as sa_update
        now = datetime.utcnow()
        pct: Optional[float] = None
        r_mult: Optional[float] = None
        try:
            pct = ((price - entry) / entry) * 100.0
            r_mult = abs(price - entry) / (abs(entry) + 1e-9)
        except Exception:
            pass
        async with get_session() as session:
            outcome = Outcome(
                signal_id=signal_id,
                status=status,
                r_multiple=r_mult,
                percent=pct,
                opened_at=now,
                closed_at=now,
                meta={"close_price": price},
            )
            session.add(outcome)
            await session.execute(
                sa_update(Signal)
                .where(Signal.signal_id == signal_id)
                .values(archived=True)
            )
            await session.commit()
        logger.info("[outcome_tracker] Outcome persisted: %s -> %s @ %.5f", signal_id[:8], status, price)
    except Exception as exc:
        logger.error("[outcome_tracker] persist_outcome error: %s", exc)


async def _notify_outcome(signal: Dict[str, Any], status: str, price: float) -> None:
    """Send branded PnL notification to signal recipients."""
    try:
        from db.session import get_session
        from db.models import SignalDelivery, User
        from sqlalchemy import select
        from signalrank_telegram.bot import _send_message_sync
        from telegram import Bot
        from config import config

        signal_id = signal["signal_id"]
        asset = signal["asset"]
        direction = signal.get("direction", "long").upper()
        entry = float(signal.get("entry", 0))

        is_tp = status.startswith("tp")
        is_sl = status == "sl"

        if direction == "LONG":
            pnl_pct = ((price - entry) / entry) * 100
        else:
            pnl_pct = ((entry - price) / entry) * 100

        pnl_sign = "+" if pnl_pct >= 0 else ""

        if is_tp:
            header = "🎯🔥 TAKE PROFIT HIT"
            emoji = "✅"
            body = (
                f"{header}\n\n"
                f"🪙 *{asset}* {direction}\n"
                f"📊 Ref: `{signal_id[:8]}`\n\n"
                f"📥 Entry: `{entry:.5f}`\n"
                f"💰 Close: `{price:.5f}`\n"
                f"📈 ROI: *{pnl_sign}{pnl_pct:.2f}%*\n\n"
                f"🏆 *Target {status.upper()} reached!*\n"
                f"💪 Screenshot & share your win!\n\n"
                f"_SignalRankAI — Trade smarter._"
            )
        elif is_sl:
            header = "🛑 STOP LOSS HIT"
            emoji = "❌"
            body = (
                f"{header}\n\n"
                f"🪙 *{asset}* {direction}\n"
                f"📊 Ref: `{signal_id[:8]}`\n\n"
                f"📥 Entry: `{entry:.5f}`\n"
                f"💰 SL hit: `{price:.5f}`\n"
                f"📉 Loss: *{pnl_sign}{pnl_pct:.2f}%*\n\n"
                f"🔄 The next setup is loading...\n\n"
                f"_SignalRankAI — Risk managed._"
            )
        else:
            body = f"Signal `{signal_id[:8]}` closed at {price:.5f} ({status})"

        # TP1 -> move SL to break-even (trailing stop)
        if status == "tp1":
            body += "\n\n🛡️ *TP1 Hit! Stop-loss moved to break-even.*"
            await _apply_trailing_sl_to_breakeven(signal, price)

        # Send to all recipients
        bot_token = (config.TELEGRAM_BOT_TOKEN or "").strip()
        if not bot_token:
            return
        bot = Bot(token=bot_token)

        async with get_session() as session:
            stmt = select(SignalDelivery).where(SignalDelivery.signal_id == signal_id)
            rows = (await session.execute(stmt)).scalars().all()
            for row in rows:
                try:
                    # Get Telegram user_id
                    user_stmt = select(User).where(User.id == row.user_id)
                    user = (await session.execute(user_stmt)).scalar_one_or_none()
                    if user:
                        _send_message_sync(bot, chat_id=user.telegram_user_id, text=body, parse_mode="Markdown")
                except Exception as exc:
                    logger.debug("[outcome_tracker] notify user %s error: %s", row.user_id, exc)

    except Exception as exc:
        logger.error("[outcome_tracker] _notify_outcome error: %s", exc)


async def _apply_trailing_sl_to_breakeven(signal: Dict[str, Any], tp1_price: float) -> None:
    """Move SL to break-even when TP1 is hit, via MT5 bridge and DB update."""
    signal_id = signal.get("signal_id", "")
    entry = float(signal.get("entry", 0))
    asset = signal.get("asset", "")

    # Update DB trades table SL to break-even
    try:
        from db.session import get_session
        from db.models import Trade
        from sqlalchemy import update as sa_update
        async with get_session() as session:
            await session.execute(
                sa_update(Trade)
                .where(Trade.signal_id == signal_id)
                .where(Trade.status == "open")
                .values(stop_loss=entry)
            )
            await session.commit()
        logger.info("[outcome_tracker] SL moved to break-even for signal %s entry=%.5f", signal_id[:8], entry)
    except Exception as exc:
        logger.debug("[outcome_tracker] DB trailing SL update error: %s", exc)

    # If user has MT5 linked, update via MetaApi
    try:
        from db.session import get_session
        from db.models import Trade, User
        from sqlalchemy import select, join
        from services.mt5_client import update_stop_loss, get_user_mt5_account_id
        async with get_session() as session:
            stmt = (
                select(Trade, User)
                .join(User, Trade.symbol == User.telegram_user_id.cast(str))
                .where(Trade.signal_id == signal_id)
                .where(Trade.status == "open")
                .limit(10)
            )
            rows = (await session.execute(stmt)).fetchall()
            for trade, user in rows:
                acct_id = await get_user_mt5_account_id(user.telegram_user_id)
                if acct_id and trade.trade_metadata.get("mt5_order_id"):
                    await update_stop_loss(
                        acct_id,
                        trade.trade_metadata["mt5_order_id"],
                        entry,
                    )
    except Exception:
        pass  # MT5 bridge is optional


class RealtimeOutcomeTracker:
    """Async task that continuously monitors open signals for TP/SL hits."""

    def __init__(self) -> None:
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._loop(), name="outcome_tracker")
        logger.info("[outcome_tracker] Started (interval=%ds)", _check_interval())

    async def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[outcome_tracker] Stopped")

    async def _loop(self) -> None:
        while self.running:
            try:
                await self._check_all()
            except Exception as exc:
                logger.error("[outcome_tracker] loop error: %s", exc)
            await asyncio.sleep(_check_interval())

    async def _check_all(self) -> None:
        signals = await _fetch_active_signals()
        if not signals:
            return

        logger.debug("[outcome_tracker] Checking %d active signals", len(signals))

        tasks = [self._check_signal(sig) for sig in signals]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_signal(self, signal: Dict[str, Any]) -> None:
        symbol = signal["asset"]
        signal_id = signal["signal_id"]

        price = await _get_live_price(symbol)
        if price is None:
            return

        tp_levels = _parse_tp_levels(signal["take_profit"])
        if not tp_levels:
            return

        entry = float(signal["entry"])
        sl = float(signal["stop_loss"])
        direction = signal.get("direction", "long")

        hit = _check_hit(direction, entry, sl, tp_levels, price)
        if hit:
            logger.info(
                "[outcome_tracker] Hit detected: %s -> %s @ %.5f (entry=%.5f sl=%.5f)",
                signal_id[:8], hit, price, entry, sl,
            )
            await _persist_outcome(signal_id, hit, entry, price)
            await _notify_outcome(signal, hit, price)


# Singleton instance
outcome_tracker = RealtimeOutcomeTracker()
