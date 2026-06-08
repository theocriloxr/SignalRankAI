-- Fix ML threshold to allow 82.43 scores to pass through
-- Run this in your Railway Postgres terminal

-- Fix 1: Update the adaptive_thresholds in runtime_state table
-- This is where threshold_optimizer stores ML probability threshold
UPDATE runtime_state 
SET value = '{
  "ml_prob_threshold": 0.80, 
  "min_score_threshold": 75, 
  "confluence_min": 0.0, 
  "source": "manual_fix"
}'::jsonb,
    updated_at = NOW() 
WHERE key = 'adaptive_thresholds';

-- Verify the update
SELECT key, value FROM runtime_state WHERE key = 'adaptive_thresholds';

-- Also check if there are any other threshold keys
SELECT key, value FROM runtime_state WHERE key LIKE '%threshold%';
