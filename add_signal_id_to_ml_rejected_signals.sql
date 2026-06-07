-- Add signal_id column to ml_rejected_signals table
-- This enables linking rejected signals to their original signal for tracking

ALTER TABLE ml_rejected_signals ADD COLUMN IF NOT EXISTS signal_id VARCHAR(36);

-- Add index for faster lookups
CREATE INDEX IF NOT EXISTS idx_ml_rejected_signals_signal_id 
ON ml_rejected_signals(signal_id)
WHERE signal_id IS NOT NULL;

-- Add index for outcome tracking
CREATE INDEX IF NOT EXISTS idx_ml_rejected_signals_outcome_tracked 
ON ml_rejected_signals(outcome_tracked_at)
WHERE outcome_tracked_at IS NOT NULL;

-- Add index for ML probability analysis
CREATE INDEX IF NOT EXISTS idx_ml_rejected_signals_ml_probability 
ON ml_rejected_signals(ml_probability)
WHERE ml_probability IS NOT NULL;

-- Backfill signal_id from features JSON where available
UPDATE ml_rejected_signals 
SET signal_id = (features->>'signal_id')::VARCHAR(36)
WHERE signal_id IS NULL 
AND features IS NOT NULL 
AND features ? 'signal_id';

-- Verify the column was added
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'ml_rejected_signals' 
AND column_name IN ('signal_id', 'ml_probability', 'actual_outcome', 'outcome_tracked_at')
ORDER BY column_name;
