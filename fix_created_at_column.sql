-- Fix for: WARNING engine.admin_pulse: created_at column missing in signal_deliveries
-- Add missing created_at column to signal_deliveries table

ALTER TABLE signal_deliveries ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
