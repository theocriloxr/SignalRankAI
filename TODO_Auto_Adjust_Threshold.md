# Auto-Adjusting AI Threshold System Implementation Plan

## Information Gathered

### Current State Analysis
1. **train_model.py** already has:
   - Logging breadcrumb logs (`[ml] Starting load_training_data...`)
   - Redis AUC storage (`_r.set("ml:model:auc", float(auc))`)
   - ✅ Model training complete log

2. **threshold_optimizer.py** exists and has:
   - AdaptiveThresholdOptimizer class
   - Adjusts thresholds based on win rate and R metrics
   - Uses DB for persistence

3. **inference.py (MLFilter)** has:
   - `ml_filter(features, threshold)` - takes threshold as parameter
   - No dynamic threshold calculation

### What's MISSING
1. `calculate_dynamic_threshold()` function in ml/inference.py
2. worker/ai_feedback.py for Gemini AI validation loop
3. Integration in engine/core.py

## Plan

### Step 1: Add calculate_dynamic_threshold to ml/inference.py
- Create function that fetches current_auc from Redis
- Calculate dynamic threshold: base_threshold * (target_auc / current_auc)
- Clamp between 0.15 and 0.60

### Step 2: Create worker/ai_feedback.py
- Weekly task to gather performance stats
- Use Gemini to analyze and recommend threshold adjustments
- Store in Redis: ENGINE_BASE_THRESHOLD

### Step 3: Update engine/core.py
- Import and use calculate_dynamic_threshold
- Update _current_ml_prob_threshold() to use dynamic calculation

## Dependent Files to Edit
- ml/inference.py - add calculate_dynamic_threshold()
- worker/ai_feedback.py - create Gemini feedback loop
- engine/core.py - integrate dynamic threshold

## Followup Steps
- Test the implementation locally
- Monitor logs for AUC storage
- Verify threshold auto-adjusts

## Implementation Confirmation Required
