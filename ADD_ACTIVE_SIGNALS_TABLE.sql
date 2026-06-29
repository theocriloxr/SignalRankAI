-- Active Signal Registry Table
-- Enables outcome tracking, message editing, and signal replacement

CREATE TABLE IF NOT EXISTS active_signals (
    signal_id VARCHAR(36) PRIMARY KEY,
    fingerprint VARCHAR(128) NOT NULL,
    asset VARCHAR(32) NOT NULL,
    direction VARCHAR(16) NOT NULL,
    timeframe VARCHAR(8) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'NEW',
    message_id BIGINT,
    chat_id BIGINT,
    user_id INTEGER NOT NULL,
    entry_hit TIMESTAMP,
    tp1_hit TIMESTAMP,
    tp2_hit TIMESTAMP,
    tp3_hit TIMESTAMP,
    sl_hit TIMESTAMP,
    expiry TIMESTAMP,
    signal_metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS ix_active_signals_fingerprint ON active_signals(fingerprint);
CREATE INDEX IF NOT EXISTS ix_active_signals_asset ON active_signals(asset);
CREATE INDEX IF NOT EXISTS ix_active_signals_user_id ON active_signals(user_id);
CREATE INDEX IF NOT EXISTS ix_active_signals_chat_id ON active_signals(chat_id);
CREATE INDEX IF NOT EXISTS ix_active_signals_user_status ON active_signals(user_id, status);
CREATE INDEX IF NOT EXISTS ix_active_signals_asset_status ON active_signals(asset, status);
CREATE INDEX IF NOT EXISTS ix_active_signals_status ON active_signals(status);

-- Unique constraint for user + signal
ALTER TABLE active_signals ADD CONSTRAINT uq_active_signals_user_signal UNIQUE (user_id, signal_id);
