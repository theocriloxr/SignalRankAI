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
    ACTIVE_SIGNAL_LOOKBACK_HOURS    - How far back to look for open signals (default: 720)
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
        return int(os.getenv("ACTIVE_SIGNAL_LOOKBACK_HOURS", "720"))
    except Exception:
        return 720


async def _fetch_active_signals() -> List[Dict[str, Any]]:
    """Return all unresolved signals from DB created within lookback window."""
    try:
        from db.session import get_session
        from db.models import Signal, Outcome
        from sqlalchemy import select, or_
        cutoff = datetime.utcnow() - timedelta(hours=_lookback_hours())
        async with get_session() as session:
            stmt = (
                select(Signal, Outcome)
                .outerjoin(Outcome, Outcome.signal_id == Signal.signal_id)
                .where(Signal.archived.is_(False))
                .where(Signal.created_at >= cutoff)
                .where(
                    or_(
                        Outcome.id.is_(None),
                        Outcome.status.in_(["tp1", "tp2"]),
                    )
                )
                .limit(200)
            )
            res = await session.execute(stmt)
            rows = res.all()
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
                    "ml_probability": getattr(s, "ml_probability", None),
                    "prev_outcome_status": str(getattr(o, "status", "") or "").lower() if o is not None else None,
                    "prev_outcome_meta": dict(getattr(o, "meta", {}) or {}) if o is not None else {},
                }
                for s, o in rows
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
        max_idx = 0
        for i, tp in enumerate(tp_levels, 1):
            if price >= tp:
                max_idx = i
        if max_idx > 0:
            return f"tp{max_idx}" if max_idx <= 3 else "tp"
    else:  # short
        if price >= stop_loss:
            return "sl"
        max_idx = 0
        for i, tp in enumerate(tp_levels, 1):
            if price <= tp:
                max_idx = i
        if max_idx > 0:
            return f"tp{max_idx}" if max_idx <= 3 else "tp"
    return None


def _halfway_to_tp1_reached(direction: str, entry: float, tp1: float, price: float) -> bool:
    """True when price reaches 50% of path to TP1 but TP1 is not yet hit."""
    try:
        d = str(direction or "long").lower()
        midpoint = float(entry) + ((float(tp1) - float(entry)) * 0.5)
        if d == "short":
            return float(price) <= midpoint and float(price) > float(tp1)
        return float(price) >= midpoint and float(price) < float(tp1)
    except Exception:
        return False


def _risk_free_cache_key(signal_id: str) -> str:
    return f"risk_free_half_tp1:{str(signal_id)}"


def _tp_progress_cache_key(signal_id: str) -> str:
    return f"tp_progress:{str(signal_id)}"


def _retrace_warn_cache_key(signal_id: str) -> str:
    return f"tp_retrace_warned:{str(signal_id)}"


def _mark_risk_free_triggered(signal_id: str, ttl_seconds: int = 7 * 24 * 3600) -> bool:
    """Returns True only once per signal for the configured TTL window."""
    try:
        from core.redis_state import state
        key = _risk_free_cache_key(signal_id)
        if state.get_sync(key):
            return False
        state.set_sync(key, "1", ex=max(3600, int(ttl_seconds)))
        return True
    except Exception:
        # If Redis is unavailable, allow trigger (idempotency is still mostly safe).
        return True


def _get_tp_progress(signal: Dict[str, Any]) -> int:
    signal_id = str(signal.get("signal_id") or "")
    if not signal_id:
        return 0
    try:
        from core.redis_state import state
        raw = state.get_sync(_tp_progress_cache_key(signal_id))
        cached = int(raw or 0)
    except Exception:
        cached = 0
    try:
        meta = dict(signal.get("prev_outcome_meta") or {})
        db_idx = int(meta.get("tp_hit_index") or 0)
    except Exception:
        db_idx = 0
    return max(cached, db_idx)


def _set_tp_progress(signal_id: str, idx: int, ttl_seconds: int = 10 * 24 * 3600) -> None:
    try:
        from core.redis_state import state
        state.set_sync(_tp_progress_cache_key(signal_id), str(max(0, int(idx))), ex=max(3600, int(ttl_seconds)))
    except Exception:
        pass


def _mark_retrace_warned(signal_id: str, ttl_seconds: int = 10 * 24 * 3600) -> bool:
    try:
        from core.redis_state import state
        key = _retrace_warn_cache_key(signal_id)
        if state.get_sync(key):
            return False
        state.set_sync(key, "1", ex=max(3600, int(ttl_seconds)))
        return True
    except Exception:
        return True


def _retrace_warning_triggered(direction: str, sl: float, best_tp_price: float, price: float, zone_pct: float = 0.20) -> bool:
    """True when price retraces into SL danger zone after at least one TP hit.

    zone_pct=0.20 means: notify when price is within 20% of distance to SL from
    the best TP that was reached.
    """
    try:
        z = min(0.9, max(0.01, float(zone_pct)))
        d = str(direction or "long").lower()
        if d == "short":
            # Example: TP=62, SL=100 -> threshold=92.4 (about 90)
            threshold = float(sl) - (float(sl) - float(best_tp_price)) * z
            return float(price) >= threshold
        threshold = float(sl) + (float(best_tp_price) - float(sl)) * z
        return float(price) <= threshold
    except Exception:
        return False
    except Exception:
        # If Redis is unavailable, allow trigger (idempotency is still mostly safe).
        return True


async def _persist_outcome(signal_id: str, status: str, entry: float, price: float) -> None:
    """Upsert outcome row. Archive only on terminal statuses."""
    try:
        from db.session import get_session
        from db.models import Signal
        from db.pg_features import upsert_outcome
        from sqlalchemy import update as sa_update
        now = datetime.utcnow()
        pct: Optional[float] = None
        r_mult: Optional[float] = None
        try:
            pct = ((price - entry) / entry) * 100.0
            r_mult = abs(price - entry) / (abs(entry) + 1e-9)
        except Exception:
            pass

        status_l = str(status or "").lower()
        terminal = status_l in {"sl", "tp3", "tp"}

        async with get_session() as session:
            await upsert_outcome(
                session,
                str(signal_id),
                status_l,
                r_multiple=r_mult,
                percent=pct,
                closed_at=now,
                meta={"close_price": float(price)},
            )
            if terminal:
                await session.execute(
                    sa_update(Signal)
                    .where(Signal.signal_id == signal_id)
                    .values(archived=True)
                )
            await session.commit()
        logger.info("[outcome_tracker] Outcome persisted: %s -> %s @ %.5f", signal_id[:8], status_l, price)
    except Exception as exc:
        logger.error("[outcome_tracker] persist_outcome error: %s", exc)


async def _notify_retrace_warning(signal: Dict[str, Any], price: float, best_tp_idx: int) -> None:
    """Notify recipients that price retraced dangerously near SL after TP progress."""
    try:
        from db.session import get_session
        from db.models import SignalDelivery, User
        from sqlalchemy import select
        from signalrank_telegram.bot import _send_message_sync
        from telegram import Bot
        from config import config

        signal_id = str(signal.get("signal_id") or "")
        if not signal_id:
            return
        asset = str(signal.get("asset") or "")
        direction = str(signal.get("direction") or "long").upper()
        sl = float(signal.get("stop_loss") or 0)

        txt = (
            "⚠️ <b>TP Retrace Warning</b>\n\n"
            f"🪙 <b>{asset}</b> {direction}\n"
            f"📊 Ref: <code>{signal_id[:8]}</code>\n"
            f"✅ Highest TP reached: <b>TP{int(best_tp_idx)}</b>\n"
            f"📉 Price retraced close to SL danger zone\n"
            f"💰 Current: <b>{float(price):.5f}</b> | SL: <b>{float(sl):.5f}</b>"
        )

        bot_token = (config.TELEGRAM_BOT_TOKEN or "").strip()
        if not bot_token:
            return
        bot = Bot(token=bot_token)

        async with get_session() as session:
            rows = (
                await session.execute(
                    select(SignalDelivery, User)
                    .join(User, User.id == SignalDelivery.user_id)
                    .where(SignalDelivery.signal_id == signal_id)
                )
            ).all()
            for _delivery, user in rows:
                try:
                    _send_message_sync(bot, chat_id=int(user.telegram_user_id), text=txt, parse_mode="HTML")
                except Exception as exc:
                    logger.debug("[outcome_tracker] retrace warn user notify failed: %s", exc)
    except Exception as exc:
        logger.debug("[outcome_tracker] retrace warning send failed: %s", exc)


def _h(text: str) -> str:
    """Escape text for Telegram HTML parse_mode."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _fmt_price(price: float) -> str:
    """Format price with appropriate decimal places."""
    if price >= 1000:
        return f"{price:,.2f}"
    if price >= 1:
        return f"{price:.5f}"
    return f"{price:.8f}"


def _build_outcome_message(
    signal_id: str,
    asset: str,
    direction: str,
    entry: float,
    price: float,
    status: str,
    pnl_pct: float,
    tier_at_send: str,
) -> str:
    """Build a tier-appropriate HTML outcome message.

    Free users get a stripped-down version (signal ref + outcome label only).
    Premium/VIP users get the full PnL breakdown.
    """
    pnl_sign = "+" if pnl_pct >= 0 else ""
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    status_u = status.upper()
    is_tp = status.startswith("tp")
    is_sl = status == "sl"
    tier = str(tier_at_send or "free").lower()
    is_free = tier == "free"

    ref_short = _h(signal_id[:8])
    asset_h = _h(asset)
    dir_h = _h(direction)

    if is_tp:
        if is_free:
            # Free: proof of result — minimal info to build trust
            return (
                f"🎯 <b>TAKE PROFIT HIT</b>\n\n"
                f"🪙 <b>{asset_h}</b> {dir_h}\n"
                f"📊 Ref: <code>{ref_short}</code>\n"
                f"🏆 {status_u} reached!\n"
                f"🕐 {_h(now_str)}\n\n"
                f"<i>Upgrade to Premium for full PnL details.</i>"
            )
        # Premium / VIP full message
        tp1_line = "\n🛡️ <b>Stop-loss moved to break-even.</b>" if status == "tp1" else ""
        return (
            f"🎯🔥 <b>TAKE PROFIT HIT</b>\n\n"
            f"🪙 <b>{asset_h}</b> {dir_h}\n"
            f"📊 Ref: <code>{ref_short}</code>\n\n"
            f"📥 Entry: <code>{_h(_fmt_price(entry))}</code>\n"
            f"💰 Close: <code>{_h(_fmt_price(price))}</code>\n"
            f"📈 ROI: <b>{_h(pnl_sign + f'{pnl_pct:.2f}%')}</b>\n\n"
            f"🏆 <b>{status_u} reached!</b>{tp1_line}\n"
            f"💪 Screenshot &amp; share your win!\n"
            f"🕐 {_h(now_str)}\n\n"
            f"<i>SignalRankAI — Trade smarter.</i>"
        )

    if is_sl:
        if is_free:
            return (
                f"🛑 <b>STOP LOSS HIT</b>\n\n"
                f"🪙 <b>{asset_h}</b> {dir_h}\n"
                f"📊 Ref: <code>{ref_short}</code>\n"
                f"🕐 {_h(now_str)}\n\n"
                f"<i>Upgrade to Premium for full details &amp; next signals.</i>"
            )
        return (
            f"🛑 <b>STOP LOSS HIT</b>\n\n"
            f"🪙 <b>{asset_h}</b> {dir_h}\n"
            f"📊 Ref: <code>{ref_short}</code>\n\n"
            f"📥 Entry: <code>{_h(_fmt_price(entry))}</code>\n"
            f"💰 SL hit: <code>{_h(_fmt_price(price))}</code>\n"
            f"📉 Loss: <b>{_h(pnl_sign + f'{pnl_pct:.2f}%')}</b>\n\n"
            f"🔄 The next setup is loading...\n"
            f"🕐 {_h(now_str)}\n\n"
            f"<i>SignalRankAI — Risk managed.</i>"
        )

    # Generic closed status
    return (
        f"📌 <b>Signal Closed</b>\n\n"
        f"🪙 <b>{asset_h}</b> | Ref: <code>{ref_short}</code>\n"
        f"Status: <b>{_h(status_u)}</b> @ <code>{_h(_fmt_price(price))}</code>\n"
        f"🕐 {_h(now_str)}"
    )


async def _notify_outcome(signal: Dict[str, Any], status: str, price: float) -> None:
    """Send branded PnL notification to signal recipients (only users who got this signal)."""
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

        if direction == "LONG":
            pnl_pct = ((price - entry) / entry) * 100
        else:
            pnl_pct = ((entry - price) / entry) * 100

        # TP1 → move SL to break-even (trailing stop), done before sending messages
        if status == "tp1":
            await _apply_trailing_sl_to_breakeven(signal, price)

        # Send to all recipients of this signal only
        bot_token = (config.TELEGRAM_BOT_TOKEN or "").strip()
        if not bot_token:
            return
        bot = Bot(token=bot_token)

        async with get_session() as session:
            # Join with User so we get tier_at_send for each recipient
            stmt = (
                select(SignalDelivery, User)
                .join(User, User.id == SignalDelivery.user_id)
                .where(SignalDelivery.signal_id == signal_id)
            )
            rows = (await session.execute(stmt)).all()
            for row_sd, row_user in rows:
                try:
                    tier_at_send = str(getattr(row_sd, "tier_at_send", "free") or "free").lower()
                    body = _build_outcome_message(
                        signal_id=signal_id,
                        asset=asset,
                        direction=direction,
                        entry=entry,
                        price=price,
                        status=status,
                        pnl_pct=pnl_pct,
                        tier_at_send=tier_at_send,
                    )
                    _send_message_sync(
                        bot,
                        chat_id=row_user.telegram_user_id,
                        text=body,
                        parse_mode="HTML",
                    )
                except Exception as exc:
                    logger.debug("[outcome_tracker] notify user %s error: %s", getattr(row_sd, "user_id", "?"), exc)

    except Exception as exc:
        logger.error("[outcome_tracker] _notify_outcome error: %s", exc)


async def _notify_risk_free_update(signal: Dict[str, Any], price: float) -> None:
    """Broadcast one-time risk-free update when halfway to TP1 is reached."""
    try:
        from db.session import get_session
        from db.models import SignalDelivery, User
        from sqlalchemy import select
        from signalrank_telegram.bot import _send_message_sync
        from telegram import Bot
        from config import config

        signal_id = str(signal.get("signal_id") or "")
        if not signal_id:
            return

        entry = float(signal.get("entry", 0) or 0)
        asset = str(signal.get("asset", "") or "")
        timeframe = str(signal.get("timeframe", "") or "")
        direction = str(signal.get("direction", "long") or "long").upper()

        if entry > 0:
            if direction == "SHORT":
                move_pct = ((entry - float(price)) / entry) * 100.0
            else:
                move_pct = ((float(price) - entry) / entry) * 100.0
        else:
            move_pct = 0.0

        text = (
            "🛡️ <b>Risk-Free Update</b>\n\n"
            f"🪙 <b>{asset}</b> {direction} ({timeframe})\n"
            f"📊 Ref: <code>{signal_id[:8]}</code>\n"
            f"💹 Price moved <b>{move_pct:+.2f}%</b> toward TP1\n\n"
            "✅ 50% to TP1 reached — stop-loss moved to breakeven (risk-free)."
        )

        bot_token = (config.TELEGRAM_BOT_TOKEN or "").strip()
        if not bot_token:
            return
        bot = Bot(token=bot_token)

        async with get_session() as session:
            rows = (
                await session.execute(
                    select(SignalDelivery, User)
                    .join(User, User.id == SignalDelivery.user_id)
                    .where(SignalDelivery.signal_id == signal_id)
                )
            ).all()
            for _delivery, user in rows:
                try:
                    _send_message_sync(bot, chat_id=int(user.telegram_user_id), text=text, parse_mode="HTML")
                except Exception as exc:
                    logger.debug("[outcome_tracker] risk-free notify user=%s error: %s", getattr(user, "id", "?"), exc)
    except Exception as exc:
        logger.debug("[outcome_tracker] risk-free notify failed: %s", exc)


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

        # Track which users had outcomes updated
        updated_users = set()

        async def wrapped_check_signal(sig):
            try:
                await self._check_signal(sig)
                # Find all users who received this signal
                from db.session import get_session
                from db.models import SignalDelivery
                from sqlalchemy import select
                async with get_session() as session:
                    rows = await session.execute(select(SignalDelivery.user_id).where(SignalDelivery.signal_id == sig["signal_id"]))
                    for (user_id,) in rows.all():
                        updated_users.add(user_id)
            except Exception as exc:
                logger.warning(f"[outcome_tracker] Error updating user performance for signal {sig.get('signal_id')}: {exc}")

        tasks = [wrapped_check_signal(sig) for sig in signals]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Retrain ML after all outcomes processed
        try:
            logger.info("[outcome_tracker] Triggering ML retraining after outcome tracking...")
            import sys
            import asyncio as _asyncio
            sys.path.append("ml")
            from ml import train_model as _train_model
            await _train_model.main()
            logger.info("[outcome_tracker] ML retraining complete.")
        except Exception as exc:
            logger.error(f"[outcome_tracker] ML retraining failed: {exc}")

        # Update user performance for all affected users
        try:
            from db.session import get_session
            from db.pg_features import get_user_performance_30d
            async with get_session() as session:
                for user_id in updated_users:
                    try:
                        perf = await get_user_performance_30d(session, int(user_id))
                        logger.info(f"[outcome_tracker] Updated performance for user {user_id}: {perf}")
                    except Exception as exc:
                        logger.warning(f"[outcome_tracker] Failed to update performance for user {user_id}: {exc}")
        except Exception as exc:
            logger.error(f"[outcome_tracker] Bulk user performance update failed: {exc}")

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
        prev_tp = int(_get_tp_progress(signal) or 0)

        # Normalize TP ladder before any checks.
        if str(direction).lower() == "short":
            tp_levels = sorted(tp_levels, reverse=True)
        else:
            tp_levels = sorted(tp_levels)

        # Explicit risk-free trigger at 50% to TP1 (one-time per signal).
        try:
            tp1 = float(tp_levels[0])
            if _halfway_to_tp1_reached(direction, entry, tp1, float(price)):
                if _mark_risk_free_triggered(signal_id):
                    await _apply_trailing_sl_to_breakeven(signal, float(price))
                    await _notify_risk_free_update(signal, float(price))
                    logger.info(
                        "[outcome_tracker] Risk-free trigger: %s halfway_to_tp1 price=%.5f entry=%.5f tp1=%.5f",
                        signal_id[:8], float(price), float(entry), float(tp1),
                    )
        except Exception as exc:
            logger.debug("[outcome_tracker] risk-free trigger check failed for %s: %s", signal_id[:8], exc)

        # Retrace warning after TP progress: notify once when price is within
        # 20% of SL distance from best TP reached (example short: 62->100 warns ~92.4).
        try:
            if prev_tp >= 1:
                best_tp_price = float(tp_levels[min(prev_tp - 1, len(tp_levels) - 1)])
                zone_pct = float(os.getenv("TP_RETRACE_SL_ZONE_PCT", "0.20") or 0.20)
                ml_prob = signal.get("ml_probability")
                ml_gate = float(os.getenv("TP_RETRACE_MIN_ML_CONF", "0.55") or 0.55)
                ml_allows_warning = (ml_prob is None) or (float(ml_prob) <= ml_gate)
                if ml_allows_warning and _retrace_warning_triggered(direction, sl, best_tp_price, float(price), zone_pct=zone_pct):
                    if _mark_retrace_warned(signal_id):
                        await _notify_retrace_warning(signal, float(price), prev_tp)
                        logger.info(
                            "[outcome_tracker] Retrace warning: %s tp=%d price=%.5f sl=%.5f",
                            signal_id[:8], prev_tp, float(price), float(sl),
                        )
        except Exception as exc:
            logger.debug("[outcome_tracker] retrace warning check failed for %s: %s", signal_id[:8], exc)

        hit = _check_hit(direction, entry, sl, tp_levels, price)
        if hit:
            hit_l = str(hit).lower()
            hit_tp_idx = 0
            if hit_l.startswith("tp") and hit_l != "tp":
                try:
                    hit_tp_idx = int(hit_l.replace("tp", "") or 0)
                except Exception:
                    hit_tp_idx = 0

            # Notify only on forward TP progression.
            if hit_tp_idx > 0 and hit_tp_idx <= prev_tp:
                return

            logger.info(
                "[outcome_tracker] Hit detected: %s -> %s @ %.5f (entry=%.5f sl=%.5f)",
                signal_id[:8], hit_l, price, entry, sl,
            )
            if hit_tp_idx > 0:
                _set_tp_progress(signal_id, hit_tp_idx)
            await _persist_outcome(signal_id, hit_l, entry, price)
            await _notify_outcome(signal, hit_l, price)


# Singleton instance
outcome_tracker = RealtimeOutcomeTracker()
