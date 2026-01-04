-- Immediate SQL fix for Railway PostgreSQL
-- Run this in Railway PostgreSQL console if Alembic migration hasn't applied yet

ALTER TABLE signals ADD COLUMN IF NOT EXISTS ml_probability FLOAT;

-- Verify column was added
SELECT column_name FROM information_schema.columns WHERE table_name='signals' AND column_name='ml_probability';
