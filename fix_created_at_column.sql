-- Fix for: column "created_at" does not exist in signal_deliveries table
-- Run this against your Railway PostgreSQL database

-- Add created_at column to signal_deliveries if it doesn't exist
ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();

-- Also ensure decision_log has created_at
ALTER TABLE decision_log ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();
