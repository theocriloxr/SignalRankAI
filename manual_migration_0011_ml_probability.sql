-- Manual SQL migration: Add ml_probability column to signals table
-- Apply this if Alembic migration fails

ALTER TABLE signals ADD COLUMN ml_probability FLOAT;
