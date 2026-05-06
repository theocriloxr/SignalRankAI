"""
Signal deduplication, caching, and ML rejection tracking.
"""
import logging
import os
from typing import Optional, Dict, Set, Iterable, Any, cast
from datetime import datetime, timedelta

from db.models import Signal, MLRejectedSignal
from db.session import get_session
from sqlalchemy import select
from utils.timeutils import now_utc_naive

logger = logging.getLogger(__name__)

class SignalDeduplicator:
    """Prevent duplicate signals within configured dedup window."""
    
    def __init__(self):
        self.recent_signals: Set[str] = set()
        self._cache_ttl = timedelta(hours=1)
    
    def make_fingerprint(self, asset: str, timeframe: str, direction: str, entry_price: float) -> str:
        """Create unique signal fingerprint."""
        return f"{asset}_{timeframe}_{direction}_{int(entry_price)}"
    
    async def is_duplicate(self, asset: str, timeframe: str, direction: str, entry_price: float) -> bool:
        """Check if signal is duplicate within dedup window."""
        try:
            async with get_session() as session:
                cutoff = now_utc_naive() - self._cache_ttl
                stmt = select(Signal).where(
                    Signal.asset == asset,
                    Signal.timeframe == timeframe,
                    Signal.direction == direction,
                    Signal.entry >= entry_price * 0.99,
                    Signal.entry <= entry_price * 1.01,
                    Signal.created_at >= cutoff
                ).limit(1)
                
                result = await session.execute(stmt)
                return result.scalars().first() is not None
        except Exception as e:
            logger.warning(f"Dedup check failed: {e}")
            return False
    
    async def register_signal(self, asset: str, timeframe: str, direction: str, entry_price: float) -> None:
        """Register signal to prevent future duplication."""
        try:
            fingerprint = self.make_fingerprint(asset, timeframe, direction, entry_price)
            self.recent_signals.add(fingerprint)
        except Exception as e:
            logger.warning(f"Signal registration failed: {e}")


class MLRejectionTracker:
    """Track ML-rejected signals for training and outcome analysis."""

    def __init__(self) -> None:
        self._windows_hours = self._parse_windows(os.getenv("REJECT_OUTCOME_WINDOWS_HOURS"))
        self._min_track_age_hours = max(1, int(os.getenv("REJECT_OUTCOME_MIN_TRACK_AGE_HOURS", "4") or 4))

    @staticmethod
    def _parse_windows(raw: Optional[str]) -> list[int]:
        if not raw:
            return [6, 12, 24]
        out: list[int] = []
        for part in str(raw).split(","):
            part = part.strip().lower().replace("h", "")
            if not part:
                continue
            try:
                val = int(part)
            except Exception:
                continue
            if val > 0:
                out.append(val)
        return sorted(set(out)) or [6, 12, 24]

    @staticmethod
    def _parse_tp_value(take_profit_levels: Any) -> float:
        if isinstance(take_profit_levels, (int, float)):
            return float(take_profit_levels)
        if isinstance(take_profit_levels, (list, tuple)):
            for item in cast(Iterable[Any], take_profit_levels):
                try:
                    if isinstance(item, dict):
                        candidate = item.get("price") or item.get("tp") or item.get("target")
                    else:
                        candidate = item
                    if candidate is None:
                        continue
                    value = float(candidate)
                    if value > 0:
                        return value
                except Exception:
                    continue
        try:
            if take_profit_levels is None:
                return 0.0
            value = float(take_profit_levels)
            return value if value > 0 else 0.0
        except Exception:
            return 0.0

    async def persist_rejection(
        self,
        asset: str,
        timeframe: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit_levels: Any,
        ml_probability: Optional[float],
        rejection_reason: str,
        features: Dict[str, Any],
        rejection_type: Optional[str] = None,
    ) -> None:
        """Store rejection for future outcome tracking."""
        try:
            tp_value = self._parse_tp_value(take_profit_levels)
            if tp_value <= 0:
                tp_value = entry_price * 1.05 if entry_price else 0.0
            safe_ml_prob = float(ml_probability or 0.0)
            features = dict(features or {})
            if rejection_type:
                features.setdefault("rejection_type", rejection_type)
            async with get_session() as session:
                rejection = MLRejectedSignal(
                    asset=str(asset or "").upper(),
                    timeframe=str(timeframe or "").lower(),
                    direction=str(direction or "").lower(),
                    entry=float(entry_price or 0.0),
                    stop_loss=float(stop_loss or 0.0),
                    take_profit=str(tp_value),
                    ml_probability=safe_ml_prob,
                    rejection_reason=str(rejection_reason or "rejected")[:128],
                    features=features,
                    actual_outcome=None,
                    outcome_tracked_at=None,
                    created_at=now_utc_naive(),
                )

                session.add(rejection)
                await session.flush()
                logger.info("Rejection stored: %s %s %s", asset, timeframe, direction)
        except Exception as e:
            logger.error("Failed to persist rejection: %s", e)

    @staticmethod
    def _label_window(
        direction: str,
        stop_loss: float,
        take_profit: float,
        candles: Iterable[Any],
    ) -> str:
        d = str(direction or "long").lower()
        sl = float(stop_loss or 0.0)
        tp = float(take_profit or 0.0)
        if sl <= 0 or tp <= 0:
            return "no_data"
        for candle in candles or []:
            try:
                high = float(getattr(candle, "high", 0.0) or 0.0)
                low = float(getattr(candle, "low", 0.0) or 0.0)
            except Exception:
                continue

            if d == "long":
                hit_sl = low <= sl
                hit_tp = high >= tp
            else:
                hit_sl = high >= sl
                hit_tp = low <= tp

            if hit_sl and hit_tp:
                return "ambiguous"
            if hit_tp:
                return "win"
            if hit_sl:
                return "loss"
        return "no_hit"

    def _resolve_overall_label(self, labels: Dict[str, str]) -> str:
        wins = any(v == "win" for v in labels.values())
        losses = any(v == "loss" for v in labels.values())
        if wins and not losses:
            return "win"
        if losses and not wins:
            return "loss"
        if wins and losses:
            return "ambiguous"
        if any(v == "no_hit" for v in labels.values()):
            return "no_hit"
        if any(v == "no_data" for v in labels.values()):
            return "no_data"
        return "unknown"

    async def _fetch_candles(
        self,
        session: Any,
        symbol: str,
        timeframe: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> list[Any]:
        try:
            from db.models import MarketCandle

            start_ms = int(start_dt.timestamp() * 1000)
            end_ms = int(end_dt.timestamp() * 1000)
            stmt = (
                select(MarketCandle)
                .where(
                    MarketCandle.symbol == str(symbol),
                    MarketCandle.timeframe == str(timeframe),
                    MarketCandle.open_time_ms >= start_ms,
                    MarketCandle.open_time_ms <= end_ms,
                )
                .order_by(MarketCandle.open_time_ms.asc())
                .limit(5000)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
        except Exception:
            return []

    async def _notify_rejection_outcomes(self, summary: Dict[str, int]) -> None:
        try:
            import requests
            from config import OWNER_IDS, ADMIN_IDS

            token = str(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
            if not token:
                return
            recipients = sorted({int(x) for x in (OWNER_IDS or set()) | (ADMIN_IDS or set())})
            if not recipients:
                return
            window_parts = [f"{k}={v}" for k, v in sorted(summary.items())]
            msg = "Rejected outcomes tracked: " + ", ".join(window_parts)
            for rid in recipients:
                try:
                    requests.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": rid, "text": msg},
                        timeout=10,
                    )
                except Exception:
                    logger.debug("Failed to notify admin/owner %s", rid)
        except Exception:
            return
    
    async def track_rejection_outcomes(self) -> int:
        """Check rejected signals for actual outcomes (TP/SL hit). Returns count tracked."""
        try:
            async with get_session() as session:
                # Get rejections still awaiting full window labels
                stmt = select(MLRejectedSignal).where(
                    MLRejectedSignal.outcome_tracked_at.is_(None),
                    MLRejectedSignal.created_at >= now_utc_naive() - timedelta(days=7)
                )
                
                result = await session.execute(stmt)
                rejections = result.scalars().all()
                
                tracked_count = 0
                summary: Dict[str, int] = {}
                for rejection in rejections:
                    time_since = now_utc_naive() - rejection.created_at
                    if time_since < timedelta(hours=self._min_track_age_hours):
                        continue

                    features = dict(getattr(rejection, "features", {}) or {})
                    outcome_labels = dict(features.get("outcome_labels") or {})
                    updated = False

                    for window in self._windows_hours:
                        label_key = f"{int(window)}h"
                        if label_key in outcome_labels:
                            continue
                        window_end = rejection.created_at + timedelta(hours=window)
                        if now_utc_naive() < window_end:
                            continue

                        candles = await self._fetch_candles(
                            session,
                            str(rejection.asset or ""),
                            str(rejection.timeframe or ""),
                            rejection.created_at,
                            window_end,
                        )
                        label = self._label_window(
                            rejection.direction,
                            rejection.stop_loss,
                            float(rejection.take_profit or 0.0),
                            candles,
                        )
                        outcome_labels[label_key] = label
                        summary[label_key] = int(summary.get(label_key, 0) or 0) + 1
                        updated = True

                    if not updated:
                        continue

                    features["outcome_labels"] = outcome_labels
                    features["outcome_windows_hours"] = self._windows_hours
                    rejection.features = features

                    # Mark fully tracked only when all windows are labeled.
                    if all(f"{int(w)}h" in outcome_labels for w in self._windows_hours):
                        overall = self._resolve_overall_label(outcome_labels)
                        outcome_labels["overall"] = overall
                        rejection.actual_outcome = overall
                        rejection.outcome_tracked_at = now_utc_naive()
                    tracked_count += 1
                
                if tracked_count > 0:
                    await session.flush()
                    logger.info(f"Tracked {tracked_count} rejection outcomes")
                    await self._notify_rejection_outcomes(summary)
                
                return tracked_count
        except Exception as e:
            logger.error(f"Failed to track rejection outcomes: {e}")
            return 0
