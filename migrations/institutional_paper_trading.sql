-- Institutional Grade Paper Trading Schema
-- This migration adds per-user paper trading capabilities

-- 1. Extend users table with paper trading defaults
ALTER TABLE users ADD COLUMN IF NOT EXISTS paper_balance DECIMAL(20, 2) DEFAULT 10000.00;
ALTER TABLE users ADD COLUMN IF NOT EXISTS max_daily_paper_trades INT DEFAULT 10;
ALTER TABLE users ADD COLUMN IF NOT EXISTS paper_trading_enabled BOOLEAN DEFAULT TRUE;

-- 2. Virtual Accounts table (per-user balance)
CREATE TABLE IF NOT EXISTS virtual_accounts (
    account_id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    balance DECIMAL(20, 2) DEFAULT 10000.00,
    currency TEXT DEFAULT 'USD',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id)
);

-- 3. Paper Positions table
CREATE TABLE IF NOT EXISTS paper_positions (
    position_id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    signal_id TEXT,
    asset TEXT NOT NULL,
    direction TEXT NOT NULL,  -- 'long' / 'short'
    entry_price DECIMAL(20, 8),
    stop_loss DECIMAL(20, 8),
    take_profit TEXT,
    size DECIMAL(20, 8),
    status TEXT DEFAULT 'OPEN',  -- 'OPEN', 'CLOSED', 'CANCELLED'
    pnl_realized DECIMAL(20, 2) DEFAULT 0.00,
    r_multiple DECIMAL(10, 4),
    exit_reason TEXT,
    opened_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    closed_at TIMESTAMP WITH TIME ZONE,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_paper_positions_user_id ON paper_positions(user_id);
CREATE INDEX IF NOT EXISTS idx_paper_positions_status ON paper_positions(status);
CREATE INDEX IF NOT EXISTS idx_paper_positions_asset ON paper_positions(asset);

-- 4. Account Ledger (Audit Trail)
CREATE TABLE IF NOT EXISTS account_ledger (
    ledger_id SERIAL PRIMARY KEY,
    account_id INT REFERENCES virtual_accounts(account_id),
    user_id BIGINT NOT NULL REFERENCES users(id),
    amount DECIMAL(20, 2),
    type TEXT,  -- 'TRADE_WIN', 'TRADE_LOSS', 'DEPOSIT', 'FEE', 'ADJUSTMENT'
    description TEXT,
    position_id INT REFERENCES paper_positions(position_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_account_ledger_user_id ON account_ledger(user_id);
CREATE INDEX IF NOT EXISTS idx_account_ledger_type ON account_ledger(type);
CREATE INDEX IF NOT EXISTS idx_account_ledger_created_at ON account_ledger(created_at);

-- 5. Signal Context table (for ML training)
CREATE TABLE IF NOT EXISTS signal_context (
    context_id SERIAL PRIMARY KEY,
    signal_id TEXT NOT NULL UNIQUE,
    rsi DECIMAL(10, 4),
    volatility DECIMAL(10, 6),
    dxy_strength DECIMAL(10, 4),
    vix DECIMAL(10, 4),
    dxy_trend TEXT,
    vix_trend TEXT,
    news_sentiment TEXT,
    atr_percent DECIMAL(10, 4),
    volume_ratio DECIMAL(10, 4),
    macd_trend TEXT,
    adx_trend TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signal_context_signal_id ON signal_context(signal_id);

-- 6. Provider Health table
CREATE TABLE IF NOT EXISTS provider_health (
    provider_id SERIAL PRIMARY KEY,
    provider_name TEXT NOT NULL UNIQUE,
    is_active BOOLEAN DEFAULT TRUE,
    fail_count INT DEFAULT 0,
    success_count INT DEFAULT 0,
    cooldown_until TIMESTAMP WITH TIME ZONE,
    last_checked TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 7. DLQ table for failed deliveries
CREATE TABLE IF NOT EXISTS dead_letter_queue (
    dlq_id SERIAL PRIMARY KEY,
    signal_id TEXT NOT NULL,
    user_id BIGINT NOT NULL,
    error TEXT,
    payload JSONB,
    retry_count INT DEFAULT 0,
    max_retries INT DEFAULT 10,
    status TEXT DEFAULT 'PENDING',  -- 'PENDING', 'RETRYING', 'FAILED', 'RESOLVED'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_retry_at TIMESTAMP WITH TIME ZONE,
    resolved_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_dead_letter_queue_status ON dead_letter_queue(status);
CREATE INDEX IF NOT EXISTS idx_dead_letter_queue_user_id ON dead_letter_queue(user_id);

-- 8. ML Training Events table
CREATE TABLE IF NOT EXISTS ml_training_events (
    event_id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,  -- 'RETRAIN_START', 'RETRAIN_COMPLETE', 'DRIFT_DETECTED'
    model_name TEXT,
    signals_used INT,
    outcomes JSONB,
    result JSONB,
    triggered_by TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ml_training_events_created_at ON ml_training_events(created_at);

-- Comments for documentation
COMMENT ON TABLE virtual_accounts IS 'Per-user virtual accounts for paper trading';
COMMENT ON TABLE paper_positions IS 'Paper trading positions linked to signals';
COMMENT ON TABLE account_ledger IS 'Audit trail for paper trading transactions';
COMMENT ON TABLE signal_context IS 'Market context at signal generation time for ML';
COMMENT ON TABLE provider_health IS 'Data provider health monitoring';
COMMENT ON TABLE dead_letter_queue IS 'Failed signal deliveries requiring manual intervention';
COMMENT ON TABLE ml_training_events IS 'ML training lifecycle events';
