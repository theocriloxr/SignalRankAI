-- Complete ML Drift Fix - Lower thresholds to allow 56% predictions through
-- This addresses the "Drift State" where the model outputs ~56% but threshold blocks them

-- 1. Lower ML probability threshold in threshold_configs
UPDATE threshold_configs SET value = '0.40' WHERE key = 'ml_min_confidence';
UPDATE threshold_configs SET value = '0.40' WHERE key = 'ml_prob_threshold';

-- 2. Also update the hard filter threshold
UPDATE threshold_configs SET value = '0.40' WHERE key = 'ml_hard_filter_min';

-- 3. Add entries if they don't exist
INSERT INTO threshold_configs (key, value, description, updated_at) 
VALUES ('ml_min_confidence', '0.40', 'ML probability minimum threshold - lowered for drift', CURRENT_TIMESTAMP)
ON CONFLICT (key) DO UPDATE SET value = '0.40', updated_at = CURRENT_TIMESTAMP;

INSERT INTO threshold_configs (key, value, description, updated_at) 
VALUES ('ml_prob_threshold', '0.40', 'ML probability threshold - lowered for drift', CURRENT_TIMESTAMP)
ON CONFLICT (key) DO UPDATE SET value = '0.40', updated_at = CURRENT_TIMESTAMP;

INSERT INTO threshold_configs (key, value, description, updated_at) 
VALUES ('ml_hard_filter_min', '0.40', 'ML hard filter minimum - lowered to allow 56% through', CURRENT_TIMESTAMP)
ON CONFLICT (key) DO UPDATE SET value = '0.40', updated_at = CURRENT_TIMESTAMP;

-- 4. Verify the update
SELECT key, value FROM threshold_configs WHERE key LIKE '%ml_%' OR key LIKE '%threshold%' OR key LIKE '%confiden%';
