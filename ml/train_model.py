#!/usr/bin/env python
"""
Train XGBoost model from existing signal history.
Loads signals + outcomes from Postgres, builds feature matrix, trains model.
"""
from utils.timeutils import now_utc_naive

import os
import asyncio
import hashlib
import sys
import json
import logging
import math
import tempfile
from bisect import bisect_right
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


def _training_db_priority() -> str:
    value = str(os.getenv("ML_TRAINING_DB_PRIORITY") or "background").strip().lower()
    return value if value in {"interactive", "critical", "background", "analytics"} else "background"


def _training_db_timeout() -> float:
    try:
        return max(5.0, float(os.getenv("ML_TRAINING_DB_TIMEOUT_SECONDS", "30") or 30))
    except Exception:
        return 30.0


def _training_session_kwargs(label: str) -> dict:
    return {
        "priority": _training_db_priority(),
        "label": label,
        "timeout_seconds": _training_db_timeout(),
        # ML snapshots are durable maintenance work. They may wait for the
        # non-reserved pool portion but can never consume foreground-reserved
        # sessions used by Telegram commands and delivery writes.
        "drop_if_busy": False,
    }


def _is_production_runtime() -> bool:
    """Return True where synthetic ML artefacts are unsafe."""
    app_env = str(
        os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or os.getenv("RAILWAY_ENVIRONMENT_NAME")
        or os.getenv("RAILWAY_ENVIRONMENT")
        or ""
    ).strip().lower()
    if app_env in {"production", "prod", "staging", "stage"}:
        return True
    return any(
        bool((os.getenv(name) or "").strip())
        for name in (
            "RAILWAY_SERVICE_ID",
            "RAILWAY_DEPLOYMENT_ID",
            "RAILWAY_PROJECT_ID",
            "RAILWAY_SERVICE_NAME",
        )
    )


def _offline_bootstrap_allowed() -> bool:
    """Synthetic rows are opt-in and can never replace a Railway model."""
    explicit = os.getenv("ML_OFFLINE_BOOTSTRAP_ENABLED")
    if explicit is not None:
        requested = _env_bool("ML_OFFLINE_BOOTSTRAP_ENABLED", False)
    else:
        app_env = str(os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "").strip().lower()
        requested = app_env in {"local", "development", "dev", "test", "testing"}
    return bool(requested and not _is_production_runtime())


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
    now = now_utc_naive()

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


async def load_training_data(lookback_days: int = 90):
    """Load signals + outcomes from Postgres."""
    try:
        from db.session import get_session

        from db.models import Signal, Outcome, SignalDelivery, MarketCandle, MLRejectedSignal, PaperPosition
        from sqlalchemy import select, desc, exists, func

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

        candle_cache: dict[tuple[str, str], tuple[list[int], list[object]]] = {}

        async def _load_candles(symbol: str, timeframe: str, created_at: datetime, limit: int = 80):
            if not symbol or not timeframe or not created_at:
                return []
            key = (str(symbol).upper(), str(timeframe).lower())
            cached = candle_cache.get(key)
            if cached is None:
                max_rows = max(500, min(100000, int(os.getenv("ML_CANDLE_CACHE_MAX_ROWS_PER_SERIES", "40000") or 40000)))
                async with get_session(**_training_session_kwargs("ml_training_candle_read")) as candle_session:
                    q = (
                        select(MarketCandle)
                        .where(
                            MarketCandle.symbol == key[0],
                            MarketCandle.timeframe == key[1],
                        )
                        .order_by(desc(MarketCandle.open_time_ms))
                        .limit(max_rows)
                    )
                    res = await candle_session.execute(q)
                    all_rows = list(res.scalars().all())
                all_rows.reverse()
                open_times = [int(getattr(row, "open_time_ms", 0) or 0) for row in all_rows]
                cached = (open_times, all_rows)
                candle_cache[key] = cached
            open_times, all_rows = cached
            cutoff_ms = int(created_at.timestamp() * 1000)
            stop = bisect_right(open_times, cutoff_ms)
            return all_rows[max(0, stop - max(1, int(limit))):stop]

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

        async with get_session(**_training_session_kwargs("ml_training_live_outcomes_read")) as session:
            # Get signals delivered in the requested lookback window with outcomes
            cutoff_days = max(1, int(lookback_days or 90))
            cutoff = now_utc_naive() - timedelta(days=cutoff_days)

            delivered_proof = exists().where(
                SignalDelivery.signal_id == Signal.signal_id,
                SignalDelivery.sent_ok.is_(True),
                SignalDelivery.delivery_state.in_((
                    "sent", "delivered", "confirmed", "reconciled",
                    "SENT", "DELIVERED", "CONFIRMED", "RECONCILED",
                )),
                SignalDelivery.telegram_chat_id.is_not(None),
                SignalDelivery.telegram_message_id.is_not(None),
            )
            stmt = (
                select(Signal, Outcome)
                .join(Outcome, Outcome.signal_id == Signal.signal_id)
                .where(Signal.created_at >= cutoff, delivered_proof)
            )
            try:
                res = await session.execute(stmt)
                rows = list(res.all())
            except Exception as exc:
                # Live proof is the strongest source, but a temporary query or
                # schema issue must not prevent archive, shadow, and paper
                # evidence from producing a candidate model. Promotion remains
                # gated by ML_MIN_LIVE_PROOF_ROWS below.
                logger.warning(
                    "Live ML data unavailable; continuing with secondary evidence: %s",
                    exc,
                )
                rows = []

        if not rows:
            logger.warning(
                "No delivery-proof-backed live outcomes found; loading archive, shadow, and paper evidence"
            )

        live_proof_rows = len(rows)
        data = []
        for sig, outcome in rows:
            status = str(getattr(outcome, 'status', '') or '').lower()
            meta = getattr(outcome, 'meta', None) or {}
            if not isinstance(meta, dict):
                meta = {}
            macro = dict(meta.get('macro') or {})

            created_at = getattr(sig, 'created_at', None) or now_utc_naive()
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
                'source_type': 'live_delivery',
                'source_weight': 1.0,
                'created_at': created_at,
                'target': target,
            }
            data.append(row)

        # Also include persisted historical archive samples so training can
        # blend legacy and fresh post-reset outcomes.
        try:
            from db.models import MLPastTrainingData
            from sqlalchemy import text

            async with get_session(**_training_session_kwargs("ml_training_archive_read")) as session:
                # Defensive bootstrap for environments where bot schema ensure
                # has not run yet (e.g. webhook startup race).
                await session.execute(text(
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
                await session.commit()

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
                archive_proof = bool(getattr(a, 'delivery_proof_backed', False))
                archive_source_weight = 0.80 if archive_proof else 0.25
                sample_weight *= archive_source_weight

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
                    'source_type': 'archive_proof' if archive_proof else 'archive_legacy',
                    'source_weight': float(archive_source_weight),
                    'created_at': getattr(a, 'signal_created_at', None) or now_utc_naive(),
                    'target': target,
                })
        except Exception as _archive_err:
            logger.warning(f"Failed to load archive training rows: {_archive_err}")

        # Include threshold-rejected/non-issued signals that were later outcome-tracked.
        # This lets the model learn from decisions that did not pass issuance gates.
        try:
            from sqlalchemy import and_

            async with get_session(**_training_session_kwargs("ml_training_rejections_read")) as session:
                rejected_rows = (
                    await session.execute(
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
                sample_weight = (1.0 if target == 1 else 0.9) * 0.60
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
                        "source_type": "shadow_rejected",
                        "source_weight": 0.60,
                        "created_at": getattr(rj, "created_at", None) or now_utc_naive(),
                        "target": target,
                    }
                )
        except Exception as rejected_err:
            logger.warning(f"Failed to load rejected-signal training rows: {rejected_err}")

        # Include one closed paper execution per signal only when the same
        # signal is not already represented by stronger live/archive evidence.
        # Paper fills are useful for execution-aware learning but remain
        # deliberately lower weight than confirmed live outcomes.
        try:
            existing_signal_ids = {str(item.get("signal_id") or "") for item in data}
            async with get_session(**_training_session_kwargs("ml_training_paper_read")) as session:
                paper_result = await session.execute(
                    select(PaperPosition, Signal)
                    .join(Signal, Signal.signal_id == PaperPosition.signal_id)
                    .where(
                        PaperPosition.closed_at.is_not(None),
                        PaperPosition.closed_at >= cutoff,
                        func.lower(PaperPosition.status).in_(("closed", "complete", "completed")),
                    )
                    .order_by(desc(PaperPosition.closed_at))
                )
                paper_pairs = list(paper_result.all())

            paper_by_signal = {}
            for position, sig in paper_pairs:
                sid = str(getattr(position, "signal_id", "") or "")
                if not sid or sid in existing_signal_ids or sid in paper_by_signal:
                    continue
                paper_by_signal[sid] = (position, sig)

            for sid, (position, sig) in paper_by_signal.items():
                exit_reason = str(getattr(position, "exit_reason", "") or "").lower()
                r_multiple = _safe_float(getattr(position, "r_multiple", 0.0))
                if any(token in exit_reason for token in ("tp", "target", "take_profit")):
                    target = 1
                    barrier = "upper"
                elif any(token in exit_reason for token in ("sl", "stop")):
                    target = 0
                    barrier = "lower"
                elif r_multiple != 0:
                    target = 1 if r_multiple > 0 else 0
                    barrier = "upper" if target else "lower"
                else:
                    continue
                meta = getattr(position, "meta", None) or {}
                if not isinstance(meta, dict):
                    meta = {}
                rr_raw = _safe_float(getattr(sig, "rr_estimate", 0.0))
                paper_weight = 0.35 * min(1.25, max(0.50, 0.75 + min(4.0, max(0.5, rr_raw or 1.0)) / 4.0))
                data.append({
                    "signal_id": sid,
                    "asset": getattr(sig, "asset", None) or getattr(position, "asset", "UNKNOWN"),
                    "timeframe": getattr(sig, "timeframe", None) or getattr(position, "timeframe", "1h") or "1h",
                    "direction": getattr(sig, "direction", None) or getattr(position, "direction", "long"),
                    "score": _safe_float(getattr(sig, "score", 0)),
                    "entry": _safe_float(getattr(sig, "entry", getattr(position, "signal_entry", 0))),
                    "stop_loss": _safe_float(getattr(sig, "stop_loss", getattr(position, "stop_loss", 0))),
                    "take_profit": _parse_tp(getattr(sig, "take_profit", getattr(position, "take_profits", 0))),
                    "rr_ratio": rr_raw,
                    "strategy_name": getattr(sig, "strategy_name", "paper") or "paper",
                    "regime": getattr(sig, "regime", "unknown") or "unknown",
                    "strength": _safe_float(getattr(sig, "strength", 0)),
                    "ml_probability": _safe_float(getattr(sig, "ml_probability", 0)),
                    "price_velocity_3": _safe_float(meta.get("price_velocity_3", 0.0)),
                    "price_velocity_5": _safe_float(meta.get("price_velocity_5", 0.0)),
                    "price_velocity_10": _safe_float(meta.get("price_velocity_10", 0.0)),
                    "price_acceleration_3_10": _safe_float(meta.get("price_acceleration_3_10", 0.0)),
                    "atr_rel": _safe_float(meta.get("atr_rel", 0.0)),
                    "atr_regime": _safe_float(meta.get("atr_regime", 0.0)),
                    "relative_volume": _safe_float(meta.get("relative_volume", 0.0)),
                    "mtf_4h_trend": _safe_float(meta.get("mtf_4h_trend", 0.0)),
                    "mtf_1d_trend": _safe_float(meta.get("mtf_1d_trend", 0.0)),
                    "funding_rate": _safe_float(meta.get("funding_rate", 0.0)),
                    "open_interest_change": _safe_float(meta.get("open_interest_change", 0.0)),
                    "asset_class_enc": _safe_float(meta.get("asset_class_enc", 0.0)),
                    "dxy_trend": _safe_float(meta.get("dxy_trend", 0.0)),
                    "vix_trend": _safe_float(meta.get("vix_trend", 0.0)),
                    "us10y_trend": _safe_float(meta.get("us10y_trend", 0.0)),
                    "yield_spread": _safe_float(meta.get("yield_spread", 0.0)),
                    "minutes_since_high_impact_news": _safe_float(meta.get("minutes_since_high_impact_news", 0.0)),
                    "minutes_until_high_impact_news": _safe_float(meta.get("minutes_until_high_impact_news", 0.0)),
                    "news_event_impact_score": _safe_float(meta.get("news_event_impact_score", 0.0)),
                    "spx_trend": _safe_float(meta.get("spx_trend", 0.0)),
                    "btc_corr": _safe_float(meta.get("btc_corr", 0.0)),
                    "partial_tp_progress": 0.0,
                    "false_breakout": 0,
                    "barrier_type": barrier,
                    "sample_weight": float(paper_weight),
                    "source_type": "paper_execution",
                    "source_weight": 0.35,
                    "created_at": getattr(sig, "created_at", None) or getattr(position, "opened_at", None) or now_utc_naive(),
                    "target": int(target),
                })
        except Exception as paper_err:
            logger.warning("Failed to load paper-execution training rows: %s", paper_err)

        df = pd.DataFrame(data)
        source_counts = (
            df["source_type"].value_counts().to_dict()
            if not df.empty and "source_type" in df.columns
            else {}
        )
        df.attrs["read_status"] = "success"
        df.attrs["live_proof_rows"] = int(live_proof_rows)
        df.attrs["source_counts"] = {str(k): int(v) for k, v in source_counts.items()}
        df.attrs["candle_series_loaded"] = int(len(candle_cache))
        logger.info(
            "[ml_dataset] status=success rows=%s live_proof=%s sources=%s candle_series=%s",
            len(df),
            live_proof_rows,
            source_counts,
            len(candle_cache),
        )
        logger.info(f"Class distribution: {df['target'].value_counts().to_dict()}")
        return df

    except Exception as e:
        if type(e).__name__ in {"DatabaseWorkDeferred", "NoncriticalWriteDropped", "AnalyticsWorkDeferred"}:
            logger.warning("ML training data read deferred; current model preserved: %s", e)
            deferred = pd.DataFrame()
            deferred.attrs["read_status"] = "deferred"
            deferred.attrs["read_error"] = f"{type(e).__name__}: {e}"
            return deferred
        logger.error(f"Failed to load training data: {e}", exc_info=True)
        failed = pd.DataFrame()
        failed.attrs["read_status"] = "failed"
        failed.attrs["read_error"] = f"{type(e).__name__}: {e}"
        return failed


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


async def load_training_data_sync(lookback_days: int = 90):
    """Backward-compatible alias for the async training data loader."""
    return await load_training_data(lookback_days)


def _expected_calibration_error(probabilities, labels, bins: int = 10) -> float:
    probs = np.asarray(probabilities, dtype=float)
    truth = np.asarray(labels, dtype=float)
    if len(probs) == 0:
        return 1.0
    edges = np.linspace(0.0, 1.0, max(2, int(bins)) + 1)
    ece = 0.0
    for idx in range(len(edges) - 1):
        left, right = edges[idx], edges[idx + 1]
        mask = (probs >= left) & ((probs < right) if idx < len(edges) - 2 else (probs <= right))
        count = int(mask.sum())
        if count <= 0:
            continue
        confidence = float(probs[mask].mean())
        accuracy = float(truth[mask].mean())
        ece += (count / len(probs)) * abs(confidence - accuracy)
    return float(ece)


def _temporal_three_way_indices(
    row_count: int,
    *,
    ordered_indices=None,
    train_ratio: float = 0.70,
    calibration_ratio: float = 0.15,
):
    """Return non-overlapping model-fit, calibration and validation indices."""
    n = int(row_count)
    if n < 3:
        raise ValueError("At least three rows are required for a three-way split")
    ordered = np.asarray(
        ordered_indices if ordered_indices is not None else np.arange(n),
        dtype=int,
    )
    if len(ordered) != n:
        raise ValueError("ordered_indices length must match row_count")
    train_ratio = min(0.85, max(0.55, float(train_ratio)))
    calibration_ratio = min(0.30, max(0.05, float(calibration_ratio)))
    train_end = min(n - 2, max(1, int(n * train_ratio)))
    calibration_end = min(n - 1, max(train_end + 1, int(n * (train_ratio + calibration_ratio))))
    return ordered[:train_end], ordered[train_end:calibration_end], ordered[calibration_end:]


def train_model(X_train, y_train, feature_cols, sample_weights=None, timestamps=None):
    """Train and calibrate an XGBoost classifier without validation leakage.

    Rows are ordered chronologically and split into three non-overlapping
    windows:

    * model-fit window (oldest rows)
    * calibration-fit window
    * untouched validation window (newest rows)

    The previous implementation fitted isotonic calibration and measured its
    quality on the same holdout rows.  That made Brier/ECE metrics optimistic
    and could incorrectly qualify a model for public probability display or
    live execution.  Calibration evidence is now always measured out of sample.
    """
    logger.info("Training XGBoost model...")

    # Time-series split: model fit -> calibration fit -> untouched validation.
    n = len(X_train)
    if n < 20:
        raise ValueError("Insufficient rows for time-series training")
    idx = np.arange(n)
    if timestamps is not None:
        ts = pd.to_datetime(timestamps, errors='coerce')
        ts_filled = ts.fillna(pd.Timestamp(now_utc_naive()))
        idx = np.argsort(ts_filled.values)

    train_ratio = min(0.85, max(0.55, float(os.getenv("ML_MODEL_FIT_RATIO", "0.70") or 0.70)))
    calibration_ratio = min(
        0.30,
        max(0.05, float(os.getenv("ML_CALIBRATION_FIT_RATIO", "0.15") or 0.15)),
    )
    idx_tr, idx_cal, idx_te = _temporal_three_way_indices(
        n,
        ordered_indices=idx,
        train_ratio=train_ratio,
        calibration_ratio=calibration_ratio,
    )

    X_tr, X_cal, X_te = X_train.iloc[idx_tr], X_train.iloc[idx_cal], X_train.iloc[idx_te]
    y_tr, y_cal, y_te = y_train.iloc[idx_tr], y_train.iloc[idx_cal], y_train.iloc[idx_te]
    if len(np.unique(y_tr)) < 2:
        raise ValueError("Model-fit window must contain both outcome classes")
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
    model.fit(X_tr, y_tr, sample_weight=w_tr)

    # Evaluate
    y_pred = model.predict(X_te)
    y_proba = model.predict_proba(X_te)[:, 1]
    calibration_x: list[float] = []
    calibration_y: list[float] = []
    calibrated_proba = np.asarray(y_proba, dtype=float)
    try:
        calibration_fit_proba = model.predict_proba(X_cal)[:, 1]
        if len(np.unique(calibration_fit_proba)) >= 2 and len(np.unique(y_cal)) >= 2:
            calibrator = IsotonicRegression(out_of_bounds='clip')
            calibrator.fit(calibration_fit_proba, y_cal)
            calibration_x = [float(x) for x in getattr(calibrator, 'X_thresholds_', [])]
            calibration_y = [float(y) for y in getattr(calibrator, 'y_thresholds_', [])]
            calibrated_proba = np.asarray(calibrator.predict(y_proba), dtype=float)
    except Exception as exc:
        logger.warning("Calibration fitting skipped: %s", exc)

    acc = accuracy_score(y_te, y_pred)
    try:
        auc = roc_auc_score(y_te, y_proba)
    except Exception:
        auc = 0.5

    logger.info(f"Test Accuracy: {acc:.4f}")
    logger.info(f"Test AUC: {auc:.4f}")
    logger.info(f"Confusion Matrix:\n{confusion_matrix(y_te, y_pred)}")
    logger.info(f"Classification Report:\n{classification_report(y_te, y_pred, zero_division=0)}")

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

    validation_rows = int(len(X_te))
    calibration_fit_rows = int(len(X_cal))
    calibration_min_rows = max(20, int(os.getenv("ML_MIN_CALIBRATION_VALIDATION_ROWS", "100") or 100))
    raw_brier = float(np.mean((np.asarray(y_proba, dtype=float) - np.asarray(y_te, dtype=float)) ** 2))
    calibrated_brier = float(np.mean((calibrated_proba - np.asarray(y_te, dtype=float)) ** 2))
    raw_ece = _expected_calibration_error(y_proba, y_te)
    calibrated_ece = _expected_calibration_error(calibrated_proba, y_te)
    max_brier = float(os.getenv("ML_MAX_CALIBRATION_BRIER", "0.25") or 0.25)
    max_ece = float(os.getenv("ML_MAX_CALIBRATION_ECE", "0.10") or 0.10)
    calibration_metrics = {
        "validation_rows": validation_rows,
        "calibration_fit_rows": calibration_fit_rows,
        "positive_calibration_rows": int((np.asarray(y_cal) == 1).sum()),
        "negative_calibration_rows": int((np.asarray(y_cal) == 0).sum()),
        "positive_validation_rows": int((np.asarray(y_te) == 1).sum()),
        "negative_validation_rows": int((np.asarray(y_te) == 0).sum()),
        "raw_brier": raw_brier,
        "calibrated_brier": calibrated_brier,
        "raw_ece": raw_ece,
        "calibrated_ece": calibrated_ece,
        "minimum_validation_rows": calibration_min_rows,
        "maximum_brier": max_brier,
        "maximum_ece": max_ece,
        "validated": bool(
            calibration_x and calibration_y
            and validation_rows >= calibration_min_rows
            and len(np.unique(y_te)) >= 2
            and calibrated_brier <= max_brier
            and calibrated_ece <= max_ece
        ),
    }
    metrics = {
        "accuracy": float(acc),
        "auc": float(auc),
        "train_rows": int(len(X_tr)),
        "calibration_fit_rows": calibration_fit_rows,
        "validation_rows": validation_rows,
        "positive_rows": int((y_train == 1).sum()),
        "negative_rows": int((y_train == 0).sum()),
        "calibration": calibration_metrics,
    }
    return model, feature_cols, calibration_x, calibration_y, metrics


def _primary_model_path() -> Path:
    raw = str(os.getenv("ML_MODEL_PATH") or "").strip()
    return Path(raw) if raw else Path(__file__).parent / "model.json"


def save_model(
    model,
    feature_cols,
    calibration_x=None,
    calibration_y=None,
    training_meta=None,
    model_path: str | Path | None = None,
):
    """Atomically save a primary or candidate model payload."""
    model_path = Path(model_path) if model_path is not None else _primary_model_path()
    
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
        "trained_at": now_utc_naive().isoformat(),
        "xgboost_version": getattr(xgb, "__version__", ""),
        "artifact_hash_sha256": artifact_hash_sha256,
        "calibration_kind": "isotonic" if calibration_x and calibration_y else "none",
        "calibration_x": calibration_x or [],
        "calibration_y": calibration_y or [],
        "metrics": dict((training_meta or {}).get("metrics") or {}),
        "calibration_metrics": dict(((training_meta or {}).get("metrics") or {}).get("calibration") or {}),
        "training_meta": dict(training_meta or {}),
    }

    model_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix="model.",
        suffix=".json.tmp",
        dir=str(model_path.parent),
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(model_dict, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, model_path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)

    logger.info(
        "[ml_model_saved] path=%s hash=%s rows=%s",
        model_path,
        artifact_hash_sha256,
        (training_meta or {}).get("total_rows"),
    )
    return model_path


async def main(lookback_days: int | None = None):
    run_id = f"ml-{now_utc_naive().strftime('%Y%m%d%H%M%S')}"
    logger.info("[ml_training_run] id=%s status=starting", run_id)

    if lookback_days is None:
        try:
            lookback_days = int(os.getenv("ML_TRAIN_LOOKBACK_DAYS", "90") or 90)
        except Exception:
            lookback_days = 90

    df = await load_training_data(int(lookback_days or 90))
    read_status = str((df.attrs.get("read_status") if df is not None else "failed") or "failed")
    if read_status != "success":
        logger.warning(
            "[ml_training_run] id=%s status=%s error=%s current_model_preserved=true",
            run_id,
            read_status,
            (df.attrs.get("read_error") if df is not None else "dataset_none"),
        )
        return False

    default_min_rows = "100" if _is_production_runtime() else "10"
    min_rows = int(os.getenv("ML_MIN_TRAIN_ROWS", default_min_rows) or default_min_rows)
    bootstrap_enabled = _offline_bootstrap_allowed()
    bootstrap_rows = int(os.getenv("ML_OFFLINE_BOOTSTRAP_ROWS", "1200") or 1200)
    used_bootstrap = False
    source_rows = int(len(df)) if df is not None else 0
    live_proof_rows = int(df.attrs.get("live_proof_rows", 0)) if df is not None else 0
    source_counts = dict(df.attrs.get("source_counts") or {}) if df is not None else {}
    min_live_proof_rows = int(
        os.getenv("ML_MIN_LIVE_PROOF_ROWS", "10" if _is_production_runtime() else "1")
        or ("10" if _is_production_runtime() else "1")
    )

    promotion_eligible = not _is_production_runtime() or live_proof_rows >= min_live_proof_rows
    if not promotion_eligible:
        logger.warning(
            "[ml_training_run] id=%s status=candidate_only reason=insufficient_live_proof "
            "live_proof=%s required=%s sources=%s primary_model_preserved=true",
            run_id, live_proof_rows, min_live_proof_rows, source_counts,
        )

    if (df is None or len(df) < min_rows) and bootstrap_enabled:
        boot = _generate_offline_bootstrap_data(max(bootstrap_rows, min_rows))
        used_bootstrap = True
        if df is None or len(df) == 0:
            df = boot
        else:
            df = pd.concat([df, boot], ignore_index=True)
        logger.warning("Bootstrap augmentation applied: source_rows=%s total_rows=%s", source_rows, len(df))

    if df is None or len(df) < min_rows:
        logger.warning(
            "[ml_training_run] id=%s status=skipped reason=insufficient_total_rows "
            "rows=%s required=%s sources=%s current_model_preserved=true",
            run_id, 0 if df is None else len(df), min_rows, source_counts,
        )
        return False

    if used_bootstrap and _is_production_runtime():
        logger.error("Refusing to save a bootstrap-trained model in production")
        return False

    effective_rows = float(df.get("sample_weight", pd.Series([1.0] * len(df))).fillna(1.0).sum())
    min_effective_rows = float(os.getenv("ML_MIN_EFFECTIVE_ROWS", str(max(25, min_rows // 2))) or max(25, min_rows // 2))
    if effective_rows < min_effective_rows:
        logger.warning(
            "[ml_training_run] id=%s status=skipped reason=insufficient_effective_rows "
            "effective_rows=%.2f required=%.2f sources=%s",
            run_id, effective_rows, min_effective_rows, source_counts,
        )
        return False

    # CPU-heavy feature engineering and XGBoost fitting must not block Telegram
    # callback acknowledgement or the realtime outcome loop.
    X_train, y_train, feature_cols, sample_weights, timestamps = await asyncio.to_thread(
        engineer_features, df
    )
    logger.info(
        "[ml_training_run] id=%s status=fitting rows=%s effective_rows=%.2f features=%s sources=%s",
        run_id, len(df), effective_rows, len(feature_cols), source_counts,
    )
    model, feature_cols, calibration_x, calibration_y, metrics = await asyncio.to_thread(
        train_model,
        X_train,
        y_train,
        feature_cols,
        sample_weights,
        timestamps,
    )

    min_auc = float(os.getenv("ML_MIN_PROMOTION_AUC", "0.52") or 0.52)
    min_accuracy = float(os.getenv("ML_MIN_PROMOTION_ACCURACY", "0.50") or 0.50)
    if metrics["auc"] < min_auc or metrics["accuracy"] < min_accuracy:
        logger.warning(
            "[ml_training_run] id=%s status=rejected reason=quality_gate "
            "accuracy=%.4f min_accuracy=%.4f auc=%.4f min_auc=%.4f current_model_preserved=true",
            run_id, metrics["accuracy"], min_accuracy, metrics["auc"], min_auc,
        )
        return False

    training_meta = {
        "run_id": run_id,
        "offline_bootstrap_used": bool(used_bootstrap),
        "source_rows": int(source_rows),
        "total_rows": int(len(df)),
        "effective_rows": float(effective_rows),
        "live_proof_rows": int(live_proof_rows),
        "source_counts": source_counts,
        "candle_series_loaded": int(df.attrs.get("candle_series_loaded", 0)),
        "metrics": metrics,
        "promotion_eligible": bool(promotion_eligible),
    }
    primary_path = _primary_model_path()
    candidate_path = Path(
        str(
            os.getenv("ML_CANDIDATE_MODEL_PATH")
            or (Path(__file__).parent / "model_candidate.json")
        )
    )
    target_path = primary_path if promotion_eligible else candidate_path
    previous_model_bytes = target_path.read_bytes() if target_path.exists() else None
    model_path = await asyncio.to_thread(
        save_model,
        model,
        feature_cols,
        calibration_x,
        calibration_y,
        training_meta,
        target_path,
    )

    # Candidate-only training learns from every trustworthy source without
    # changing live decisions until sufficient delivery-proof evidence exists.
    if not promotion_eligible:
        from engine import ml as engine_ml
        candidate_reload = await asyncio.to_thread(engine_ml.reload_shadow_model)
        if not candidate_reload.get("loaded"):
            if previous_model_bytes is not None:
                target_path.write_bytes(previous_model_bytes)
            elif target_path.exists():
                target_path.unlink()
            await asyncio.to_thread(engine_ml.reload_shadow_model)
            logger.error(
                "[ml_training_run] id=%s status=rejected reason=candidate_reload_failed error=%s",
                run_id, candidate_reload.get("error"),
            )
            return False

        from ml.artifact_store import persist_active_model_artifact
        candidate_persisted = await persist_active_model_artifact(
            model_path, training_meta=training_meta, model_name="candidate"
        )
        require_candidate_durable = _env_bool(
            "ML_REQUIRE_DURABLE_CANDIDATE_ARTIFACT", _is_production_runtime()
        )
        if require_candidate_durable and not candidate_persisted:
            if previous_model_bytes is not None:
                target_path.write_bytes(previous_model_bytes)
            elif target_path.exists():
                target_path.unlink()
            await asyncio.to_thread(engine_ml.reload_shadow_model)
            logger.error(
                "[ml_training_run] id=%s status=rejected reason=candidate_artifact_persistence_failed",
                run_id,
            )
            return False
        logger.info(
            "[ml_training_run] id=%s status=candidate_saved model=%s accuracy=%.4f auc=%.4f "
            "rows=%s live=%s sources=%s durable=%s candidate_version=%s",
            run_id, model_path, metrics["accuracy"], metrics["auc"], len(df),
            live_proof_rows, source_counts, candidate_persisted,
            candidate_reload.get("version"),
        )
        return True

    # The running engine caches the booster. A successful file write is not a
    # promotion until the new artifact can be loaded by the live inference path.
    from engine import ml as engine_ml

    reload_status = await asyncio.to_thread(engine_ml.reload_model)
    if not reload_status.get("loaded"):
        if previous_model_bytes is not None:
            primary_path.write_bytes(previous_model_bytes)
        elif primary_path.exists():
            primary_path.unlink()
        await asyncio.to_thread(engine_ml.reload_model)
        logger.error(
            "[ml_training_run] id=%s status=rejected reason=live_reload_failed error=%s",
            run_id, reload_status.get("error"),
        )
        return False

    from ml.artifact_store import persist_active_model_artifact

    artifact_persisted = await persist_active_model_artifact(
        model_path,
        training_meta=training_meta,
    )
    require_durable = _env_bool(
        "ML_REQUIRE_DURABLE_MODEL_ARTIFACT",
        _is_production_runtime(),
    )
    if require_durable and not artifact_persisted:
        if previous_model_bytes is not None:
            primary_path.write_bytes(previous_model_bytes)
        elif primary_path.exists():
            primary_path.unlink()
        await asyncio.to_thread(engine_ml.reload_model)
        logger.error(
            "[ml_training_run] id=%s status=rejected reason=artifact_persistence_failed "
            "current_model_restored=true",
            run_id,
        )
        return False

    logger.info(
        "[ml_training_run] id=%s status=promoted model=%s accuracy=%.4f auc=%.4f "
        "rows=%s live=%s sources=%s durable=%s active_version=%s",
        run_id, model_path, metrics["accuracy"], metrics["auc"], len(df), live_proof_rows,
        source_counts, artifact_persisted, reload_status.get("version"),
    )
    return True


if __name__ == "__main__":
    import asyncio
    from utils.async_runner import run_sync
    success = run_sync(main())
    sys.exit(0 if success else 1)
