# Auto-Adjusting AI Threshold System Implementation Plan

## Problem Statement
Based on the latest logs analysis:
1. Cycle=1 shows `generated_signals=0` and `max_score=None` because ML model takes time to train
2. Need dynamic threshold that auto-adjusts based on ML model AUC performance
3. Need Gemini AI validator loop for weekly macro adjustments

## Files Understanding

### Already Implemented ✅
1. **ml/train_model.py** - Stores AUC in Redis after training:
   ```python
   _r.set("ml:model:auc", float(auc))
   ```
   
2. **ml/inference.py** - Has `calculate_dynamic_threshold()` function:
   ```python
   def calculate_dynamic_threshold(base_threshold, current_auc, target_auc):
       # Returns dynamic threshold based on model AUC
   ```

### Files Needing Updates
1. **engine/core.py** - Uses threshold_optimizer but NOT inference.py's dynamic threshold
2. **worker/ai_feedback.py** - Needs to be created for Gemini weekly loop

## Implementation Plan

### Step 1: Integrate Dynamic Threshold in Engine (engine/core.py)
Edit location: Around line where `_current_ml_prob_threshold()` is defined

Current code uses `threshold_optimizer.get_threshold()` which considers win rate but NOT directly on ML model AUC.

New code:
```python
def _current_ml_prob_threshold() -> float:
    try:
        # NEW: Use dynamic threshold based on ML model AUC
        from ml.inference import calculate_dynamic_threshold
        base_threshold = float(os.getenv('ML_BASE_THRESHOLD', '0.30') or 0.30)
        target_auc = float(os.getenv('ML_TARGET_AUC', '0.85') or 0.85)
        dynamic_thresh = calculate_dynamic_threshold(
            base_threshold=base_threshold,
            current_auc=None,  # Fetches from Redis automatically
            target_auc=target_auc
        )
        return dynamic_thresh
    except Exception:
        # Fallback to threshold_optimizer
        if _threshold_optimizer is not None and hasattr(_threshold_optimizer, "get_threshold"):
            return float(_threshold_optimizer.get_threshold() or _env_float("ML_PROB_THRESHOLD", 0.55))
    return _env_float("ML_PROB_THRESHOLD", 0.55)
```

### Step 2: Create Gemini AI Feedback Worker (worker/ai_feedback.py)
New file to review weekly performance and adjust engine aggressiveness.

```python
import json
import os
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Add parent dir to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

async def auto_adjust_engine_parameters():
    """
    Gemini AI reviews weekly performance and adjusts engine parameters.
    
    This is the "Chief Investment Officer" loop that looks at 
    actual financial outcomes and recommends threshold changes.
    """
    # 1. Gather last 7 days of performance data
    stats = await gather_weekly_performance_stats()
    
    # 2. Ask Gemini for adjustment
    prompt = build_gemini_prompt(stats)
    
    validator = GeminiValidator()
    response = await validator.generate_content(prompt)
    ai_recommendation = json.loads(response)
    
    # 3. Apply settings via Redis
    await redis.set("ENGINE_BASE_THRESHOLD", ai_recommendation["new_threshold"])
    logger.info(f"[AI Ops] Gemini adjusted threshold to {new_threshold}")

async def gather_weekly_performance_stats():
    """Query database for last 7 days of outcomes."""
    pass

if __name__ == "__main__":
    asyncio.run(auto_adjust_engine_parameters())
```

### Step 3: Add Breadcrumb Logs for Debugging (ml/train_model.py)
Add progress logs so we can see where training hangs:

```python
logger.info("[ml] Fetching signals from DB...")
# ... fetch signals ...
logger.info(f"[ml] Fetched {len(signals)} signals. Fetching candles now...")

for sig in signals:
    logger.info(f"[ml] Loading candles for {sig.asset}...")
    # ... load candles ...
    
logger.info("[ml] All data loaded. Beginning XGBoost training...")
# ... train model ...
logger.info("✅ Model training complete!")
```

## Dependent Files to be Edited
1. **engine/core.py** - Update `_current_ml_prob_threshold()` function
2. **worker/ai_feedback.py** - Create new file (Gemini AI validator loop)
3. **ml/train_model.py** - Add breadcrumb logs for debugging

## Followup Steps After Editing
1. Add ML_BASE_THRESHOLD and ML_TARGET_AUC to environment variables
2. Schedule worker/ai_feedback.py as weekly cron job
3. Monitor Railway metrics for OOM issues
4. Test by running train_model.py manually and checking Redis for AUC

## Implementation Order
1. First: Add breadcrumb logs to train_model.py for debugging
2. Second: Update engine/core.py to use dynamic threshold
3. Third: Create worker/ai_feedback.py (Gemini loop)
4. Fourth: Deploy and monitor

Let me know if you approve this plan!
