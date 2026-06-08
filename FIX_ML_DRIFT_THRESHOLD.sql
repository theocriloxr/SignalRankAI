-- Fix ML Drift: Lower the ML probability threshold to allow drifted model predictions through
-- The model is outputting ~56% probability but threshold was 55%, blocking all signals

-- Option 1: Update threshold_configs table if it exists
UPDATE threshold_configs SET value = '0.50' WHERE key = 'ml_min_confidence';

-- Option 2: Also update ML_PROB_THRESHOLD if tracked separately
UPDATE threshold_configs SET value = '0.50' WHERE key = 'ml_prob_threshold';

-- Verify the update
SELECT key, value FROM threshold_configs WHERE key LIKE '%threshold%' OR key LIKE '%confiden%';
