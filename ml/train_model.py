#!/usr/bin/env python
"""
Train XGBoost model from existing signal history.
Loads signals + outcomes from Postgres, builds feature matrix, trains model.
"""

import os
import hashlib
import sys
import json
import logging
import math
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.isotonic import IsotonicRegression
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import roc_auc_score, accuracy_score, confusion_matrix, classification_report

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "y"}


def _safe_float(val):
    """Coerce numbers that may be stored as strings or single-item lists."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, (list, tuple)):
        return _safe_float(val[0]) if val else 0.0
    try:
        s = str(val).strip()
        if not s:
            return 0.0
        return float(s)
    except Exception:
        try:
            import json

            parsed = json.loads(str(val))
            if isinstance(parsed, (list, tuple)):
                return _safe_float(parsed[0]) if parsed else 0.0
            if isinstance(parsed, (int, float)):
                return float(parsed)
        except Exception:
            pass
    return 0.0


def _generate_offline_bootstrap_data(num_samples: int = 1200) -> pd.DataFrame:
    """Generate synthetic-but-structured training rows when DB is unavailable.

    The generator is deterministic by default and encodes realistic relationships
    between score, RR, trend alignment, macro pressure, and outcome likelihood.
    """
    seed = int(os.getenv("ML_OFFLINE_BOOTSTRAP_SEED", "42") or 42)
    rng = np.random.default_rng(seed)
    now = datetime.utcnow()

    assets = ["BTCUSDT", "ETHUSDT", "EURUSD", "GBPUSD", "XAUUSD", "AAPL", "SPY", "US30"]
    timeframes = ["15m", "1h", "4h", "1d"]
    strategies = ["ATR Breakout", "EMA Trend", "Structure Bull", "RSI Momentum", "fibonacci_confluence"]
    regimes = ["TRENDING", "RANGING", "VOLATILE"]

    rows = []
    for i in range(max(50, int(num_samples))):
        asset = str(rng.choice(assets))
        tf = str(rng.choice(timeframes, p=[0.25, 0.35, 0.25, 0.15]))
        strategy = str(rng.choice(strategies))
        regime = str(rng.choice(regimes, p=[0.42, 0.33, 0.25]))
        direction = "long" if float(rng.random()) > 0.47 else "short"

        asset_class_enc = 0.0 if asset.endswith(("USDT", "USDC", "BUSD")) else 1.0 if len(asset) == 6 and asset.isalpha() else 2.0 if asset.startswith("XAU") else 3.0

        score = float(np.clip(rng.normal(66.0, 11.0), 25.0, 95.0))
        rr_ratio = float(np.clip(rng.normal(1.75, 0.55), 0.6, 4.0))
        strength = float(np.clip(score + rng.normal(0.0, 8.0), 10.0, 100.0))

        price_velocity_3 = float(np.clip(rng.normal(0.0, 0.02), -0.08, 0.08))
        price_velocity_5 = float(np.clip(price_velocity_3 + rng.normal(0.0, 0.01), -0.08, 0.08))
        price_velocity_10 = float(np.clip(rng.normal(0.0, 0.02), -0.08, 0.08))
        price_acceleration = float(price_velocity_3 - price_velocity_10)
        atr_rel = float(np.clip(abs(rng.normal(0.01, 0.007)), 0.001, 0.06))
        atr_regime = float(np.clip(rng.normal(1.0, 0.35), 0.2, 3.5))
        relative_volume = float(np.clip(rng.normal(1.05, 0.45), 0.2, 5.0))
        mtf_4h_trend = float(rng.choice([-1.0, 0.0, 1.0], p=[0.27, 0.22, 0.51]))
        mtf_1d_trend = float(rng.choice([-1.0, 0.0, 1.0], p=[0.29, 0.24, 0.47]))

        funding_rate = float(np.clip(rng.normal(0.0, 0.003), -0.02, 0.02))
        open_interest_change = float(np.clip(rng.normal(0.0, 0.04), -0.2, 0.2))
        dxy_trend = float(np.clip(rng.normal(0.0, 0.02), -0.08, 0.08))
        vix_trend = float(np.clip(rng.normal(0.0, 0.03), -0.12, 0.12))
        us10y_trend = float(np.clip(rng.normal(0.0, 0.015), -0.06, 0.06))
        yield_spread = float(np.clip(rng.normal(0.015, 0.008), -0.02, 0.04))
        minutes_since_news = float(np.clip(rng.exponential(180.0), 0.0, 1440.0))
        minutes_until_news = float(np.clip(rng.exponential(210.0), 0.0, 1440.0))
        news_event_impact_score = float(np.clip(max(0.0, 1.0 - (min(minutes_since_news, minutes_until_news) / 90.0)), 0.0, 1.0))
        spx_trend = float(np.clip(rng.normal(0.0, 0.018), -0.07, 0.07))
        btc_corr = float(np.clip(rng.normal(0.2 if asset_class_enc in (0.0, 3.0) else 0.05, 0.25), -0.85, 0.95))

        trend_alignment = 0.5 * mtf_4h_trend + 0.7 * mtf_1d_trend
        directional_bias = 0.35 if direction == "long" else -0.25
        macro_penalty = 0.8 * max(vix_trend, 0.0) + 0.9 * news_event_impact_score
        macro_support = 0.35 * spx_trend - 0.25 * dxy_trend + 0.2 * yield_spread
        z = (
            -0.9
            + 0.055 * (score - 60.0)
            + 0.85 * (rr_ratio - 1.0)
            + 0.012 * (strength - 50.0)
            + 0.6 * trend_alignment
            + 0.45 * price_acceleration
            + 0.25 * open_interest_change
            + 0.18 * relative_volume
            + directional_bias
            + macro_support
            - macro_penalty
            + float(rng.normal(0.0, 0.45))
        )
        p_win = 1.0 / (1.0 + math.exp(-z))
        target = 1 if float(rng.random()) < p_win else 0

        barrier_type = "upper" if target == 1 else "lower"
        false_breakout = int(float(rng.random()) < (0.22 if target == 0 else 0.07))
        partial_tp_progress = 0
        if target == 1:
            partial_tp_progress = int(rng.choice([1, 2, 3], p=[0.45, 0.35, 0.20]))
        elif float(rng.random()) < 0.17:
            partial_tp_progress = 1

        sample_weight = 1.0
        if target == 1 and rr_ratio >= 2.0:
            sample_weight *= 1.15
        if target == 0 and false_breakout:
            sample_weight *= 0.72

        entry = float(np.clip(rng.uniform(1.0, 50000.0), 1.0, 50000.0))
        risk_pct = float(np.clip(rng.normal(0.012, 0.006), 0.002, 0.04))
        if direction == "long":
            stop_loss = entry * (1.0 - risk_pct)
            take_profit = entry * (1.0 + risk_pct * rr_ratio)
        else:
            stop_loss = entry * (1.0 + risk_pct)
            take_profit = entry * (1.0 - risk_pct * rr_ratio)

        created_at = now - timedelta(hours=float(rng.uniform(1.0, 24.0 * 120.0)))
        row = {
            "signal_id": f"bootstrap_{i}",
            "asset": asset,
            "timeframe": tf,
            "direction": direction,
            "score": score,
            "entry": float(entry),
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
            "rr_ratio": rr_ratio,
            "strategy_name": strategy,
            "regime": regime,
            "strength": strength,
            "ml_probability": float(p_win),
            "price_velocity_3": price_velocity_3,
            "price_velocity_5": price_velocity_5,
            "price_velocity_10": price_velocity_10,
            "price_acceleration_3_10": price_acceleration,
            "atr_rel": atr_rel,
            "atr_regime": atr_regime,
            "relative_volume": relative_volume,
            "mtf_4h_trend": mtf_4h_trend,
            "mtf_1d_trend": mtf_1d_trend,
            "funding_rate": funding_rate,
            "open_interest_change": open_interest_change,
            "asset_class_enc": asset_class_enc,
            "dxy_trend": dxy_trend,
            "vix_trend": vix_trend,
            "us10y_trend": us10y_trend,
            "yield_spread": yield_spread,
            "minutes_since_high_impact_news": minutes_since_news,
            "minutes_until_high_impact_news": minutes_until_news,
            "news_event_impact_score": news_event_impact_score,
            "spx_trend": spx_trend,
            "btc_corr": btc_corr,
            "partial_tp_progress": int(partial_tp_progress),
            "false_breakout": int(false_breakout),
            "barrier_type": barrier_type,
            "sample_weight": float(sample_weight),
            "created_at": created_at,
            "target": int(target),
        }
        rows.append(row)

    out = pd.DataFrame(rows)
    logger.warning(
        "Using offline bootstrap data: rows=%s seed=%s class_dist=%s",
        len(out),
        seed,
        out["target"].value_counts().to_dict() if "target" in out.columns else {},
    )
    return out


async def load_training_data_sync(lookback_days: int = 90):
    """Load signals + outcomes from Postgres using synchronous session.

    This is FIX for the asyncpg thread deadlock issue.
    When running ML training in a separate thread via asyncio.to_thread(),
    the async session cannot cross thread boundaries because asyncpg
    is bound to the event loop where it was created.
    Use synchronous SQLAlchemy for background tasks.
    """
    logger.info("[ml] Starting load_training_data_sync...")
    try:
        from db.session import get_sync_session, get_session

        from db.models import Signal, Outcome, MarketCandle, MLRejectedSignal
        from sqlalchemy import select, desc
        logger.info("[ml] Fetching signals from DB (sync)...")

        def _parse_tp(raw_tp):
            if raw_tp is None:
                return 0.0
            if isinstance(raw_tp, (int, float)):
                return float(raw_tp)
            if isinstance(raw_tp, (list, tuple)):
                vals = []
                for item in raw_tp:
                    try:
                        if isinstance(item, dict):
                            vals.append(float(item.get("price") or item.get("tp") or item.get("target")))
                        else:
                            vals.append(float(item))
                    except Exception:
                        continue
                return float(vals[0]) if vals else 0.0
            try:
                txt = str(raw_tp)
                parsed = json.loads(txt)
                return _parse_tp(parsed)
            except Exception:
                try:
                    return float(raw_tp)
                except Exception:
                    return 0.0

        def _load_candles_sync(symbol: str, timeframe: str, created_at: datetime, limit: int = 80):
            if not symbol or not timeframe or not created_at:
                return []
            cutoff_ms = int(created_at.timestamp() * 1000)
            Session = get_sync_session()
            with Session() as candle_session:
                q = (
                    select(MarketCandle)
                    .where(
                        MarketCandle.symbol == str(symbol),
                        MarketCandle.timeframe == str(timeframe),
                        MarketCandle.open_time_ms <= cutoff_ms,
                    )
                    .order_by(desc(MarketCandle.open_time_ms))
                    .limit(limit)
                )
                res = candle_session.execute(q)
                rows = list(res.scalars().all())
                rows.reverse()
                return rows

        def _atr(highs, lows, closes, period=14):
            if len(closes) < period + 1:
                return 0.0
            trs = []
            for i in range(1, len(closes)):
                h = float(highs[i])
                l = float(lows[i])
                pc = float(closes[i - 1])
                trs.append(max(h - l, abs(h - pc), abs(l - pc)))
            tail = trs[-period:] if len(trs) >= period else trs
            return (sum(tail) / len(tail)) if tail else 0.0

        def _pct(closes, n):
            if len(closes) <= n:
                return 0.0
            prev = float(closes[-(n + 1)])
            cur = float(closes[-1])
            if prev <= 0:
                return 0.0
            return (cur - prev) / prev

        def _trend_from_closes(closes):
            if len(closes) < 50:
                return 0.0
            sma20 = sum(closes[-20:]) / 20.0
            sma50 = sum(closes[-50:]) / 50.0
            if sma20 > sma50:
                return 1.0
            if sma20 < sma50:
                return -1.0
            return 0.0

        async with get_session() as session:
            # Get signals delivered in the requested lookback window with outcomes
            cutoff_days = max(1, int(lookback_days or 90))
            cutoff = datetime.utcnow() - timedelta(days=cutoff_days)

            stmt = (
                select(Signal, Outcome)
                .join(Outcome, Outcome.signal_id == Signal.signal_id)
                .where(Signal.created_at >= cutoff)
            )
            try:
                res = session.execute(stmt)
                rows = list(res.all())
                session.commit()
            except Exception as exc:
                logger.warning("Failed to load training data from DB; using offline bootstrap data: %s", exc)
                if _env_bool("ML_OFFLINE_BOOTSTRAP_ENABLED", True):
                    return _generate_offline_bootstrap_data(int(os.getenv("ML_OFFLINE_BOOTSTRAP_ROWS", "1200") or 1200))
                return None

        if not rows:
            logger.warning("No signals with outcomes found in last 90 days")
            if _env_bool("ML_OFFLINE_BOOTSTRAP_ENABLED", True):
                return _generate_offline_bootstrap_data(int(os.getenv("ML_OFFLINE_BOOTSTRAP_ROWS", "1200") or 1200))
            return None

        data = []
        for sig, outcome in rows:
            status = str(getattr(outcome, 'status', '') or '').lower()
            meta = getattr(outcome, 'meta', None) or {}
            if not isinstance(meta, dict):
                meta = {}
            macro = dict(meta.get('macro') or {})

            created_at = getattr(sig, 'created_at', None) or datetime.utcnow()
            candles = await _load_candles(
                str(getattr(sig, 'asset', '') or ''),
                str(getattr(sig, 'timeframe', '') or ''),
                created_at,
                limit=120,
            )
            closes = [float(getattr(c, 'close', 0.0) or 0.0) for c in candles]
            highs = [float(getattr(c, 'high', 0.0) or 0.0) for c in candles]
            lows = [float(getattr(c, 'low', 0.0) or 0.0) for c in candles]
            vols = [float(getattr(c, 'volume', 0.0) or 0.0) for c in candles]

            vel3 = _pct(closes, 3)
            vel5 = _pct(closes, 5)
            vel10 = _pct(closes, 10)
            atr14 = _atr(highs, lows, closes, period=14)
            atr50 = _atr(highs, lows, closes, period=50)
            atr_rel = (atr14 / closes[-1]) if closes and closes[-1] > 0 else 0.0
            atr_regime = (atr14 / atr50) if atr50 > 0 else 0.0
            rel_vol = 0.0
            if len(vols) >= 21:
                ma20v = sum(vols[-21:-1]) / 20.0
                rel_vol = (vols[-1] / ma20v) if ma20v > 0 else 0.0

            candles_4h = await _load_candles(str(getattr(sig, 'asset', '') or ''), '4h', created_at, limit=60)
            closes_4h = [float(getattr(c, 'close', 0.0) or 0.0) for c in candles_4h]
            candles_1d = await _load_candles(str(getattr(sig, 'asset', '') or ''), '1d', created_at, limit=60)
            closes_1d = [float(getattr(c, 'close', 0.0) or 0.0) for c in candles_1d]
            mtf_4h_trend = _trend_from_closes(closes_4h)
            mtf_1d_trend = _trend_from_closes(closes_1d)

            # Capture partial TP progression even when final status is SL.
            tp_progress = 0
            for key in ("tp_progress", "max_tp_hit", "tp_hit_count", "highest_tp_reached"):
                try:
                    tp_progress = max(tp_progress, int(meta.get(key) or 0))
                except Exception:
                    continue

            false_breakout = 0
            for k in ("false_breakout", "volatility_stopout", "sl_then_tp1", "post_sl_reversal_to_tp1"):
                try:
                    if bool(meta.get(k)):
                        false_breakout = 1
                        break
                except Exception:
                    continue

            if status in ("tp", "tp1", "tp2", "tp3", "partial_tp"):
                barrier = "upper"
            elif status in ("expired", "timeout", "time", "time_expired"):
                barrier = "time"
            else:
                barrier = "lower"

            # Binary target + sample-weight shaping.
            target = 1 if barrier == "upper" else 0
            sample_weight = 1.0
            if status in ("tp", "tp3"):
                sample_weight = 1.30
                tp_progress = max(tp_progress, 3)
            elif status == "tp2":
                sample_weight = 1.15
                tp_progress = max(tp_progress, 2)
            elif status in ("tp1", "partial_tp"):
                sample_weight = 1.05
                tp_progress = max(tp_progress, 1)
            elif barrier == "time":
                sample_weight = 0.85
            elif status == "sl":
                if tp_progress >= 2:
                    sample_weight = 0.55
                elif tp_progress >= 1:
                    sample_weight = 0.70

            if false_breakout:
                # Keep the sample, but reduce SL penalty so model learns stop-hunt contexts.
                sample_weight *= 0.65

            rr_raw = _safe_float(getattr(sig, 'rr_estimate', 0))
            rr_eff = min(4.0, max(0.5, rr_raw))
            sample_weight *= (0.75 + (rr_eff / 4.0))

            row = {
                'signal_id': sig.signal_id,
                'asset': sig.asset,
                'timeframe': sig.timeframe,
                'direction': sig.direction,
                'score': _safe_float(getattr(sig, 'score', 0)),
                'entry': _safe_float(getattr(sig, 'entry', 0)),
                'stop_loss': _safe_float(getattr(sig, 'stop_loss', 0)),
                'take_profit': _parse_tp(getattr(sig, 'take_profit', 0)),
                'rr_ratio': _safe_float(getattr(sig, 'rr_estimate', 0)),
                'strategy_name': sig.strategy_name or 'unknown',
                'regime': sig.regime or 'unknown',
                'strength': _safe_float(getattr(sig, 'strength', 0)),
                'ml_probability': _safe_float(getattr(sig, 'ml_probability', 0)),
                'price_velocity_3': float(vel3),
                'price_velocity_5': float(vel5),
                'price_velocity_10': float(vel10),
                'price_acceleration_3_10': float(vel3 - vel10),
                'atr_rel': float(atr_rel),
                'atr_regime': float(atr_regime),
                'relative_volume': float(rel_vol),
                'mtf_4h_trend': float(mtf_4h_trend),
                'mtf_1d_trend': float(mtf_1d_trend),
                'funding_rate': _safe_float(meta.get('funding_rate', 0.0)),
                'open_interest_change': _safe_float(meta.get('open_interest_change', 0.0)),
                'asset_class_enc': _safe_float(meta.get('asset_class_enc', 0.0)),
                'dxy_trend': _safe_float(macro.get('dxy_trend', meta.get('dxy_trend', 0.0))),
                'vix_trend': _safe_float(macro.get('vix_trend', meta.get('vix_trend', 0.0))),
                'us10y_trend': _safe_float(macro.get('us10y_trend', meta.get('us10y_trend', 0.0))),
                'yield_spread': _safe_float(macro.get('yield_spread', meta.get('yield_spread', 0.0))),
                'minutes_since_high_impact_news': _safe_float(macro.get('minutes_since_high_impact_news', meta.get('minutes_since_high_impact_news', 0.0))),
                'minutes_until_high_impact_news': _safe_float(macro.get('minutes_until_high_impact_news', meta.get('minutes_until_high_impact_news', 0.0))),
                'news_event_impact_score': _safe_float(macro.get('news_event_impact_score', meta.get('news_event_impact_score', 0.0))),
                'spx_trend': _safe_float(macro.get('spx_trend', meta.get('spx_trend', 0.0))),
                'btc_corr': _safe_float(macro.get('btc_corr', meta.get('btc_corr', 0.0))),
                'partial_tp_progress': float(tp_progress),
                'false_breakout': int(false_breakout),
                'barrier_type': barrier,
                'sample_weight': float(sample_weight),
                'created_at': created_at,
                'target': target,
            }
            data.append(row)

        # Also include persisted historical archive samples so training can
        # blend legacy and fresh post-reset outcomes.
        try:
            from db.models import MLPastTrainingData
            from sqlalchemy import text

            async with get_session() as session:
                # Defensive bootstrap for environments where bot schema ensure
                # has not run yet (e.g. webhook startup race).
                session.execute(text(
                    """
                    CREATE TABLE IF NOT EXISTS ml_past_training_data (
                        id SERIAL PRIMARY KEY,
                        signal_id VARCHAR(36) UNIQUE NOT NULL,
                        asset VARCHAR(32) NOT NULL,
                        timeframe VARCHAR(8) NOT NULL,
                        direction VARCHAR(8) NOT NULL,
                        entry DOUBLE PRECISION NOT NULL,
                        stop_loss DOUBLE PRECISION NOT NULL,
                        take_profit TEXT NOT NULL,
                        rr_estimate DOUBLE PRECISION NULL,
                        score DOUBLE PRECISION NULL,
                        strength DOUBLE PRECISION NULL,
                        regime VARCHAR(32) NULL,
                        strategy_name VARCHAR(64) NULL,
                        ml_probability DOUBLE PRECISION NULL,
                        outcome_status VARCHAR(16) NOT NULL,
                        outcome_r_multiple DOUBLE PRECISION NULL,
                        outcome_percent DOUBLE PRECISION NULL,
                        outcome_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
                        signal_created_at TIMESTAMP NULL,
                        outcome_closed_at TIMESTAMP NULL,
                        archived_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """
                ))
                archive_rows = (
                    await session.execute(
                        select(MLPastTrainingData).where(MLPastTrainingData.signal_created_at >= cutoff)
                    )
                ).scalars().all()
                session.commit()

            for a in archive_rows:
                status = str(getattr(a, 'outcome_status', '') or '').lower()
                meta = getattr(a, 'outcome_meta', None) or {}
                if not isinstance(meta, dict):
                    meta = {}
                macro = dict(meta.get('macro') or {})

                tp_progress = 0
                for key in ("tp_progress", "max_tp_hit", "tp_hit_count", "highest_tp_reached"):
                    try:
                        tp_progress = max(tp_progress, int(meta.get(key) or 0))
                    except Exception:
                        continue

                false_breakout = 0
                for k in ("false_breakout", "volatility_stopout", "sl_then_tp1", "post_sl_reversal_to_tp1"):
                    try:
                        if bool(meta.get(k)):
                            false_breakout = 1
                            break
                    except Exception:
                        continue

                if status in ("tp", "tp1", "tp2", "tp3", "partial_tp"):
                    barrier = "upper"
                elif status in ("expired", "timeout", "time", "time_expired"):
                    barrier = "time"
                else:
                    barrier = "lower"

                target = 1 if barrier == "upper" else 0
                sample_weight = 1.0
                if status in ("tp", "tp3"):
                    sample_weight = 1.30
                    tp_progress = max(tp_progress, 3)
                elif status == "tp2":
                    sample_weight = 1.15
                    tp_progress = max(tp_progress, 2)
                elif status in ("tp1", "partial_tp"):
                    sample_weight = 1.05
                    tp_progress = max(tp_progress, 1)
                elif barrier == "time":
                    sample_weight = 0.85
                elif status == "sl":
                    if tp_progress >= 2:
                        sample_weight = 0.55
                    elif tp_progress >= 1:
                        sample_weight = 0.70

                if false_breakout:
                    sample_weight *= 0.65

                rr_raw = _safe_float(getattr(a, 'rr_estimate', 0))
                rr_eff = min(4.0, max(0.5, rr_raw))
                sample_weight *= (0.75 + (rr_eff / 4.0))

                a_take_profit = _parse_tp(getattr(a, 'take_profit', 0))
                a_entry = _safe_float(getattr(a, 'entry', 0))
                a_sl = _safe_float(getattr(a, 'stop_loss', 0))

                data.append({
                    'signal_id': getattr(a, 'signal_id', None),
                    'asset': getattr(a, 'asset', 'UNKNOWN') or 'UNKNOWN',
                    'timeframe': getattr(a, 'timeframe', '1h') or '1h',
                    'direction': getattr(a, 'direction', 'long') or 'long',
                    'score': _safe_float(getattr(a, 'score', 0)),
                    'entry': a_entry,
                    'stop_loss': a_sl,
                    'take_profit': a_take_profit,
                    'rr_ratio': _safe_float(getattr(a, 'rr_estimate', 0)),
                    'strategy_name': getattr(a, 'strategy_name', 'unknown') or 'unknown',
                    'regime': getattr(a, 'regime', 'unknown') or 'unknown',
                    'strength': _safe_float(getattr(a, 'strength', 0)),
                    'ml_probability': _safe_float(getattr(a, 'ml_probability', 0)),
                    'price_velocity_3': _safe_float(meta.get('price_velocity_3', 0.0)),
                    'price_velocity_5': _safe_float(meta.get('price_velocity_5', 0.0)),
                    'price_velocity_10': _safe_float(meta.get('price_velocity_10', 0.0)),
                    'price_acceleration_3_10': _safe_float(meta.get('price_acceleration_3_10', 0.0)),
                    'atr_rel': _safe_float(meta.get('atr_rel', 0.0)),
                    'atr_regime': _safe_float(meta.get('atr_regime', 0.0)),
                    'relative_volume': _safe_float(meta.get('relative_volume', 0.0)),
                    'mtf_4h_trend': _safe_float(meta.get('mtf_4h_trend', 0.0)),
                    'mtf_1d_trend': _safe_float(meta.get('mtf_1d_trend', 0.0)),
                    'funding_rate': _safe_float(meta.get('funding_rate', 0.0)),
                    'open_interest_change': _safe_float(meta.get('open_interest_change', 0.0)),
                    'asset_class_enc': _safe_float(meta.get('asset_class_enc', 0.0)),
                    'dxy_trend': _safe_float(macro.get('dxy_trend', meta.get('dxy_trend', 0.0))),
                    'vix_trend': _safe_float(macro.get('vix_trend', meta.get('vix_trend', 0.0))),
                    'us10y_trend': _safe_float(macro.get('us10y_trend', meta.get('us10y_trend', 0.0))),
                    'yield_spread': _safe_float(macro.get('yield_spread', meta.get('yield_spread', 0.0))),
                    'minutes_since_high_impact_news': _safe_float(macro.get('minutes_since_high_impact_news', meta.get('minutes_since_high_impact_news', 0.0))),
                    'minutes_until_high_impact_news': _safe_float(macro.get('minutes_until_high_impact_news', meta.get('minutes_until_high_impact_news', 0.0))),
                    'news_event_impact_score': _safe_float(macro.get('news_event_impact_score', meta.get('news_event_impact_score', 0.0))),
                    'spx_trend': _safe_float(macro.get('spx_trend', meta.get('spx_trend', 0.0))),
                    'btc_corr': _safe_float(macro.get('btc_corr', meta.get('btc_corr', 0.0))),
                    'partial_tp_progress': float(tp_progress),
                    'false_breakout': int(false_breakout),
                    'barrier_type': barrier,
                    'sample_weight': float(sample_weight),
                    'created_at': getattr(a, 'signal_created_at', None) or datetime.utcnow(),
                    'target': target,
                })
        except Exception as _archive_err:
            logger.warning(f"Failed to load archive training rows: {_archive_err}")

        # Include threshold-rejected/non-issued signals that were later outcome-tracked.
        # This lets the model learn from decisions that did not pass issuance gates.
        try:
            from sqlalchemy import and_

            async with get_session() as session:
                rejected_rows = (
                    session.execute(
                        select(MLRejectedSignal).where(
                            and_(
                                MLRejectedSignal.created_at >= cutoff,
                                MLRejectedSignal.outcome_tracked_at.is_not(None),
                            )
                        )
                    )
                ).scalars().all()

            for rj in rejected_rows:
                outcome = str(getattr(rj, "actual_outcome", "") or "").lower().strip()
                if outcome not in {"win", "loss"}:
                    continue

                feat = getattr(rj, "features", None) or {}
                if not isinstance(feat, dict):
                    feat = {}
                macro = dict(feat.get("macro") or {})

                tp_progress = 0
                for key in ("tp_progress", "max_tp_hit", "tp_hit_count", "highest_tp_reached"):
                    try:
                        tp_progress = max(tp_progress, int(feat.get(key) or 0))
                    except Exception:
                        continue

                false_breakout = 0
                for k in ("false_breakout", "volatility_stopout", "sl_then_tp1", "post_sl_reversal_to_tp1"):
                    try:
                        if bool(feat.get(k)):
                            false_breakout = 1
                            break
                    except Exception:
                        continue

                barrier = "upper" if outcome == "win" else "lower"
                target = 1 if barrier == "upper" else 0
                sample_weight = 1.0 if target == 1 else 0.9
                if false_breakout:
                    sample_weight *= 0.75

                rr_raw = _safe_float(feat.get("rr_ratio"))
                if rr_raw <= 0:
                    rr_raw = _safe_float(feat.get("rr_estimate", 0))
                rr_eff = min(4.0, max(0.5, rr_raw)) if rr_raw > 0 else 1.0
                sample_weight *= (0.75 + (rr_eff / 4.0))

                data.append(
                    {
                        "signal_id": f"rejected_{int(getattr(rj, 'id', 0))}",
                        "asset": getattr(rj, "asset", "UNKNOWN") or "UNKNOWN",
                        "timeframe": getattr(rj, "timeframe", "1h") or "1h",
                        "direction": getattr(rj, "direction", "long") or "long",
                        "score": _safe_float(feat.get("score", 0)),
                        "entry": _safe_float(getattr(rj, "entry", 0)),
                        "stop_loss": _safe_float(getattr(rj, "stop_loss", 0)),
                        "take_profit": _parse_tp(getattr(rj, "take_profit", 0)),
                        "rr_ratio": rr_raw,
                        "strategy_name": str(feat.get("strategy_name") or "rejected"),
                        "regime": str(feat.get("regime") or "unknown"),
                        "strength": _safe_float(feat.get("strength", 0)),
                        "ml_probability": _safe_float(getattr(rj, "ml_probability", 0)),
                        "price_velocity_3": _safe_float(feat.get("price_velocity_3", 0.0)),
                        "price_velocity_5": _safe_float(feat.get("price_velocity_5", 0.0)),
                        "price_velocity_10": _safe_float(feat.get("price_velocity_10", 0.0)),
                        "price_acceleration_3_10": _safe_float(feat.get("price_acceleration_3_10", 0.0)),
                        "atr_rel": _safe_float(feat.get("atr_rel", 0.0)),
                        "atr_regime": _safe_float(feat.get("atr_regime", 0.0)),
                        "relative_volume": _safe_float(feat.get("relative_volume", 0.0)),
                        "mtf_4h_trend": _safe_float(feat.get("mtf_4h_trend", 0.0)),
                        "mtf_1d_trend": _safe_float(feat.get("mtf_1d_trend", 0.0)),
                        "funding_rate": _safe_float(feat.get("funding_rate", 0.0)),
                        "open_interest_change": _safe_float(feat.get("open_interest_change", 0.0)),
                        "asset_class_enc": _safe_float(feat.get("asset_class_enc", 0.0)),
                        "dxy_trend": _safe_float(macro.get("dxy_trend", feat.get("dxy_trend", 0.0))),
                        "vix_trend": _safe_float(macro.get("vix_trend", feat.get("vix_trend", 0.0))),
                        "us10y_trend": _safe_float(macro.get("us10y_trend", feat.get("us10y_trend", 0.0))),
                        "yield_spread": _safe_float(macro.get("yield_spread", feat.get("yield_spread", 0.0))),
                        "minutes_since_high_impact_news": _safe_float(macro.get("minutes_since_high_impact_news", feat.get("minutes_since_high_impact_news", 0.0))),
                        "minutes_until_high_impact_news": _safe_float(macro.get("minutes_until_high_impact_news", feat.get("minutes_until_high_impact_news", 0.0))),
                        "news_event_impact_score": _safe_float(macro.get("news_event_impact_score", feat.get("news_event_impact_score", 0.0))),
                        "spx_trend": _safe_float(macro.get("spx_trend", feat.get("spx_trend", 0.0))),
                        "btc_corr": _safe_float(macro.get("btc_corr", feat.get("btc_corr", 0.0))),
                        "partial_tp_progress": float(tp_progress),
                        "false_breakout": int(false_breakout),
                        "barrier_type": barrier,
                        "sample_weight": float(sample_weight),
                        "created_at": getattr(rj, "created_at", None) or datetime.utcnow(),
                        "target": target,
                    }
                )
        except Exception as rejected_err:
            logger.warning(f"Failed to load rejected-signal training rows: {rejected_err}")

        df = pd.DataFrame(data)
        logger.info(f"Loaded {len(df)} signals with outcomes")
        logger.info(f"Class distribution: {df['target'].value_counts().to_dict()}")
        return df

    except Exception as e:
        logger.error(f"Failed to load training data: {e}", exc_info=True)
        return None


def engineer_features(df):
    """Build feature matrix with domain-specific features."""
    X = df.copy()

    # Encode categorical features
    le_direction = LabelEncoder()
    le_regime = LabelEncoder()
    le_strategy = LabelEncoder()
    le_asset = LabelEncoder()
    le_timeframe = LabelEncoder()

    X['direction_enc'] = le_direction.fit_transform(X['direction'].fillna('long'))
    X['regime_enc'] = le_regime.fit_transform(X['regime'].fillna('neutral'))
    X['strategy_enc'] = le_strategy.fit_transform(X['strategy_name'].fillna('unknown'))
    X['asset_enc'] = le_asset.fit_transform(X['asset'].fillna('UNKNOWN'))
    X['timeframe_enc'] = le_timeframe.fit_transform(X['timeframe'].fillna('1d'))

    # Domain features
    X['risk_reward_ratio'] = X['rr_ratio'].fillna(1.0)
    X['score_normalized'] = X['score'] / 100.0
    X['price_range'] = (X['take_profit'] - X['entry']).abs() / (X['entry'] + 1e-6)
    X['risk_amount'] = (X['entry'] - X['stop_loss']).abs() / (X['entry'] + 1e-6)
    X['spread_ratio'] = X['risk_amount'] / (X['price_range'] + 1e-6)
    X['strength_normalized'] = X['strength'] / 100.0 if X['strength'].max() > 1 else X['strength']
    # FIX: Removed partial_tp_progress_norm - this feature leaks the trade outcome (whether TP was hit)
    # into training data, causing data leakage/lookahead bias and fake 100% accuracy
    # X['partial_tp_progress_norm'] = X['partial_tp_progress'].fillna(0.0) / 3.0
    X['velocity_abs_3'] = X['price_velocity_3'].abs()
    X['velocity_abs_10'] = X['price_velocity_10'].abs()
    X['atr_regime_clamped'] = X['atr_regime'].clip(lower=0.0, upper=5.0)
    X['relative_volume_clamped'] = X['relative_volume'].clip(lower=0.0, upper=10.0)

    # Score bins
    X['high_score'] = (X['score'] >= 75).astype(int)
    X['medium_score'] = ((X['score'] >= 60) & (X['score'] < 75)).astype(int)

    # Direction bias
    X['is_long'] = (X['direction'].str.lower() == 'long').astype(int)

# Feature selection for model
    # BUG FIX: Removed partial_tp_progress_norm to prevent data leakage (lookahead bias)
    # This feature tracks whether a trade hit TP, which leaks the outcome into training data
    feature_cols = [
        'score_normalized', 'risk_reward_ratio', 'price_range', 'risk_amount',
        'spread_ratio', 'strength_normalized', 'direction_enc', 'regime_enc',
        'strategy_enc', 'high_score', 'medium_score', 'is_long', 'asset_class_enc',
        # 'partial_tp_progress_norm',  # REMOVED - causes data leakage/lookahead bias
        'price_velocity_3', 'price_velocity_5', 'price_velocity_10',
        'price_acceleration_3_10', 'velocity_abs_3', 'velocity_abs_10',
        'atr_rel', 'atr_regime_clamped', 'relative_volume_clamped',
        'mtf_4h_trend', 'mtf_1d_trend',
        'funding_rate', 'open_interest_change', 'dxy_trend', 'vix_trend', 'us10y_trend', 'yield_spread', 'minutes_since_high_impact_news', 'minutes_until_high_impact_news', 'news_event_impact_score', 'spx_trend', 'btc_corr',
    ]

    X_train = X[feature_cols].fillna(0.0).astype(np.float32)
    y_train = X['target'].astype(np.int32)
    sample_weights = X['sample_weight'].fillna(1.0).astype(np.float32)

    # Recency bias: exponentially emphasize recent outcomes (rolling market adaptation).
    try:
        ts = pd.to_datetime(X['created_at'], errors='coerce')
        newest = ts.max()
        if pd.notna(newest):
            age_days = (newest - ts).dt.total_seconds().fillna(0.0) / 86400.0
            half_life_days = float(os.getenv('ML_RECENCY_HALF_LIFE_DAYS', '90') or 90)
            decay = np.exp(-np.log(2.0) * (age_days / max(1.0, half_life_days)))
            recency_multiplier = 0.6 + (0.9 * decay)
            sample_weights = (sample_weights * recency_multiplier.astype(np.float32)).astype(np.float32)
    except Exception:
        pass

    timestamps = pd.to_datetime(X['created_at'], errors='coerce')

    return X_train, y_train, feature_cols, sample_weights, timestamps


def train_model(X_train, y_train, feature_cols, sample_weights=None, timestamps=None):
    """Train XGBoost classifier and check for drift."""
    logger.info("Training XGBoost model...")

    # Time-series split: train on past, validate on immediate future.
    n = len(X_train)
    if n < 20:
        raise ValueError("Insufficient rows for time-series training")
    idx = np.arange(n)
    if timestamps is not None:
        ts = pd.to_datetime(timestamps, errors='coerce')
        ts_filled = ts.fillna(pd.Timestamp(datetime.utcnow()))
        idx = np.argsort(ts_filled.values)

    split = max(1, int(n * 0.8))
    idx_tr = idx[:split]
    idx_te = idx[split:] if split < n else idx[max(0, n - 1):]

    X_tr, X_te = X_train.iloc[idx_tr], X_train.iloc[idx_te]
    y_tr, y_te = y_train.iloc[idx_tr], y_train.iloc[idx_te]
    w_tr = None
    if sample_weights is not None:
        w_tr = np.asarray(sample_weights.iloc[idx_tr], dtype=np.float32)

    # Train model
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        objective='binary:logistic',
        random_state=42,
        verbosity=1,
    )
    model.fit(X_tr, y_tr, sample_weight=w_tr, eval_set=[(X_te, y_te)], verbose=False)

    # Evaluate
    y_pred = model.predict(X_te)
    y_proba = model.predict_proba(X_te)[:, 1]
    calibration_x = []
    calibration_y = []
    try:
        if len(np.unique(y_proba)) >= 2 and len(np.unique(y_te)) >= 2:
            calibrator = IsotonicRegression(out_of_bounds='clip')
            calibrator.fit(y_proba, y_te)
            calibration_x = [float(x) for x in getattr(calibrator, 'X_thresholds_', [])]
            calibration_y = [float(y) for y in getattr(calibrator, 'y_thresholds_', [])]
    except Exception as exc:
        logger.warning("Calibration fitting skipped: %s", exc)

    acc = accuracy_score(y_te, y_pred)
    try:
        auc = roc_auc_score(y_te, y_proba)
    except Exception:
        auc = 0.5

    logger.info(f"Test Accuracy: {acc:.4f}")
    logger.info(f"Test AUC: {auc:.4f}")

    # FIX: Store AUC in Redis for dynamic threshold calculation
    # This enables the engine to auto-adjust threshold based on ML model performance
    try:
        import redis as _redis_client
        import os as _os_env
        
        _redis_url = _os_env.getenv("REDIS_URL")
        if _redis_url:
            _r = _redis_client.from_url(_redis_url, decode_responses=True)
            _r.set("ml:model:auc", float(auc))
            _r.set("ml:model:auc:last_updated", datetime.utcnow().isoformat())
            _r.close()
            logger.info(f"[ml] Stored AUC={auc:.4f} in Redis for dynamic threshold")
    except Exception as _e:
        logger.debug(f"[ml] Failed to store AUC in Redis: {_e}")
    logger.info(f"Confusion Matrix:\n{confusion_matrix(y_te, y_pred)}")
    logger.info(f"Classification Report:\n{classification_report(y_te, y_pred)}")

    # Drift detection: compare with last run (if available)
    drift_path = Path(__file__).parent / "ml_drift.json"
    drift = {}
    try:
        if drift_path.exists():
            with open(drift_path, "r") as f:
                drift = json.load(f)
        prev_acc = float(drift.get("accuracy", 0))
        prev_auc = float(drift.get("auc", 0))
        acc_drop = prev_acc - acc
        auc_drop = prev_auc - auc
        if acc_drop > 0.05 or auc_drop > 0.05:
            logger.warning(f"[ML DRIFT] Accuracy or AUC dropped significantly! Δacc={acc_drop:.3f}, Δauc={auc_drop:.3f}")
            print(f"[ML DRIFT] Accuracy or AUC dropped! Δacc={acc_drop:.3f}, Δauc={auc_drop:.3f}", flush=True)
        # Feature distribution drift (simple mean diff)
        prev_means = drift.get("feature_means", {})
        means = {k: float(v) for k, v in X_train.mean().items()}
        drifted = []
        for k, v in means.items():
            prev = float(prev_means.get(k, v))
            if abs(v - prev) > 0.1 * (abs(prev) + 1e-6):
                drifted.append(k)
        if drifted:
            logger.warning(f"[ML DRIFT] Feature(s) drifted: {drifted}")
            print(f"[ML DRIFT] Feature(s) drifted: {drifted}", flush=True)
        drift = {"accuracy": float(acc), "auc": float(auc), "feature_means": means}
        with open(drift_path, "w") as f:
            json.dump(drift, f, indent=2)
    except Exception as e:
        logger.warning(f"[ML DRIFT] Drift check failed: {e}")

    # Feature importance
    importance = dict(zip(feature_cols, model.feature_importances_))
    logger.info(f"Top features: {sorted(importance.items(), key=lambda x: x[1], reverse=True)[:5]}")

    return model, feature_cols, calibration_x, calibration_y


def save_model(model, feature_cols, calibration_x=None, calibration_y=None, training_meta=None):
    """Save model to JSON."""
    model_path = Path(__file__).parent / "model.json"
    
    # Save model as ubj (XGBoost binary JSON) - avoids format warnings
    import base64
    booster = model.get_booster()
    model_bytes = booster.save_raw('ubj')  # Binary format, no warnings
    
    artifact_hash_sha256 = hashlib.sha256(model_bytes).hexdigest()
    model_dict = {
        "type": "xgboost",
        "version": os.getenv("ML_MODEL_VERSION", "1.0.0"),
        "feature_cols": feature_cols,
        "model_bytes_b64": base64.b64encode(model_bytes).decode('utf-8'),
        "trained_at": datetime.utcnow().isoformat(),
        "xgboost_version": getattr(xgb, "__version__", ""),
        "artifact_hash_sha256": artifact_hash_sha256,
        "calibration_kind": "isotonic" if calibration_x and calibration_y else "none",
        "calibration_x": calibration_x or [],
        "calibration_y": calibration_y or [],
        "training_meta": dict(training_meta or {}),
    }

    with open(model_path, 'w') as f:
        json.dump(model_dict, f, indent=2)

    logger.info(f"Model saved to {model_path}")
    return model_path


async def main(lookback_days: int | None = None):
    logger.info("Starting ML model training...")

    if lookback_days is None:
        try:
            lookback_days = int(os.getenv("ML_TRAIN_LOOKBACK_DAYS", "90") or 90)
        except Exception:
            lookback_days = 90

    # Load data
    df = await load_training_data(int(lookback_days or 90))
    min_rows = int(os.getenv("ML_MIN_TRAIN_ROWS", "10") or 10)
    bootstrap_enabled = _env_bool("ML_OFFLINE_BOOTSTRAP_ENABLED", True)
    bootstrap_rows = int(os.getenv("ML_OFFLINE_BOOTSTRAP_ROWS", "1200") or 1200)
    used_bootstrap = False
    source_rows = int(len(df)) if df is not None else 0

    if (df is None or len(df) < min_rows) and bootstrap_enabled:
        boot = _generate_offline_bootstrap_data(max(bootstrap_rows, min_rows))
        used_bootstrap = True
        if df is None or len(df) == 0:
            df = boot
        else:
            df = pd.concat([df, boot], ignore_index=True)
        logger.warning("Bootstrap augmentation applied: source_rows=%s total_rows=%s", source_rows, len(df))

    if df is None or len(df) < min_rows:
        logger.error("Insufficient training data (need >= %s rows)", min_rows)
        return False

    # Engineer features
    X_train, y_train, feature_cols, sample_weights, timestamps = engineer_features(df)
    logger.info(f"Features engineered: {feature_cols}")
    logger.info(f"Training set shape: {X_train.shape}")

    # Train model
    model, feature_cols, calibration_x, calibration_y = train_model(
        X_train,
        y_train,
        feature_cols,
        sample_weights=sample_weights,
        timestamps=timestamps,
    )

    # Save model
    save_model(
        model,
        feature_cols,
        calibration_x=calibration_x,
        calibration_y=calibration_y,
        training_meta={
            "offline_bootstrap_used": bool(used_bootstrap),
            "source_rows": int(source_rows),
            "total_rows": int(len(df)),
        },
    )

    logger.info("✅ Model training complete!")
    return True


if __name__ == "__main__":
    import asyncio
    from utils.async_runner import run_sync
    success = run_sync(main())
    sys.exit(0 if success else 1)
