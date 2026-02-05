-- Manual migration: decision_log + ml_rejected_signals + missing columns

-- Add missing columns
ALTER TABLE users ADD COLUMN IF NOT EXISTS premium_until TIMESTAMP;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS bonus_days INTEGER;

-- decision_log table
CREATE TABLE IF NOT EXISTS decision_log (
    id SERIAL PRIMARY KEY,
    signal_id VARCHAR(36),
    asset VARCHAR(32),
    timeframe VARCHAR(8),
    decision VARCHAR(32) NOT NULL,
    reason TEXT,
    meta JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_decision_log_signal_id ON decision_log(signal_id);
CREATE INDEX IF NOT EXISTS ix_decision_log_asset ON decision_log(asset);
CREATE INDEX IF NOT EXISTS ix_decision_log_timeframe ON decision_log(timeframe);
CREATE INDEX IF NOT EXISTS ix_decision_log_decision ON decision_log(decision);
CREATE INDEX IF NOT EXISTS ix_decision_log_created_at ON decision_log(created_at);

-- ml_rejected_signals table
CREATE TABLE IF NOT EXISTS ml_rejected_signals (
    id SERIAL PRIMARY KEY,
    asset VARCHAR(32) NOT NULL,
    timeframe VARCHAR(8) NOT NULL,
    direction VARCHAR(8) NOT NULL,
    entry DOUBLE PRECISION NOT NULL,
    stop_loss DOUBLE PRECISION NOT NULL,
    take_profit TEXT NOT NULL,
    ml_probability DOUBLE PRECISION NOT NULL,
    rejection_reason VARCHAR(128) NOT NULL,
    features JSONB NOT NULL DEFAULT '{}'::jsonb,
    actual_outcome VARCHAR(32),
    outcome_tracked_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_ml_rejected_signals_asset ON ml_rejected_signals(asset);
CREATE INDEX IF NOT EXISTS ix_ml_rejected_signals_timeframe ON ml_rejected_signals(timeframe);
CREATE INDEX IF NOT EXISTS ix_ml_rejected_signals_actual_outcome ON ml_rejected_signals(actual_outcome);
