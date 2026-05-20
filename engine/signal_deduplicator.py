"""
Signal deduplication, caching, and ML rejection tracking.
"""
import logging
import os
import json
from typing import Optional, Dict, Set, Iterable, Any, cast
from datetime import datetime, timedelta

from db.models import Signal, MLRejectedSignal
from db.session import get_session
from sqlalchemy import select, text
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
    """Track all non-issued signals and label would-have outcomes for learning."""

    def __init__(self) -> None:
        raw_windows = (
            os.getenv("REJECT_OUTCOME_WINDOWS")
            or os.getenv("REJECT_OUTCOME_WINDOWS_HOURS")
            or "5m,15m,1h,4h,1d"
        )
        self._windows_minutes = self._parse_windows_minutes(raw_windows)
        self._min_track_age_minutes = max(
            1,
            int(os.getenv("REJECT_OUTCOME_MIN_TRACK_AGE_MINUTES", "5") or 5),
        )
        self._min_track_age_hours = max(1, int(self._min_track_age_minutes // 60) or 1)
        self._move_pct_threshold = max(
            0.01,
            float(os.getenv("REJECT_OUTCOME_MOVE_PCT", "1.0") or 1.0),
        )
        self._adaptive_batch_size = max(
            10,
            int(os.getenv("ADAPTIVE_LEARNING_BATCH_SIZE", "100") or 100),
        )
        self._decision_backfill_lookback_days = max(
            1,
            int(os.getenv("REJECTION_DECISION_LOOKBACK_DAYS", "14") or 14),
        )

    @staticmethod
    def _parse_windows_minutes(raw: Optional[str]) -> list[int]:
        if not raw:
            return [5, 15, 60, 240, 1440]
        out: list[int] = []
        for part in str(raw).split(","):
            token = str(part or "").strip().lower()
            if not token:
                continue
            mult = 1
            if token.endswith("d"):
                mult = 1440
                token = token[:-1]
            elif token.endswith("h"):
                mult = 60
                token = token[:-1]
            elif token.endswith("m"):
                mult = 1
                token = token[:-1]
            try:
                val = int(token)
            except Exception:
                continue
            if val > 0:
                out.append(val * mult)
        return sorted(set(out)) or [5, 15, 60, 240, 1440]

    @staticmethod
    def _window_key(minutes: int) -> str:
        if minutes % 1440 == 0:
            return f"{minutes // 1440}d"
        if minutes % 60 == 0:
            return f"{minutes // 60}h"
        return f"{minutes}m"

    @staticmethod
    def _normalize_timeframe(tf: str) -> str:
        norm = str(tf or "").strip().lower()
        return "1d" if norm == "24h" else norm

    @staticmethod
    def _candidate_timeframes(window_minutes: int, signal_tf: str) -> list[str]:
        stf = MLRejectionTracker._normalize_timeframe(signal_tf)
        if window_minutes <= 15:
            prefs = ["5m", "15m", stf]
        elif window_minutes <= 60:
            prefs = ["15m", "1h", stf]
        elif window_minutes <= 240:
            prefs = ["1h", "4h", stf]
        else:
            prefs = ["4h", "1d", stf]
        out: list[str] = []
        for p in prefs:
            p = MLRejectionTracker._normalize_timeframe(p)
            if p and p not in out:
                out.append(p)
        return out

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
        if isinstance(take_profit_levels, str):
            raw = str(take_profit_levels).strip()
            if not raw:
                return 0.0
            try:
                parsed = json.loads(raw)
                return MLRejectionTracker._parse_tp_value(parsed)
            except Exception:
                pass
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            if parts:
                try:
                    return float(parts[0])
                except Exception:
                    pass
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

    async def _load_runtime_int(self, key: str, default: int = 0) -> int:
        try:
            async with get_session() as session:
                row = (
                    await session.execute(
                        text("SELECT value FROM runtime_state WHERE key = :k"),
                        {"k": str(key)},
                    )
                ).first()
                await session.commit()
            if not row or row[0] is None:
                return int(default)
            value = row[0]
            if isinstance(value, dict):
                for k in ("value", "count", "id"):
                    if k in value:
                        return int(value[k] or 0)
            return int(value)
        except Exception:
            return int(default)

    async def _save_runtime_int(self, key: str, value: int) -> None:
        try:
            async with get_session() as session:
                await session.execute(
                    text(
                        """
                        INSERT INTO runtime_state(key, value, expires_at, updated_at)
                        VALUES (:k, CAST(:v AS JSONB), NULL, NOW())
                        ON CONFLICT (key) DO UPDATE
                        SET value = EXCLUDED.value, updated_at = NOW()
                        """
                    ),
                    {"k": str(key), "v": json.dumps(int(value))},
                )
                await session.commit()
        except Exception:
            return

    async def _ingest_non_ml_rejections_from_decision_log(self) -> int:
        """Backfill skipped/rejected decision logs into MLRejectedSignal for outcome tracking."""
        tracked = 0
        try:
            from db.models import DecisionLog

            last_id = await self._load_runtime_int("rejections_backfill_last_decision_id", 0)
            cutoff = now_utc_naive() - timedelta(days=self._decision_backfill_lookback_days)
            async with get_session() as session:
                rows = (
                    await session.execute(
                        select(DecisionLog)
                        .where(DecisionLog.id > int(last_id))
                        .where(DecisionLog.created_at >= cutoff)
                        .where(DecisionLog.decision.in_(["rejected", "skipped"]))
                        .order_by(DecisionLog.id.asc())
                        .limit(500)
                    )
                ).scalars().all()

                max_seen_id = int(last_id)
                for dl in rows:
                    max_seen_id = max(max_seen_id, int(getattr(dl, "id", 0) or 0))
                    meta = dict(getattr(dl, "meta", {}) or {})
                    asset = str(getattr(dl, "asset", "") or "").upper().strip()
                    timeframe = self._normalize_timeframe(str(getattr(dl, "timeframe", "") or "").strip())
                    direction = str(meta.get("direction") or "").lower().strip()
                    try:
                        entry = float(meta.get("entry") or 0.0)
                        stop_loss = float(meta.get("stop_loss") or 0.0)
                    except Exception:
                        entry = 0.0
                        stop_loss = 0.0
                    take_profit = meta.get("take_profit")
                    ml_prob_raw = meta.get("ml_probability")
                    try:
                        ml_prob = float(ml_prob_raw) if ml_prob_raw is not None else 0.0
                    except Exception:
                        ml_prob = 0.0

                    if not asset or not timeframe or direction not in {"long", "short"}:
                        continue
                    if entry <= 0 or stop_loss <= 0:
                        continue

                    feature_blob = {
                        "source": "decision_log",
                        "decision_log_id": int(getattr(dl, "id", 0) or 0),
                        "decision": str(getattr(dl, "decision", "") or ""),
                        "reason": str(getattr(dl, "reason", "") or "")[:256],
                    }
                    feature_blob.update(meta)

                    rejection = MLRejectedSignal(
                        asset=asset,
                        timeframe=timeframe,
                        direction=direction,
                        entry=entry,
                        stop_loss=stop_loss,
                        take_profit=str(self._parse_tp_value(take_profit) or 0.0),
                        ml_probability=ml_prob,
                        rejection_reason=str(getattr(dl, "reason", "") or getattr(dl, "decision", "rejected"))[:128],
                        features=feature_blob,
                        actual_outcome=None,
                        outcome_tracked_at=None,
                        created_at=getattr(dl, "created_at", None) or now_utc_naive(),
                    )
                    session.add(rejection)
                    tracked += 1

                if tracked > 0:
                    await session.flush()
                await session.commit()

            if rows:
                await self._save_runtime_int("rejections_backfill_last_decision_id", max_seen_id)
        except Exception as e:
            logger.debug("Decision-log rejection backfill skipped: %s", e)
        return tracked

    @staticmethod
    def _label_target_window(
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

    @staticmethod
    def _directional_label(direction: str, entry: float, close_price: float) -> str:
        if entry <= 0 or close_price <= 0:
            return "no_data"
        d = str(direction or "long").lower()
        if d == "long":
            return "win" if close_price > entry else ("loss" if close_price < entry else "flat")
        return "win" if close_price < entry else ("loss" if close_price > entry else "flat")

    @staticmethod
    def _pct_move_label(direction: str, entry: float, close_price: float, threshold_pct: float) -> str:
        if entry <= 0 or close_price <= 0:
            return "no_data"
        pct = ((close_price - entry) / entry) * 100.0
        d = str(direction or "long").lower()
        if d == "short":
            pct = -pct
        if pct >= threshold_pct:
            return "win"
        if pct <= -threshold_pct:
            return "loss"
        return "no_hit"

    @staticmethod
    def _window_label_from_methods(method_labels: Dict[str, str]) -> str:
        wins = sum(1 for v in method_labels.values() if v == "win")
        losses = sum(1 for v in method_labels.values() if v == "loss")
        if wins > losses:
            return "win"
        if losses > wins:
            return "loss"
        if wins and losses:
            return "ambiguous"
        if any(v == "flat" for v in method_labels.values()):
            return "flat"
        if any(v == "no_hit" for v in method_labels.values()):
            return "no_hit"
        if any(v == "no_data" for v in method_labels.values()):
            return "no_data"
        return "unknown"

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

    @staticmethod
    def _last_close(candles: Iterable[Any]) -> float:
        last = None
        for c in candles or []:
            last = c
        if last is None:
            return 0.0
        try:
            return float(getattr(last, "close", 0.0) or 0.0)
        except Exception:
            return 0.0

    async def _evaluate_window(
        self,
        session: Any,
        rejection: MLRejectedSignal,
        window_minutes: int,
    ) -> tuple[str, Dict[str, str], float]:
        end_dt = rejection.created_at + timedelta(minutes=window_minutes)
        candles: list[Any] = []
        used_tf = ""
        for tf in self._candidate_timeframes(window_minutes, str(rejection.timeframe or "")):
            candles = await self._fetch_candles(
                session,
                str(rejection.asset or ""),
                tf,
                rejection.created_at,
                end_dt,
            )
            if candles:
                used_tf = tf
                break

        close_price = self._last_close(candles)
        entry = float(rejection.entry or 0.0)
        target_label = self._label_target_window(
            rejection.direction,
            float(rejection.stop_loss or 0.0),
            float(rejection.take_profit or 0.0),
            candles,
        )
        directional_label = self._directional_label(rejection.direction, entry, close_price)
        pct_label = self._pct_move_label(
            rejection.direction,
            entry,
            close_price,
            self._move_pct_threshold,
        )
        methods = {
            "target_hit": target_label,
            "directional": directional_label,
            "pct_move": pct_label,
        }
        window_label = self._window_label_from_methods(methods)
        methods["source_timeframe"] = used_tf or "none"
        return window_label, methods, close_price

    async def _notify_admin_owner(self, msg: str) -> None:
        try:
            import requests
            from config import OWNER_IDS, ADMIN_IDS

            token = str(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
            if not token:
                return
            recipients = sorted({int(x) for x in (OWNER_IDS or set()) | (ADMIN_IDS or set())})
            if not recipients:
                return
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

    async def _run_adaptive_learning_if_due(self) -> None:
        try:
            async with get_session() as session:
                accepted_total = int(
                    (
                        await session.execute(
                            text("SELECT COUNT(*) FROM outcomes WHERE closed_at IS NOT NULL")
                        )
                    ).scalar()
                    or 0
                )
                rejected_total = int(
                    (
                        await session.execute(
                            text("SELECT COUNT(*) FROM ml_rejected_signals WHERE outcome_tracked_at IS NOT NULL")
                        )
                    ).scalar()
                    or 0
                )
                total = accepted_total + rejected_total

            last_mark = await self._load_runtime_int("adaptive_learning_last_total", 0)
            if total < (last_mark + self._adaptive_batch_size):
                return

            batch_mark = (total // self._adaptive_batch_size) * self._adaptive_batch_size
            await self._save_runtime_int("adaptive_learning_last_total", batch_mark)

            threshold_info = "n/a"
            try:
                from engine.threshold_optimizer import refresh_thresholds

                cfg = await refresh_thresholds(force=True)
                if cfg is not None:
                    _force_env_override = bool((os.getenv("PREMIUM_SCORE_THRESHOLD_FORCE") or "").strip())
                    os.environ["ML_PROB_THRESHOLD"] = str(float(getattr(cfg, "ml_prob_threshold", 0.55) or 0.55))
                    if not _force_env_override:
                        os.environ["PREMIUM_SCORE_THRESHOLD"] = str(
                            float(getattr(cfg, "min_score_threshold", 70.0) or 70.0)
                        )
                    os.environ["CONFLUENCE_GATE_MIN"] = str(float(getattr(cfg, "confluence_min", 0.0) or 0.0))
                    threshold_info = (
                        f"ml={float(getattr(cfg, 'ml_prob_threshold', 0.55) or 0.55):.3f}, "
                        f"score={float(getattr(cfg, 'min_score_threshold', 70.0) or 70.0):.1f}, "
                        f"confluence={float(getattr(cfg, 'confluence_min', 0.0) or 0.0):.1f}"
                    )
                    if _force_env_override:
                        threshold_info += " (score env override preserved)"
            except Exception as e:
                logger.warning("Adaptive threshold refresh failed: %s", e)

            gemini_ok = False
            gemini_error = ""
            try:
                from services.gemini_ml import run_gemini_review_pipeline

                gemini_res = await run_gemini_review_pipeline(
                    trigger="adaptive_learning_batch",
                    scope="all_time",
                )
                gemini_ok = bool(gemini_res.get("ok"))
                if not gemini_ok:
                    gemini_error = str(gemini_res.get("error") or "")
            except Exception as e:
                gemini_ok = False
                gemini_error = str(e)

            news_hint = "n/a"
            try:
                from data.news import get_news_sentiment
                async with get_session() as session:
                    top_assets = (
                        await session.execute(
                            text(
                                """
                                SELECT asset, COUNT(*) c
                                FROM ml_rejected_signals
                                WHERE outcome_tracked_at IS NOT NULL
                                GROUP BY asset
                                ORDER BY c DESC
                                LIMIT 3
                                """
                            )
                        )
                    ).fetchall()
                    await session.commit()
                hints: list[str] = []
                for row in top_assets:
                    asset = str(row[0] or "").upper()
                    if not asset:
                        continue
                    try:
                        hints.append(f"{asset}:{float(get_news_sentiment(asset)):.2f}")
                    except Exception:
                        continue
                if hints:
                    news_hint = ", ".join(hints)
            except Exception:
                pass

            retrain_ok = False
            try:
                from ml.train_model import main as train_main

                retrain_ok = bool(await train_main())
            except Exception as e:
                logger.warning("Adaptive retrain failed: %s", e)

            message = (
                "Adaptive learning applied immediately. "
                f"global_outcomes={total} (accepted={accepted_total}, rejected={rejected_total}), "
                f"batch={batch_mark}. "
                f"thresholds={threshold_info}. "
                f"gemini_ok={gemini_ok}"
            )
            if gemini_error:
                message += f" gemini_error={gemini_error[:120]}"
            message += f". retrain_ok={retrain_ok}. news_hint={news_hint}"
            await self._notify_admin_owner(message)
        except Exception as e:
            logger.warning("Adaptive learning trigger failed: %s", e)

    async def _notify_rejection_outcomes(self, summary: Dict[str, int]) -> None:
        try:
            if not summary:
                return
            window_parts = [f"{k}={v}" for k, v in sorted(summary.items())]
            msg = "Rejected outcomes tracked: " + ", ".join(window_parts)
            await self._notify_admin_owner(msg)
        except Exception:
            return
    
    async def track_rejection_outcomes(self) -> int:
        """Track all non-issued outcomes across configured windows and trigger adaptive learning."""
        try:
            backfilled = await self._ingest_non_ml_rejections_from_decision_log()
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
                    if time_since < timedelta(minutes=self._min_track_age_minutes):
                        continue

                    features = dict(getattr(rejection, "features", {}) or {})
                    outcome_labels = dict(features.get("outcome_labels") or {})
                    outcome_methods = dict(features.get("outcome_methods") or {})
                    outcome_close_prices = dict(features.get("outcome_close_prices") or {})
                    updated = False

                    for window in self._windows_minutes:
                        label_key = self._window_key(int(window))
                        if label_key in outcome_labels:
                            continue
                        window_end = rejection.created_at + timedelta(minutes=window)
                        if now_utc_naive() < window_end:
                            continue

                        label, methods, close_px = await self._evaluate_window(
                            session=session,
                            rejection=rejection,
                            window_minutes=int(window),
                        )
                        outcome_labels[label_key] = label
                        outcome_methods[label_key] = methods
                        outcome_close_prices[label_key] = close_px
                        summary[label_key] = int(summary.get(label_key, 0) or 0) + 1
                        updated = True

                    if not updated:
                        continue

                    features["outcome_labels"] = outcome_labels
                    features["outcome_methods"] = outcome_methods
                    features["outcome_close_prices"] = outcome_close_prices
                    features["outcome_windows_minutes"] = self._windows_minutes
                    features["evaluation_mode"] = "close_at_each_window"
                    rejection.features = features

                    # Mark fully tracked only when all windows are labeled.
                    if all(self._window_key(int(w)) in outcome_labels for w in self._windows_minutes):
                        overall = self._resolve_overall_label(outcome_labels)
                        outcome_labels["overall"] = overall
                        rejection.actual_outcome = overall
                        rejection.outcome_tracked_at = now_utc_naive()
                    tracked_count += 1
                
                if tracked_count > 0:
                    await session.flush()
                    logger.info(f"Tracked {tracked_count} rejection outcomes")
                    await self._notify_rejection_outcomes(summary)

            if tracked_count > 0 or backfilled > 0:
                await self._run_adaptive_learning_if_due()
                
                return tracked_count + backfilled
        except Exception as e:
            logger.error(f"Failed to track rejection outcomes: {e}")
            return 0
