# Auto-Adjusting AI Threshold System - Implementation TODO

## Steps

- [x] Add calculate_dynamic_threshold to ml/dynamic_threshold.py
- [x] Create engine/dynamic_threshold.py wrapper
- [ ] Create worker/ai_feedback.py with Gemini AI validation loop (optional macro-adjustments)
- [x] Update engine/core.py to use dynamic threshold

## Implementation Log
[Created: 2025-01-21]

### Done:
1. ✅ Created ml/dynamic_threshold.py with:
   - calculate_dynamic_threshold(base_threshold, current_auc, target_auc)
   - get_current_model_auc() to fetch AUC from Redis
   - get_dynamic_ml_threshold() convenience function

2. ✅ Created engine/dynamic_threshold.py wrapper with:
   - calculate_dynamic_threshold() - main engine function
   - get_ml_model_auc() - fetches AUC from Redis
   - get_threshold() - matches engine interface

3. ✅ Updated engine/core.py _current_ml_prob_threshold() to use dynamic threshold

### How it works:
- Micro-adjustments (every cycle): Dynamic threshold math shifts threshold based on XGBoost AUC
- If model AUC < target (0.85), threshold INCREASES (stricter) -> fewer signals
- If model AUC > target (0.85), threshold DECREASES (looser) -> more signals
- If no AUC in Redis, falls back to base threshold from env var

### To enable:
Set env var ML_PROB_THRESHOLD=0.30 (base threshold)
ML model will store AUC to Redis key "ml:model:auc" after training
