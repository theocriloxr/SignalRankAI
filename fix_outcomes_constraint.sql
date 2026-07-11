-- Fix: Add unique constraint to outcomes table to ensure each signal has only one outcome
-- This prevents duplicate outcome records for the same signal

-- Step 1: Remove any duplicate outcome records keeping the most recent
DELETE FROM outcomes
WHERE id NOT IN (
    SELECT MAX(id)
    FROM outcomes
    GROUP BY signal_id
);

-- Step 2: Add unique constraint to outcomes table
ALTER TABLE outcomes ADD CONSTRAINT unique_signal_id UNIQUE (signal_id);

-- Step 3: Verify the constraint was added
SELECT 
    conname AS constraint_name,
    contype AS constraint_type
FROM pg_constraint
WHERE conname = 'unique_signal_id';
