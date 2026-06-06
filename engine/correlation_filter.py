from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default)
    raw = raw.strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.getenv(name) or str(default)).strip())
    except Exception:
        return float(default)


# Lightweight cluster map to prevent over-exposure on tightly coupled assets.
CRYPTO_CLUSTER_OVERRIDES: dict[str, str] = {
    "BTCUSDT": "cluster_btc_beta",
    "ETHUSDT": "cluster_btc_beta",
    "SOLUSDT": "cluster_btc_beta",
    "BNBUSDT": "cluster_btc_beta",
    "AVAXUSDT": "cluster_btc_beta",
    "MATICUSDT": "cluster_btc_beta",
    "POLUSDT": "cluster_btc_beta",
}


def _signal_asset(signal: Dict[str, Any]) -> str:
    return str(signal.get("asset") or signal.get("symbol") or "").upper().strip()


def _signal_timeframe(signal: Dict[str, Any]) -> str:
    return str(signal.get("timeframe") or "").lower().strip()


def _signal_score(signal: Dict[str, Any]) -> float:
    try:
        return float(signal.get("score") or 0.0)
    except Exception:
        return 0.0


def _cluster_for_symbol(symbol: str) -> str:
    s = str(symbol or "").upper().strip()
    if not s:
        return "cluster_unknown"

    mapped = CRYPTO_CLUSTER_OVERRIDES.get(s)
    if mapped:
        return mapped

    if s.endswith("USDT"):
        base = s[:-4]
        return f"cluster_crypto_{base[:3]}"

    if len(s) == 6:
        base = s[:3]
        quote = s[3:]
        return f"cluster_fx_{base}_{quote}"

    if ":" in s:
        return f"cluster_{s.split(':', 1)[0]}"

    return f"cluster_asset_{s[:6]}"


def cluster_key(signal: Dict[str, Any]) -> Tuple[str, str]:
    symbol = _signal_asset(signal)
    timeframe = _signal_timeframe(signal)
    return (_cluster_for_symbol(symbol), timeframe)


def select_best_per_cluster(signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for signal in signals or []:
        key = cluster_key(signal)
        incumbent = best.get(key)
        if incumbent is None:
            best[key] = signal
            continue

        candidate_rank = (
            _signal_score(signal),
            float(signal.get("ml_probability") or 0.0),
        )
        incumbent_rank = (
            _signal_score(incumbent),
            float(incumbent.get("ml_probability") or 0.0),
        )
        if candidate_rank > incumbent_rank:
            best[key] = signal

    # Keep stable highest-first ordering for deterministic dispatch.
    return sorted(best.values(), key=_signal_score, reverse=True)


# ──────────────────────────────────────────────────────────────────────────────────────────────────────────
# Portfolio Exposure Manager (Capital Protection)
# ────────────────────────────────────────────────────���─────────────────────────────────────────────────────
# Limits open trades per asset class + direction to prevent over-exposure.
# E.g., max 2 Crypto Shorts, 2 Crypto Longs, etc.

class PortfolioExposureManager:
    """Gatekeeper that limits trades per asset class+direction to prevent correlation risk."""

    def __init__(
        self,
        max_sector_direction: int = 2,
        max_global_trades: int = 5,
    ):
        self.max_sector_direction = max_sector_direction
        self.max_global_trades = max_global_trades

    async def is_trade_allowed(
        self,
        session,
        asset_class: str,
        direction: str,
    ) -> bool:
        """Returns True if portfolio has room for this trade, False if over-exposed."""
        try:
            # Normalize inputs
            asset_class = str(asset_class or "crypto").lower().strip()
            direction = str(direction or "long").lower().strip()

            # If no session provided, create one internally
            if session is None:
                try:
                    from db.session import get_session
                    async with get_session() as _internal_session:
                        return await self._check_exposure(_internal_session, asset_class, direction)
                except Exception as e:
                    logger.debug(f"[exposure] could not create internal session: {e}")
                    return True  # Fail open - allow trade if we can't check
            else:
                return await self._check_exposure(session, asset_class, direction)

        except Exception as e:
            logger.error(f"Failed to check portfolio exposure: {e}")
            # Fail closed to protect capital
            return False

    async def _check_exposure(self, session, asset_class: str, direction: str) -> bool:
        """Internal method to check exposure limits."""
        try:
            # Import here to avoid circular imports
            from db.models import Signal
            from sqlalchemy import select, func

            # Query open trades (not expired, not archived)
            query = (
                select(Signal.asset, Signal.direction, func.count(Signal.signal_id).label("count"))
                .where(
                    Signal.expired.is_(False),
                    Signal.archived.is_(False),
                )
                .group_by(Signal.asset, Signal.direction)
            )
            result = await session.execute(query)
            rows = result.fetchall()

            # Count trades by asset_class + direction
            sector_direction_count = 0
            global_count = 0

            for row in rows:
                trade_asset = str(row[0] or "").upper().strip()
                trade_direction = str(row[1] or "").lower().strip()
                count = int(row[2] or 0)

                # Determine asset class for this trade
                trade_class = self._get_asset_class(trade_asset)

                global_count += count

                # Count within the same asset_class + direction
                if trade_class == asset_class and trade_direction == direction:
                    sector_direction_count += count

            # Check global limit
            if global_count >= self.max_global_trades:
                logger.warning(
                    f"Portfolio maxed out ({global_count}/{self.max_global_trades} trades). "
                    f"Blocking {direction} on {asset_class}."
                )
                return False

            # Check sector direction limit
            if sector_direction_count >= self.max_sector_direction:
                logger.warning(
                    f"Sector maxed out ({sector_direction_count}/{self.max_sector_direction} "
                    f"{asset_class} {direction}s). Blocking trade."
                )
                return False

            logger.debug(
                f"Portfolio check passed: {asset_class} {direction} "
                f"({sector_direction_count}/{self.max_sector_direction}), "
                f"global ({global_count}/{self.max_global_trades})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to check portfolio exposure: {e}")
            # Fail closed to protect capital
            return False

    def _get_asset_class(self, asset: str) -> str:
        """Determine asset class from symbol."""
        from data.fetcher import is_crypto, is_fx, is_stock

        s = str(asset or "").upper().strip()
        if is_crypto(s):
            return "crypto"
        if is_fx(s):
            return "fx"
        if is_stock(s):
            return "stock"
        # Default to crypto for crypto symbols
        if s.endswith("USDT") or s.endswith("BUSD"):
            return "crypto"
        return "other"


def _create_exposure_manager() -> PortfolioExposureManager:
    """Factory to create exposure manager with env overrides."""
    return PortfolioExposureManager(
        max_sector_direction=_env_int("PORTFOLIO_MAX_SECTOR_DIRECTION", 2),
        max_global_trades=_env_int("PORTFOLIO_MAX_GLOBAL_TRADES", 5),
    )


# Global instance
exposure_manager = _create_exposure_manager()
