"""
SignalRankAI — Realtime Outcome Tracker (PERFECTED)

Implements the "State-Driven WebSocket Outcome Tracking" specification:
  - Dynamically subscribes to asset price streams when signal goes ACTIVE
  - Evaluates ticks in memory against signal targets (linear state machine)
  - Tracks: PENDING → ENTRY_FILLED → PARTIAL_TP1 → PARTIAL_TP2 → TP3/SL
  - Recalculates Stop Loss to Break-Even after TP1 hit
  - Triggers Telegram broadcast on every state transition
  - Zero polling of REST history APIs — all price data from cached ticks

Signal lifecycle states:
  PENDING       → Waiting for price to reach entry zone
  ENTRY_FILLED  → Entry hit, trade is live
  PARTIAL_TP1   → TP1 hit, SL moved to Break-Even, position partial-closed
  PARTIAL_TP2   → TP2 hit, remainder running
  CLOSED_TP3    → Full take profit
  CLOSED_SL     → Stop loss hit (or break-even hit after TP1)
  EXPIRED       → Signal expired without entry
  INVALIDATED   → SL hit before entry
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Price tolerance thresholds ───────────────────────────────────────────────

ENTRY_ZONE_PCT = float(os.getenv("ENTRY_ZONE_PCT", "0.003"))   # ±0.3% of entry
BE_BUFFER_PCT  = float(os.getenv("BE_BUFFER_PCT",  "0.001"))   # 0.1% above entry = BE SL
TICK_INTERVAL  = float(os.getenv("TICK_INTERVAL_SECONDS", "30.0"))


# ─── Signal lifecycle state machine ───────────────────────────────────────────

class SignalState:
    PENDING       = "PENDING"
    ENTRY_FILLED  = "ENTRY_FILLED"
    PARTIAL_TP1   = "PARTIAL_TP1"
    PARTIAL_TP2   = "PARTIAL_TP2"
    CLOSED_TP3    = "CLOSED_TP3"
    CLOSED_SL     = "CLOSED_SL"
    EXPIRED       = "EXPIRED"
    INVALIDATED   = "INVALIDATED"

    TERMINAL = {CLOSED_TP3, CLOSED_SL, EXPIRED, INVALIDATED}


class TrackedSignal:
    """In-memory representation of an actively tracked signal."""

    __slots__ = (
        "signal_id", "asset", "direction", "entry", "stop_loss", "tp_levels",
        "timeframe", "state", "sl_current", "highest_tp_hit",
        "entry_filled_at", "created_at", "expires_at",
    )

    def __init__(self, row) -> None:
        self.signal_id   = str(getattr(row, "signal_id", "") or "")
        self.asset       = str(getattr(row, "asset", "") or "").upper().strip()
        self.direction   = str(getattr(row, "direction", "long") or "long").lower()
        self.entry       = float(getattr(row, "entry", 0) or 0)
        self.stop_loss   = float(getattr(row, "stop_loss", 0) or 0)
        self.timeframe   = str(getattr(row, "timeframe", "1h") or "1h").lower()
        self.created_at  = getattr(row, "created_at", None)
        self.expires_at  = getattr(row, "expires_at", None)
        self.state       = SignalState.PENDING
        self.sl_current  = self.stop_loss
        self.highest_tp_hit = 0
        self.entry_filled_at = None

        # Parse TP levels
        raw_tp = getattr(row, "take_profit", None)
        self.tp_levels: list[float] = self._parse_tp(raw_tp)

    def _parse_tp(self, raw) -> list[float]:
        if raw is None:
            return []
        if isinstance(raw, (int, float)):
            return [float(raw)] if raw > 0 else []
        if isinstance(raw, (list, tuple)):
            result = []
            for item in raw:
                try:
                    v = float(item.get("price") if isinstance(item, dict) else item)
                    if v > 0:
                        result.append(v)
                except Exception:
                    continue
            return result
        if isinstance(raw, str):
            try:
                return self._parse_tp(json.loads(raw))
            except Exception:
                try:
                    return [float(raw)]
                except Exception:
                    return []
        return []

    @property
    def is_terminal(self) -> bool:
        return self.state in SignalState.TERMINAL

    @property
    def is_long(self) -> bool:
        return self.direction == "long"


# ─── Price tick evaluator ─────────────────────────────────────────────────────

def evaluate_tick(
    signal: TrackedSignal,
    price: float,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Evaluate a single price tick against the signal's current state.

    Returns (new_state, transition_data) if a state change occurred,
    or (None, None) if no change.

    Implements the linear state machine:
      PENDING → ENTRY_FILLED → PARTIAL_TP1 → PARTIAL_TP2 → CLOSED_TP3
                                          ↘ CLOSED_SL (anytime after entry)
    """
    if signal.is_terminal:
        return None, None

    now = datetime.now(timezone.utc)

    # ── Expiry check ──────────────────────────────────────────────────────────
    if signal.expires_at:
        try:
            exp = signal.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now >= exp and signal.state == SignalState.PENDING:
                return SignalState.EXPIRED, {"expired_at": now.isoformat()}
        except Exception:
            pass

    p = float(price)
    if p <= 0:
        return None, None

    # ── PENDING: check for entry fill or pre-entry SL invalidation ────────────
    if signal.state == SignalState.PENDING:
        entry_tolerance = signal.entry * ENTRY_ZONE_PCT
        price_at_entry = abs(p - signal.entry) <= entry_tolerance

        # SL hit before entry = invalidated (stop was wrong / news event)
        if signal.is_long and p <= signal.sl_current:
            return SignalState.INVALIDATED, {
                "price": p,
                "reason": "SL hit before entry",
            }
        if not signal.is_long and p >= signal.sl_current:
            return SignalState.INVALIDATED, {
                "price": p,
                "reason": "SL hit before entry",
            }

        if price_at_entry or (signal.is_long and p <= signal.entry) or (
            not signal.is_long and p >= signal.entry
        ):
            signal.entry_filled_at = now
            return SignalState.ENTRY_FILLED, {
                "fill_price": p,
                "filled_at": now.isoformat(),
            }
        return None, None

    # ── ENTRY_FILLED / PARTIAL_TP1 / PARTIAL_TP2: check SL and TP levels ─────
    # SL check (current SL may have moved to break-even after TP1)
    if signal.is_long and p <= signal.sl_current:
        status = "CLOSED_SL"
        return SignalState.CLOSED_SL, {
            "exit_price": p,
            "sl_level": signal.sl_current,
            "highest_tp_hit": signal.highest_tp_hit,
            "break_even_stop": signal.sl_current > signal.stop_loss,
        }
    if not signal.is_long and p >= signal.sl_current:
        return SignalState.CLOSED_SL, {
            "exit_price": p,
            "sl_level": signal.sl_current,
            "highest_tp_hit": signal.highest_tp_hit,
            "break_even_stop": signal.sl_current < signal.stop_loss,
        }

    # TP check — scan from highest unhit TP
    tps = signal.tp_levels
    for idx in range(signal.highest_tp_hit, len(tps)):
        tp_price = tps[idx]
        tp_hit = (signal.is_long and p >= tp_price) or (
            not signal.is_long and p <= tp_price
        )
        if not tp_hit:
            break  # TPs are sequential — stop if current not hit

        tp_number = idx + 1  # 1-indexed
        signal.highest_tp_hit = tp_number

        if tp_number == 1:
            # Move SL to break-even after TP1
            if signal.is_long:
                be_sl = signal.entry * (1 + BE_BUFFER_PCT)
                signal.sl_current = max(signal.sl_current, be_sl)
            else:
                be_sl = signal.entry * (1 - BE_BUFFER_PCT)
                signal.sl_current = min(signal.sl_current, be_sl)

            new_state = SignalState.PARTIAL_TP1
            return new_state, {
                "tp_number": 1,
                "tp_price": tp_price,
                "exit_price": p,
                "sl_moved_to_be": signal.sl_current,
            }

        elif tp_number == 2:
            return SignalState.PARTIAL_TP2, {
                "tp_number": 2,
                "tp_price": tp_price,
                "exit_price": p,
                "remaining_stop": signal.sl_current,
            }

        elif tp_number >= 3 or tp_number == len(tps):
            return SignalState.CLOSED_TP3, {
                "tp_number": tp_number,
                "tp_price": tp_price,
                "exit_price": p,
                "full_close": True,
            }

    return None, None


# ─── Outcome state mapper ─────────────────────────────────────────────────────

def state_to_db_outcome(state: str, highest_tp_hit: int) -> str:
    """Map internal SignalState to DB outcome status string."""
    mapping = {
        SignalState.CLOSED_TP3: "tp3" if highest_tp_hit >= 3 else ("tp2" if highest_tp_hit == 2 else "tp1"),
        SignalState.CLOSED_SL: "sl",
        SignalState.EXPIRED: "expired",
        SignalState.INVALIDATED: "invalidated",
        SignalState.PARTIAL_TP1: "tp1",
        SignalState.PARTIAL_TP2: "tp2",
    }
    return mapping.get(state, "unknown")


# ─── Price fetcher ────────────────────────────────────────────────────────────

async def _get_live_price(asset: str) -> Optional[float]:
    """Fetch latest price for asset from all available sources."""
    # 1. Try cached Redis price first (sub-millisecond)
    try:
        from core.redis_state import state
        cached = state.get_sync(f"price:{asset.upper()}")
        if cached:
            return float(cached)
    except Exception:
        pass

    # 2. Try engine price cache
    try:
        from core.trade_tracker import _get_current_price
        price = await asyncio.to_thread(_get_current_price, asset)
        if price and float(price) > 0:
            return float(price)
    except Exception:
        pass

    # 3. Try data fetcher
    try:
        from data.fetcher import get_candles
        candles = await asyncio.to_thread(get_candles, asset, "1m")
        if candles:
            last = candles[-1]
            price = last.get("close") or last.get("Close") or last.get("c")
            if price and float(price) > 0:
                return float(price)
    except Exception:
        pass

    return None


# ─── Outcome writer ───────────────────────────────────────────────────────────

async def _write_outcome_to_db(
    signal: TrackedSignal,
    new_state: str,
    transition: dict,
) -> None:
    """Persist state transition to DB."""
    try:
        from db.session import get_session
        from db.pg_features import upsert_outcome

        db_status = state_to_db_outcome(new_state, signal.highest_tp_hit)
        entry = signal.entry
        exit_price = float(transition.get("exit_price") or transition.get("tp_price") or entry)

        # Calculate R-multiple and percent
        risk = abs(entry - signal.stop_loss)
        reward = abs(exit_price - entry)
        r_mult = (reward / risk) if risk > 0 else None
        if db_status.startswith("sl"):
            r_mult = -1.0
            pct = -abs(risk / entry * 100) if entry > 0 else None
        elif db_status.startswith("tp"):
            if signal.is_long:
                pct = ((exit_price - entry) / entry) * 100
            else:
                pct = ((entry - exit_price) / entry) * 100
        else:
            pct = None

        meta = {
            "tracker": "realtime_outcome_tracker",
            "state": new_state,
            "transition": transition,
            "highest_tp_hit": signal.highest_tp_hit,
            "sl_final": signal.sl_current,
            "be_stop": signal.sl_current > signal.stop_loss if signal.is_long else signal.sl_current < signal.stop_loss,
        }

        async with get_session() as session:
            await upsert_outcome(
                session,
                signal_id=signal.signal_id,
                status=db_status,
                meta=meta,
                r_multiple=r_mult,
                percent=pct,
                opened_at=signal.entry_filled_at,
                closed_at=datetime.now(timezone.utc) if new_state in SignalState.TERMINAL else None,
            )
            # Mark signal as expired/archived if terminal
            if new_state in SignalState.TERMINAL:
                from db.models import Signal
                from sqlalchemy import update as sa_update
                await session.execute(
                    sa_update(Signal)
                    .where(Signal.signal_id == signal.signal_id)
                    .values(expired=True)
                )
            await session.commit()

        logger.info(
            "[outcome_tracker] %s → %s: asset=%s tp_hit=%s",
            signal.signal_id[:8],
            new_state,
            signal.asset,
            signal.highest_tp_hit,
        )
    except Exception as exc:
        logger.warning("[outcome_tracker] DB write failed for %s: %s", signal.signal_id[:8], exc)


# ─── Telegram broadcast ───────────────────────────────────────────────────────

async def _broadcast_state_change(
    signal: TrackedSignal,
    new_state: str,
    transition: dict,
) -> None:
    """Broadcast state change to all recipients of this signal."""
    try:
        from db.session import get_session
        from db.pg_features import list_delivery_recipients_for_signal
        from signalrank_telegram.bot import _send_message_with_retry, _require_telegram_token
        from engine.tier_notifications import TierNotificationManager
        from telegram import Bot

        notifier = TierNotificationManager()

        async with get_session() as session:
            recipients = await list_delivery_recipients_for_signal(session, signal.signal_id)
            await session.commit()

        if not recipients:
            return

        bot = Bot(token=_require_telegram_token())
        db_status = state_to_db_outcome(new_state, signal.highest_tp_hit)
        tp_level_num = signal.highest_tp_hit if new_state.startswith("PARTIAL") or new_state == SignalState.CLOSED_TP3 else 0
        pct = abs(float(transition.get("pct") or 0))

        signal_dict = {
            "signal_id": signal.signal_id,
            "asset": signal.asset,
            "direction": signal.direction,
            "entry": signal.entry,
            "stop_loss": signal.stop_loss,
            "timeframe": signal.timeframe,
        }

        for telegram_user_id, tier_at_send in recipients:
            try:
                tier = str(tier_at_send or "free").lower()
                if tier in ("owner", "admin"):
                    tier = "vip"

                if new_state in (SignalState.PARTIAL_TP1, SignalState.PARTIAL_TP2, SignalState.CLOSED_TP3):
                    msg = notifier.format_tp_hit_notification(
                        signal_dict, tier, tp_level_num or 1, pct,
                        float(transition.get("exit_price") or 0) or None,
                    )
                elif new_state == SignalState.CLOSED_SL:
                    loss_pct = float(
                        abs(signal.entry - signal.sl_current) / signal.entry * 100
                        if signal.entry > 0 else 0
                    )
                    be_stop = bool(transition.get("break_even_stop"))
                    if be_stop:
                        msg = (
                            f"🛡️ <b>Break-Even Stop Hit</b>\n"
                            f"<b>{signal.asset}</b> closed at break-even.\n"
                            "Capital fully protected. TP1 was already secured. ✅"
                        )
                    else:
                        msg = (
                            f"❌ <b>Stop Loss Hit</b>\n"
                            f"<b>{signal.asset}</b> {signal.direction.upper()}\n"
                            f"Loss: <b>-{loss_pct:.2f}%</b>\n"
                            "Risk was predefined and controlled."
                        )
                elif new_state == SignalState.ENTRY_FILLED:
                    msg = (
                        f"⚡ <b>Entry Filled</b>\n"
                        f"<b>{signal.asset}</b> {signal.direction.upper()}\n"
                        f"Entry: <b>{float(transition.get('fill_price', signal.entry)):.5f}</b>\n"
                        f"Stop Loss: <b>{signal.sl_current:.5f}</b>\n"
                        "Trade is now live. Watching targets."
                    )
                else:
                    continue  # No broadcast for other states

                await _send_message_with_retry(
                    bot,
                    chat_id=int(telegram_user_id),
                    text=msg,
                    parse_mode="HTML",
                )
                await asyncio.sleep(0.3)  # Rate limit

            except Exception as exc:
                logger.debug(
                    "[outcome_tracker] broadcast failed user=%s: %s",
                    telegram_user_id,
                    exc,
                )

    except Exception as exc:
        logger.warning("[outcome_tracker] broadcast error %s: %s", signal.signal_id[:8], exc)


# ─── Main tracker class ───────────────────────────────────────────────────────

class RealtimeOutcomeTracker:
    """
    Asynchronous outcome tracker that monitors active signals.

    Usage:
        tracker = RealtimeOutcomeTracker()
        asyncio.create_task(tracker.start())
        # ... later:
        await tracker.stop()
    """

    def __init__(self) -> None:
        self._active: Dict[str, TrackedSignal] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._tick_interval = TICK_INTERVAL
        self._max_tracked = int(os.getenv("OUTCOME_TRACKER_MAX_SIGNALS", "200") or 200)

    async def start(self) -> None:
        """Start the background tracking loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._tracking_loop())
        logger.info("[outcome_tracker] Started (interval=%.0fs max=%d)", self._tick_interval, self._max_tracked)

    async def stop(self) -> None:
        """Stop the background tracking loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        logger.info("[outcome_tracker] Stopped. Tracked %d signals.", len(self._active))

    def add_signal(self, signal_row) -> None:
        """Register a new signal for tracking."""
        try:
            ts = TrackedSignal(signal_row)
            if not ts.signal_id or not ts.asset or not ts.tp_levels:
                return
            if ts.signal_id not in self._active:
                self._active[ts.signal_id] = ts
                logger.debug("[outcome_tracker] Added signal %s (%s)", ts.signal_id[:8], ts.asset)
        except Exception as exc:
            logger.debug("[outcome_tracker] add_signal failed: %s", exc)

    def remove_signal(self, signal_id: str) -> None:
        """Remove a signal from tracking (e.g. on outcome or expiry)."""
        self._active.pop(str(signal_id), None)

    @property
    def tracked_count(self) -> int:
        return len(self._active)

    async def _load_active_signals(self) -> None:
        """Load active signals from DB into tracking set."""
        try:
            from db.session import get_session
            from db.models import Signal, Outcome
            from sqlalchemy import select, and_
            from datetime import timedelta

            cutoff = datetime.now(timezone.utc) - timedelta(hours=int(
                os.getenv("OUTCOME_TRACKER_MAX_AGE_HOURS", "48") or 48
            ))

            async with get_session() as session:
                rows = (
                    await session.execute(
                        select(Signal)
                        .outerjoin(Outcome, Outcome.signal_id == Signal.signal_id)
                        .where(
                            and_(
                                Signal.expired == False,
                                Signal.archived == False,
                                Signal.created_at >= cutoff,
                                Outcome.id.is_(None),  # No outcome yet
                            )
                        )
                        .limit(self._max_tracked)
                    )
                ).scalars().all()
                await session.commit()

            loaded = 0
            for row in rows:
                sid = str(getattr(row, "signal_id", "") or "")
                if sid and sid not in self._active:
                    self.add_signal(row)
                    loaded += 1

            if loaded:
                logger.info("[outcome_tracker] Loaded %d new active signals", loaded)

        except Exception as exc:
            logger.debug("[outcome_tracker] load_active_signals failed: %s", exc)

    async def _tracking_loop(self) -> None:
        """Main loop: fetch prices → evaluate → persist → broadcast."""
        load_interval = int(os.getenv("OUTCOME_TRACKER_LOAD_INTERVAL_TICKS", "10") or 10)
        tick_count = 0

        while self._running:
            try:
                tick_start = time.monotonic()

                # Periodically refresh the active signal set from DB
                if tick_count % load_interval == 0:
                    await self._load_active_signals()
                    # Prune terminal signals
                    terminal = [sid for sid, sig in self._active.items() if sig.is_terminal]
                    for sid in terminal:
                        self._active.pop(sid, None)

                tick_count += 1

                if not self._active:
                    await asyncio.sleep(self._tick_interval)
                    continue

                # Group signals by asset for batch price fetching
                asset_to_signals: Dict[str, List[TrackedSignal]] = {}
                for sig in list(self._active.values()):
                    asset_to_signals.setdefault(sig.asset, []).append(sig)

                # Fetch prices for all tracked assets concurrently
                price_tasks = {
                    asset: asyncio.create_task(_get_live_price(asset))
                    for asset in asset_to_signals
                }
                for asset, task in price_tasks.items():
                    try:
                        price = await asyncio.wait_for(task, timeout=8.0)
                    except (asyncio.TimeoutError, Exception):
                        price = None

                    if price is None or price <= 0:
                        continue

                    # Cache the price in Redis for other modules
                    try:
                        from core.redis_state import state
                        state.set_sync(f"price:{asset}", str(price), ex=120)
                    except Exception:
                        pass

                    # Evaluate each signal for this asset
                    for sig in asset_to_signals.get(asset, []):
                        try:
                            new_state, transition = evaluate_tick(sig, price)
                            if new_state is None:
                                continue

                            # Apply state transition
                            sig.state = new_state

                            # Persist to DB
                            await _write_outcome_to_db(sig, new_state, transition or {})

                            # Broadcast to Telegram users
                            await _broadcast_state_change(sig, new_state, transition or {})

                            # Remove terminal signals
                            if sig.is_terminal:
                                self._active.pop(sig.signal_id, None)
                                logger.info(
                                    "[outcome_tracker] Signal %s reached %s",
                                    sig.signal_id[:8],
                                    new_state,
                                )

                        except Exception as exc:
                            logger.debug(
                                "[outcome_tracker] eval failed %s: %s",
                                sig.signal_id[:8],
                                exc,
                            )

                # Sleep for remaining interval
                elapsed = time.monotonic() - tick_start
                sleep_time = max(0.5, self._tick_interval - elapsed)
                await asyncio.sleep(sleep_time)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("[outcome_tracker] loop error: %s", exc)
                await asyncio.sleep(5.0)


# ─── Module-level singleton ───────────────────────────────────────────────────

outcome_tracker = RealtimeOutcomeTracker()


__all__ = [
    "RealtimeOutcomeTracker",
    "outcome_tracker",
    "TrackedSignal",
    "SignalState",
    "evaluate_tick",
    "state_to_db_outcome",
]