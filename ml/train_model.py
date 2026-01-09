#!/usr/bin/env python
"""
Train XGBoost model from existing signal history.
Loads signals + outcomes from Postgres, builds feature matrix, trains model.
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, accuracy_score, confusion_matrix, classification_report

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


async def load_training_data():
    """Load signals + outcomes from Postgres."""
    try:
        from db.session import get_session, ENGINE
        if ENGINE is None:
            raise RuntimeError("DATABASE_URL not configured")

        from db.models import Signal, Outcome, SignalDelivery
        from sqlalchemy import select, func

        async with get_session() as session:
            # Get signals delivered in last 90 days with outcomes
            cutoff = datetime.utcnow() - timedelta(days=90)

            stmt = (
                select(Signal, Outcome)
                .join(Outcome, Outcome.signal_id == Signal.signal_id)
                .where(Signal.created_at >= cutoff)
            )
            res = await session.execute(stmt)
            rows = list(res.all())
            await session.commit()

        if not rows:
            logger.warning("No signals with outcomes found in last 90 days")
            return None

        data = []
        for sig, outcome in rows:
            status = str(getattr(outcome, 'status', '') or '').lower()
            # Target: 1 if TP, 0 if SL
            target = 1 if status in ("tp", "tp1", "tp2", "partial_tp") else 0

            row = {
                'signal_id': sig.signal_id,
                'asset': sig.asset,
                'timeframe': sig.timeframe,
                'direction': sig.direction,
                'score': _safe_float(getattr(sig, 'score', 0)),
                'entry': _safe_float(getattr(sig, 'entry', 0)),
                'stop_loss': _safe_float(getattr(sig, 'stop_loss', 0)),
                'take_profit': _safe_float(getattr(sig, 'take_profit', 0)),
                'rr_ratio': _safe_float(getattr(sig, 'rr_estimate', 0)),
                'strategy_name': sig.strategy_name or 'unknown',
                'regime': sig.regime or 'unknown',
                'strength': _safe_float(getattr(sig, 'strength', 0)),
                'ml_probability': _safe_float(getattr(sig, 'ml_probability', 0)),
                'target': target,
            }
            data.append(row)

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

    # Score bins
    X['high_score'] = (X['score'] >= 75).astype(int)
    X['medium_score'] = ((X['score'] >= 60) & (X['score'] < 75)).astype(int)

    # Direction bias
    X['is_long'] = (X['direction'].str.lower() == 'long').astype(int)

    # Feature selection for model
    feature_cols = [
        'score_normalized', 'risk_reward_ratio', 'price_range', 'risk_amount',
        'spread_ratio', 'strength_normalized', 'direction_enc', 'regime_enc',
        'strategy_enc', 'high_score', 'medium_score', 'is_long'
    ]

    X_train = X[feature_cols].fillna(0.0).astype(np.float32)
    y_train = X['target'].astype(np.int32)

    return X_train, y_train, feature_cols


def train_model(X_train, y_train, feature_cols):
    """Train XGBoost classifier and check for drift."""
    logger.info("Training XGBoost model...")

    # Split data
    X_tr, X_te, y_tr, y_te = train_test_split(
        X_train, y_train, test_size=0.2, random_state=42, stratify=y_train
    )

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
    model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)

    # Evaluate
    y_pred = model.predict(X_te)
    y_proba = model.predict_proba(X_te)[:, 1]

    acc = accuracy_score(y_te, y_pred)
    auc = roc_auc_score(y_te, y_proba)

    logger.info(f"Test Accuracy: {acc:.4f}")
    logger.info(f"Test AUC: {auc:.4f}")
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

    return model, feature_cols


def save_model(model, feature_cols):
    """Save model to JSON."""
    model_path = Path(__file__).parent / "model.json"
    
    # Save model as ubj (XGBoost binary JSON) - avoids format warnings
    import base64
    booster = model.get_booster()
    model_bytes = booster.save_raw('ubj')  # Binary format, no warnings
    
    model_dict = {
        "type": "xgboost",
        "feature_cols": feature_cols,
        "model_bytes_b64": base64.b64encode(model_bytes).decode('utf-8'),
        "trained_at": datetime.utcnow().isoformat(),
    }

    with open(model_path, 'w') as f:
        json.dump(model_dict, f, indent=2)

    logger.info(f"Model saved to {model_path}")
    return model_path


async def main():
    logger.info("Starting ML model training...")

    # Load data
    df = await load_training_data()
    if df is None or len(df) < 10:
        logger.error("Insufficient training data (need >= 10 signals with outcomes)")
        return False

    # Engineer features
    X_train, y_train, feature_cols = engineer_features(df)
    logger.info(f"Features engineered: {feature_cols}")
    logger.info(f"Training set shape: {X_train.shape}")

    # Train model
    model, feature_cols = train_model(X_train, y_train, feature_cols)

    # Save model
    save_model(model, feature_cols)

    logger.info("✅ Model training complete!")
    return True


if __name__ == "__main__":
    import asyncio
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
