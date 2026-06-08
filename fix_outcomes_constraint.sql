-- Fix: Add unique constraint to outcomes table for UPSERT operations
-- This fixes "ON CONFLICT" errors when saving trade outcomes

ALTER TABLE outcomes ADD CONSTRAINT unique_signal_id UNIQUE (signal_id);
