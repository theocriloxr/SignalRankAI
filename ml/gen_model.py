#!/usr/bin/env python
"""Generate a test XGBoost model."""
import json
import xgboost as xgb
from pathlib import Path
import base64
import hashlib

# Create a minimal model
model = xgb.XGBClassifier(n_estimators=1, max_depth=2, random_state=42)
X = [[0.5, 1.0, 0.3, 0.2, 1.5, 0.4, 0.0, 0.0, 0.0, 1, 0, 1],
     [0.7, 1.5, 0.5, 0.4, 1.2, 0.6, 1.0, 1.0, 1.0, 1, 0, 1],
     [0.3, 0.5, 0.1, 0.1, 2.0, 0.2, 0.0, 1.0, 0.0, 0, 0, 0],
     [0.9, 2.0, 0.8, 0.6, 1.3, 0.8, 1.0, 0.0, 1.0, 1, 1, 1]]
y = [1, 1, 0, 1]
model.fit(X, y)

# Export to binary
booster = model.get_booster()
model_bytes = booster.save_raw()

# Encode as base64 for JSON storage
model_b64 = base64.b64encode(model_bytes).decode('utf-8')

# Save to file
model_data = {
    "type": "xgboost",
    "version": "1.0.0",
    "feature_cols": [
        "score_normalized",
        "risk_reward_ratio",
        "price_range",
        "risk_amount",
        "spread_ratio",
        "strength_normalized",
        "direction_enc",
        "regime_enc",
        "strategy_enc",
        "high_score",
        "medium_score",
        "is_long"
    ],
    "model_bytes_b64": model_b64,
    "trained_at": "2026-01-03T12:00:00",
    "xgboost_version": getattr(xgb, "__version__", ""),
    "artifact_hash_sha256": hashlib.sha256(model_bytes).hexdigest(),
    "note": "Minimal test model. Train with ml/train_model.py for production."
}

model_path = Path(__file__).parent / "model.json"
with open(model_path, "w") as f:
    json.dump(model_data, f, indent=2)

print(f"✅ Model saved to {model_path}")
