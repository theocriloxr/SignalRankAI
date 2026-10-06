"""
ML Auto-Retraining Pipeline.
Runs periodically (e.g., weekly) to retrain the XGBoost model
using actual signal outcomes stored in the database.
"""

import os
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

MODEL_PATH = os.getenv("ML_MODEL_PATH", "ml/model.json")
RETRAIN_MIN_SAMPLES = int(os.getenv("ML_RETRAIN_MIN_SAMPLES", "100"))
RETRAIN_LOOKBACK_DAYS = int(os.getenv("ML_RETRAIN_LOOKBACK_DAYS", "90"))

from ml.schema_version import (
    get_legacy_retrain_feature_columns,
)

# This module is intentionally legacy-only. The governed v3 pipeline lives in
# ml.train_model and must not receive synthetic zeroes for unavailable features.
FEATURE_COLS = get_legacy_retrain_feature_columns()


async def collect_training_data() -> list:
    """Collect labeled training data from signal outcomes."""
    try:
        from db.session import get_session
        from sqlalchemy import text

        cutoff = datetime.now(timezone.utc) - timedelta(days=RETRAIN_LOOKBACK_DAYS)

        async with get_session() as session:
            await session.execute(
                text("""
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
            """)
            )
            result = await session.execute(
                text("""
                SELECT
                    s.rr_estimate,
                    s.score,
                    s.strength,
                    0.0::double precision AS regime_score,
                    0.0::double precision AS trend_ema,
                    0.0::double precision AS rsi,
                    0.0::double precision AS volume_ratio,
                    0.0::double precision AS macd_trend,
                    0.0::double precision AS adx_value,
                    0.0::double precision AS news_sentiment,
                    0.0::double precision AS nearest_support_dist,
                    0.0::double precision AS nearest_resistance_dist,
                    o.status as outcome_status,
                    o.r_multiple
                FROM signals s
                JOIN outcomes o ON o.signal_id = s.signal_id
                WHERE s.created_at >= :cutoff
                  AND o.status IN ('tp', 'sl', 'partial_tp', 'tp1', 'tp2')

                UNION ALL

                SELECT
                    a.rr_estimate,
                    a.score,
                    a.strength,
                    COALESCE((a.outcome_meta->>'regime_score')::double precision, 0.0) AS regime_score,
                    COALESCE((a.outcome_meta->>'trend_ema')::double precision, 0.0) AS trend_ema,
                    COALESCE((a.outcome_meta->>'rsi')::double precision, 0.0) AS rsi,
                    COALESCE((a.outcome_meta->>'volume_ratio')::double precision, 0.0) AS volume_ratio,
                    COALESCE((a.outcome_meta->>'macd_trend')::double precision, 0.0) AS macd_trend,
                    COALESCE((a.outcome_meta->>'adx_value')::double precision, 0.0) AS adx_value,
                    COALESCE((a.outcome_meta->>'news_sentiment')::double precision, 0.0) AS news_sentiment,
                    COALESCE((a.outcome_meta->>'nearest_support_dist')::double precision, 0.0) AS nearest_support_dist,
                    COALESCE((a.outcome_meta->>'nearest_resistance_dist')::double precision, 0.0) AS nearest_resistance_dist,
                    a.outcome_status,
                    a.outcome_r_multiple AS r_multiple
                FROM ml_past_training_data a
                WHERE a.signal_created_at >= :cutoff
                  AND a.outcome_status IN ('tp', 'sl', 'partial_tp', 'tp1', 'tp2')
            """),
                {"cutoff": cutoff},
            )

            rows = result.fetchall()
            data = []
            for row in rows:
                features = {}
                for col in FEATURE_COLS:
                    # Use getattr to safely access columns
                    val = getattr(row, col, None) if hasattr(row, col) else None
                    features[col] = float(val or 0)

                # Label: 1 if TP hit, 0 if SL hit
                features["label"] = 1 if row.outcome_status in ("tp", "partial_tp", "tp1", "tp2") else 0
                data.append(features)

            logger.info(f"Collected {len(data)} training samples from outcomes")
            return data
    except Exception as e:
        logger.error(f"Failed to collect training data: {e}")
        return []


async def retrain_model() -> bool:
    """Backward-compatible entrypoint for the single governed trainer.

    Historically this module contained an independent AUC-only promotion path.
    Keep callers stable while delegating all training/promotion decisions to
    ml.train_model.main(), which owns temporal validation, calibration,
    live-proof evidence, candidate-only fallback and artifact persistence.
    """
    try:
        from ml.train_model import main as governed_training_main

        logger.info("[ml_retrain] delegating legacy retrain entrypoint to governed trainer")
        return bool(await governed_training_main())
    except Exception as exc:
        logger.exception("[ml_retrain] governed trainer failed: %s", exc)
        return False
