"""Guarded Smart DCA for delivered VIP signals.

DCA is an optional execution feature.  It is disabled by default, uses the
canonical MT5SignalRouter/ExecutionGate, and never guesses users, balances,
quotes, or lot sizes.  State is isolated by user and signal so DCA1 and DCA2
progress monotonically and survive restarts through Redis acceleration plus
broker idempotency.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.env import env_bool, env_int
from core.redis_state import state
from data.provider_types import LivePriceQuote
from db.models import Signal, SignalDelivery, User
from db.session import get_session
from sqlalchemy import select
from utils.timeutils import now_utc_naive

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DCAProfile:
    name: str
    scale_weights: tuple[float, float, float]
    dca_triggers: tuple[float, float]
    breakeven_pct: float
    trail_start_pct: float
    trail_distance_pct: float


PROFILES: dict[str, DCAProfile] = {
    "conservative": DCAProfile(
        name="Conservative",
        scale_weights=(0.40, 0.30, 0.30),
        dca_triggers=(-2.5, -5.0),
        breakeven_pct=0.75,
        trail_start_pct=1.5,
        trail_distance_pct=1.0,
    ),
    "balanced": DCAProfile(
        name="Balanced",
        scale_weights=(0.33, 0.33, 0.34),
        dca_triggers=(-3.0, -6.0),
        breakeven_pct=1.0,
        trail_start_pct=2.0,
        trail_distance_pct=1.5,
    ),
    "aggressive": DCAProfile(
        name="Aggressive",
        scale_weights=(0.20, 0.30, 0.50),
        dca_triggers=(-4.0, -8.0),
        breakeven_pct=1.5,
        trail_start_pct=3.0,
        trail_distance_pct=2.0,
    ),
}


def _normalise_direction(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"long", "buy"}:
        return "long"
    if raw in {"short", "sell"}:
        return "short"
    return ""


def _parse_targets(value: Any) -> list[float]:
    from services.mt5_signal_router import MT5SignalRouter

    return MT5SignalRouter._parse_take_profit(value)


class SmartDCA:
    """Per-user DCA manager that delegates every order to the canonical gate."""

    def __init__(self, profile_name: str = "balanced", *, redis_state=state) -> None:
        self.profile = PROFILES.get(str(profile_name).lower(), PROFILES["balanced"])
        self._redis = redis_state

    @staticmethod
    def enabled() -> bool:
        return env_bool("SMART_DCA_ENABLED", False)

    @staticmethod
    def _state_key(user_telegram_id: int, signal_id: str) -> str:
        return f"smart_dca:{int(user_telegram_id)}:{str(signal_id)}"

    async def _load_state(self, user_telegram_id: int, signal_id: str) -> dict[str, Any]:
        raw = await self._redis.cache_get(self._state_key(user_telegram_id, signal_id))
        if not raw:
            return {}
        if isinstance(raw, dict):
            return dict(raw)
        try:
            parsed = json.loads(str(raw))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    async def _save_state(
        self,
        user_telegram_id: int,
        signal_id: str,
        payload: dict[str, Any],
    ) -> None:
        ttl = env_int("SMART_DCA_STATE_TTL_SECONDS", 7 * 24 * 3600, minimum=3600)
        await self._redis.cache_set(
            self._state_key(user_telegram_id, signal_id),
            json.dumps(payload, separators=(",", ":"), sort_keys=True),
            ex=ttl,
        )

    @staticmethod
    def _calc_drawdown(entry: float, current: float, direction: str) -> float:
        if not all(math.isfinite(value) and value > 0 for value in (entry, current)):
            return 0.0
        if direction == "long":
            return ((current - entry) / entry) * 100.0
        if direction == "short":
            return ((entry - current) / entry) * 100.0
        return 0.0

    async def should_dca(
        self,
        signal_id: str,
        user_telegram_id: int,
        current_price: float,
        *,
        signal: Optional[Signal] = None,
    ) -> Tuple[bool, str]:
        if not self.enabled():
            return False, "smart_dca_disabled"
        try:
            sig = signal
            if sig is None:
                async with get_session(priority="interactive", label="smart_dca_signal") as session:
                    sig = (
                        await session.execute(
                            select(Signal).where(Signal.signal_id == str(signal_id)).limit(1)
                        )
                    ).scalar_one_or_none()
            if sig is None:
                return False, "signal_not_found"
            direction = _normalise_direction(sig.direction)
            entry = float(sig.entry)
            stop = float(sig.stop_loss)
            current = float(current_price)
            if not direction or not all(
                math.isfinite(value) and value > 0 for value in (entry, stop, current)
            ):
                return False, "invalid_signal_geometry"
            # Never average after the original hard stop has already been crossed.
            if (direction == "long" and current <= stop) or (
                direction == "short" and current >= stop
            ):
                return False, "stop_already_crossed"

            state_data = await self._load_state(user_telegram_id, signal_id)
            dca1_done = state_data.get("dca1_done") is True
            dca2_done = state_data.get("dca2_done") is True
            max_additions = min(2, env_int("SMART_DCA_MAX_ADDITIONS", 2, minimum=0, maximum=2))
            drawdown_pct = self._calc_drawdown(entry, current, direction)

            if not dca1_done and max_additions >= 1 and drawdown_pct <= self.profile.dca_triggers[0]:
                return True, "dca1"
            if (
                dca1_done
                and not dca2_done
                and max_additions >= 2
                and drawdown_pct <= self.profile.dca_triggers[1]
            ):
                return True, "dca2"
            if dca2_done:
                return False, "dca_complete"
            return False, "no_trigger"
        except Exception:
            logger.exception("DCA check failed signal_id=%s user=%s", signal_id, user_telegram_id)
            return False, "error"

    async def execute_dca(
        self,
        signal_id: str,
        user_telegram_id: int,
        dca_level: str,
        current_price: float,
        *,
        signal: Optional[Signal] = None,
    ) -> bool:
        if not self.enabled() or dca_level not in {"dca1", "dca2"}:
            return False
        try:
            sig = signal
            if sig is None:
                async with get_session(priority="interactive", label="smart_dca_execute") as session:
                    sig = (
                        await session.execute(
                            select(Signal).where(Signal.signal_id == str(signal_id)).limit(1)
                        )
                    ).scalar_one_or_none()
            if sig is None:
                return False

            state_data = await self._load_state(user_telegram_id, signal_id)
            if dca_level == "dca1" and state_data.get("dca1_done") is True:
                return False
            if dca_level == "dca2" and (
                state_data.get("dca1_done") is not True
                or state_data.get("dca2_done") is True
            ):
                return False

            direction = _normalise_direction(sig.direction)
            targets = _parse_targets(sig.take_profit)
            current = float(current_price)
            stop = float(sig.stop_loss)
            if not direction or not targets or current <= 0 or stop <= 0:
                return False
            if direction == "long" and not stop < current < targets[0]:
                return False
            if direction == "short" and not targets[0] < current < stop:
                return False

            weight_index = 1 if dca_level == "dca1" else 2
            weight = float(self.profile.scale_weights[weight_index])
            synthetic_id = f"{signal_id}:{dca_level}:{int(user_telegram_id)}"
            routed_signal = {
                "signal_id": synthetic_id,
                "evidence_signal_id": str(signal_id),
                "asset": str(sig.asset),
                "direction": direction,
                "entry": current,
                "stop_loss": stop,
                "take_profit": targets,
                "position_weight": weight,
                "execution_context": "smart_dca",
                "dca_level": dca_level,
            }
            from services.mt5_signal_router import route_signal_to_mt5

            result = await route_signal_to_mt5(
                routed_signal,
                int(user_telegram_id),
                execution_mode="auto",
            )
            if not result.success:
                logger.warning(
                    "DCA broker route rejected signal=%s user=%s level=%s error=%s",
                    signal_id,
                    user_telegram_id,
                    dca_level,
                    result.error,
                )
                return False

            previous_weight = float(
                state_data.get("cumulative_weight") or self.profile.scale_weights[0]
            )
            previous_average = float(state_data.get("avg_entry") or sig.entry)
            cumulative_weight = previous_weight + weight
            avg_entry = (
                (previous_average * previous_weight) + (current * weight)
            ) / cumulative_weight
            state_data.update(
                {
                    "dca1_done": dca_level == "dca1" or state_data.get("dca1_done") is True,
                    "dca2_done": dca_level == "dca2" or state_data.get("dca2_done") is True,
                    "last_level": dca_level,
                    "last_order_id": result.order_id,
                    "executed_at": now_utc_naive().isoformat(),
                    "avg_entry": avg_entry,
                    "cumulative_weight": cumulative_weight,
                }
            )
            await self._save_state(user_telegram_id, signal_id, state_data)
            logger.info(
                "DCA executed signal=%s user=%s level=%s order=%s weight=%s",
                signal_id,
                user_telegram_id,
                dca_level,
                result.order_id,
                weight,
            )
            return True
        except Exception:
            logger.exception("DCA execution failed signal_id=%s user=%s", signal_id, user_telegram_id)
            return False

    def should_breakeven(self, unrealized_pnl_pct: float) -> bool:
        return float(unrealized_pnl_pct) >= self.profile.breakeven_pct

    def get_trail_stop(self, high_watermark_pct: float) -> float:
        return float(high_watermark_pct) - self.profile.trail_distance_pct


async def get_user_dca_profile(telegram_user_id: int) -> str:
    try:
        async with get_session(priority="interactive", label="dca_profile_read") as session:
            user = (
                await session.execute(
                    select(User).where(User.telegram_user_id == int(telegram_user_id)).limit(1)
                )
            ).scalar_one_or_none()
        value = str(getattr(user, "dca_profile", "balanced") or "balanced").lower()
        return value if value in PROFILES else "balanced"
    except Exception:
        return "balanced"


async def set_user_dca_profile(telegram_user_id: int, profile: str) -> bool:
    value = str(profile or "").lower()
    if value not in PROFILES:
        return False
    try:
        async with get_session(priority="interactive", label="dca_profile_write") as session:
            user = (
                await session.execute(
                    select(User).where(User.telegram_user_id == int(telegram_user_id)).limit(1)
                )
            ).scalar_one_or_none()
            if user is None:
                return False
            user.dca_profile = value
            await session.commit()
        return True
    except Exception:
        logger.exception("Failed to set DCA profile user=%s", telegram_user_id)
        return False


async def _eligible_dca_deliveries(limit: int = 50) -> list[tuple[Signal, int, str]]:
    """Return only delivery-proven VIP users who explicitly selected AUTO."""
    async with get_session(priority="background", label="smart_dca_candidates") as session:
        rows = await session.execute(
            select(Signal, User.telegram_user_id, User.dca_profile)
            .join(SignalDelivery, SignalDelivery.signal_id == Signal.signal_id)
            .join(User, User.id == SignalDelivery.user_id)
            .where(
                Signal.archived.is_(False),
                Signal.expired.is_(False),
                SignalDelivery.sent_ok.is_(True),
                SignalDelivery.delivery_state.in_(("delivered", "confirmed", "sent")),
                SignalDelivery.tier_at_send.in_(("vip", "VIP", "owner", "OWNER", "admin", "ADMIN")),
                User.execution_mode.in_(("auto", "live")),
                User.accepted_terms.is_(True),
            )
            .order_by(Signal.created_at.desc())
            .limit(max(1, min(int(limit), 200)))
        )
        return [
            (row[0], int(row[1]), str(row[2] or "balanced"))
            for row in rows.all()
        ]


async def monitor_dca_once() -> dict[str, int]:
    summary = {"candidates": 0, "triggered": 0, "executed": 0, "quote_failed": 0}
    if not SmartDCA.enabled():
        return summary
    from data.get_live_price import get_live_price_result

    rows = await _eligible_dca_deliveries(env_int("SMART_DCA_MONITOR_BATCH", 50, minimum=1, maximum=200))
    summary["candidates"] = len(rows)
    quote_cache: dict[str, LivePriceQuote | None] = {}
    for sig, telegram_user_id, profile_name in rows:
        asset = str(sig.asset).upper()
        if asset not in quote_cache:
            quote_result = await get_live_price_result(
                asset,
                timeout=float(os.getenv("SMART_DCA_QUOTE_TIMEOUT_SECONDS", "5") or 5),
            )
            quote_cache[asset] = quote_result if isinstance(quote_result, LivePriceQuote) else None
        quote = quote_cache[asset]
        if quote is None or quote.source_timestamp is None or quote.is_stale:
            summary["quote_failed"] += 1
            continue
        manager = SmartDCA(profile_name)
        should, level = await manager.should_dca(
            str(sig.signal_id),
            telegram_user_id,
            float(quote.mid),
            signal=sig,
        )
        if not should:
            continue
        summary["triggered"] += 1
        if await manager.execute_dca(
            str(sig.signal_id),
            telegram_user_id,
            level,
            float(quote.mid),
            signal=sig,
        ):
            summary["executed"] += 1
    return summary


async def monitor_dca_opportunities() -> None:
    """Bounded optional scheduler loop; real execution remains default-off."""
    interval = env_int("SMART_DCA_MONITOR_INTERVAL_SECONDS", 60, minimum=15, maximum=3600)
    while True:
        try:
            await monitor_dca_once()
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("DCA monitor error")
            await asyncio.sleep(min(interval, 60))


__all__ = [
    "DCAProfile",
    "PROFILES",
    "SmartDCA",
    "get_user_dca_profile",
    "monitor_dca_once",
    "monitor_dca_opportunities",
    "set_user_dca_profile",
]
