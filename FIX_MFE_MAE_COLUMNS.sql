-- =====================================================
-- FIX: Add missing mfe_pct and mae_pct columns
-- Run this in Railway PostgreSQL Query console
-- =====================================================

-- Add columns to signals table if they don't exist
ALTER TABLE signals ADD COLUMN IF NOT EXISTS mfe_pct FLOAT;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS mae_pct FLOAT;

-- Add columns to trades table if they don't exist  
ALTER TABLE trades ADD COLUMN IF NOT EXISTS mfe_pct FLOAT;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS mae_pct FLOAT;

-- Verify columns were added
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name IN ('signals', 'trades') 
AND column_name IN ('mfe_pct', 'mae_pct')
ORDER BY table_name, column_name;
