# SignalRankAI - Complete System Documentation
**Last Updated**: April 12, 2026  
**Status**: Production Ready with Enhancements  
**Architecture**: PythonAsyncIO + FastAPI Monolith (Railway Optimized)

---

## Table of Contents
1. [System Architecture](#system-architecture)
2. [Core Services](#core-services)
3. [Command Reference](#command-reference)
4. [Database Schema](#database-schema)
5. [Configuration & Deployment](#configuration--deployment)
6. [Troubleshooting Guide](#troubleshooting-guide)
7. [Testing & Verification](#testing--verification)
8. [Feature Matrix](#feature-matrix)
9. [API Endpoints](#api-endpoints)
10. [Enhancement Roadmap](#enhancement-roadmap)

---

## System Architecture

### Monolith Design
SignalRankAI runs as a **single unified service** with multiple internal components:

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Web Server                    │
│  (railway_main.py: lifespan-managed async context)      │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Engine     │  │   Worker     │  │  Telegram    │  │
│  │   Loop       │  │   Loop       │  │  Bot +       │  │
│  │  (signals)   │  │  (outcomes)  │  │  Webhook     │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                          │
├─────────────────────────────────────────────────────────┤
│  PostgreSQL Database  │  Redis Cache  │  Market Data    │
│  (Signals, Users)     │  (State)      │  Providers      │
└─────────────────────────────────────────────────────────┘
```

### Key Characteristics
- **Single Event Loop**: All async tasks share one asyncio.run() call
- **Memory Optimized**: NullPool for DB, in-process webhook queue fallback
- **Graceful Degradation**: Optional services (Redis, WebSocket, ML) fail safe
- **Auto-Recovery**: Background tasks restart if they crash
- **Railway Compatible**: Works on Railway free tier (256 MB + 100m bandwidth)

---

## Core Services

### 1. Signal Generation Engine (`engine/core.py`)

**Purpose**: Generates crypto, forex, stock, and commodity trading signals  
**Frequency**: Every 30 seconds (configurable via `ENGINE_CYCLE_SLEEP_SECONDS`)  
**Cycle**: Batch processing of 20 assets per wakeup

#### Signal Generation Pipeline

```
Assets Discovery → Market Data Fetch → Technical Analysis → Strategy Execution 
  ↓
Regime Detection → Consensus Filter → Risk Manager → ML Scoring 
  ↓
Advanced Filters → Final Score → User Delivery (Tier-Gated)
  ↓
Database Persistence → Telegram Dispatch → Custom Webhooks
```

#### Key Functions

| Function | Purpose |
|----------|---------|
| `main_loop(dry_run)` | Perpetual signal generation cycle |
| `_fetch_market_data_for_assets()` | Async market data collection |
| `run_all_strategies()` | Multi-strategy signal generation |
| `apply_consensus_filter()` | Multi-indicator agreement gate |
| `dispatch_signals()` | Tier-based user delivery |

**Strategies Implemented**:
- Trend Following (EMA, SMA crosses)
- Momentum (RSI divergence, MACD)
- Volatility (Bollinger Bands, ATR-based)
- Structure (Support/Resistance)  
- Harmonic Patterns
- Confluence (Multi-timeframe alignment)
- Commodity-Specific

**Filters & Gates**:
- Risk Manager: Max trades, position sizing, correlation
- ML Rejection: XGBoost shadow model (reject low-confidence signals)
- Economic Calendar: No-trade zones (30-min buffer around events)
- Market Regime: Skip signals on extreme volatility
- Slippage Control: Ensure realistic entry/exit

### 2. Outcome Tracker (`engine/realtime_outcome_tracker.py`)

**Purpose**: Monitors active signals and detects TP/SL hits  
**Frequency**: Every 10 seconds (configurable via `OUTCOME_CHECK_INTERVAL_SECONDS`)  
**Ownership**: Worker loop only (engine loop disabled in monolith)

#### Outcome Detection Logic

```
For each active signal:
  1. Fetch current price from exchange
  2. Check if price >= TP1 → Partial win (1/3)
  3. Check if price >= TP2 → Win (2/3)
  4. Check if price >= TP3 → Full win (3/3)
  5. Check if price <= SL → Loss
  6. Check if age > 12h → Time stop (expired)
  
  → Create outcome record
  → Notify user (tier-gated updates)
  → Update stats
```

**Outcome Types**:
- `tp1` / `tp2` / `tp3`: Partial/full profits
- `sl`: Stop loss hit (loss)
- `expired`: 12-hour expiry reached
- `invalidated`: Manual correction
- `time_stop`: Time-based exit

**User Notifications** (Tier-Gated):
- **FREE**: Loss only
- **PREMIUM**: Loss + Final TP
- **VIP**: All TP updates + SL notification (real-time)

### 3. Telegram Bot (`signalrank_telegram/bot.py`)

**Mode**: Webhook (production) or Polling (fallback)  
**Command Handlers**: 60+ commands across 6 tiers  
**Message Types**:
- Signal delivery
- Outcome notifications
- Performance stats
- User account management
- Admin broadcasts

#### Bot Features
- Command rate limiting
- Audit logging (who ran what command)
- Tier-based access control (OWNER > ADMIN > VIP > PREMIUM > FREE)
- Caching for performance
- Error recovery with scheduled retries

### 4. Web API & Webhooks (`web/app.py`)

**Endpoints**:
- `POST /telegram/webhook` - Telegram updates
- `POST /paystack/webhook` - Payment events
- `POST /user/{user_id}/webhook` - User custom webhooks
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics

### 5. Worker Loop (`worker/worker.py`)

**Purpose**: Background maintenance tasks  
**Tasks Managed**:
- Outcome tracking
- Market monitoring  
- Subscription expiry checks
- ML model retraining (daily)
- Data drift detection (hourly)

**Auto-Restart**: All tasks automatically restart if they crash

---

## Command Reference

### Public Commands (All Users)

#### Information
- `/start` - Begin using the bot
- `/help` - Command help menu
- `/about` - Bot information
- `/faq` - Frequently asked questions
- `/disclaimer` - Risk disclaimer (must accept)

#### Signal Discovery
- `/signals` - View active signals (score-filtered by tier)
- `/signal <ID>` - Details of specific signal
- `/proof` - Top 5 proof signals (FREE only)
- `/outcome <ID>` - Result of closed signal

#### Account Management
- `/account` - Account summary
- `/status` - Current stats (tier, win rate, R multiple)
- `/myid` - Your Telegram user ID
- `/apikey` - Generate/rotate API token (30-day TTL)
- `/language` - Change bot language
- `/setwebhook <URL>` - Register custom webhook

### Premium Features

#### Trading Configuration
- `/setlot <size>` - Fixed lot size (PREMIUM only)
- `/setrisk <pct>` - Risk-based sizing (VIP only)
- `/execution <mode>` - Manual/Auto execution (VIP only)
- `/drawdown <pct>` - Daily drawdown guard (VIP only)

#### Performance Analytics
- `/performance` - Win rate, R multiple, Sharpe ratio
- `/quality` - Signal quality breakdown
- `/history` - Closed signals history
- `/stats` - Detailed trading statistics
- `/report` - Custom date range analysis
- `/portfolio` - Portfolio allocation (if MT5 linked)
- `/market` - Current market conditions

#### Referral System
- `/invite` - Referral link
- `/referral` - Referral statistics
- `/referral_leaderboard` - Top 10 referrers
- `/referral_rewards` - Bonus breakdown

#### Subscription
- `/pricing` - Tier comparison
- `/upgrade` - Premium subscription
- `/tiers` - Feature matrix
- `/elite` - Early access program
- `/cancel` - Cancel subscription

### Admin Commands (OWNER/ADMIN only)

#### Broadcasting
- `/broadcast <msg>` - Send to all users with rate limiting
- `/admin` - Admin dashboard
- `/admin_top_assets` - Top traded symbols
- `/admin_top_strategies` - Strategy performance
- `/admin_user_engagement` - User activity

#### System Health
- `/selfcheck` - System diagnostics
- `/ops_health` - Health check report
- `/version` - Bot version & commit
- `/notify <msg>` - Send to owners
- `/feedback` - Collected user feedback

#### Manual Operations
- `/correct_signal <ID>` - Manual outcome override
- `/dev_force_signal` - Create test signal
- `/dev_pause` / `/dev_resume` - Kill-switch
- `/assets` - Managed asset list
- `/force_market_scan` - Trigger scan immediately

---

## Database Schema

### Core Tables

#### `users`
```sql
CREATE TABLE users (
  id BIGSERIAL PRIMARY KEY,
  telegram_user_id BIGINT UNIQUE NOT NULL,
  username VARCHAR,
  tier VARCHAR (FREE|PREMIUM|VIP|ADMIN|OWNER),
  premium_until TIMESTAMP,
  auto_renew BOOLEAN DEFAULT FALSE,
  
  -- User preferences
  execution_mode VARCHAR (manual|automatic),
  auto_signals_daily_limit INTEGER DEFAULT 3,
  max_daily_drawdown_pct FLOAT DEFAULT 8.0,
  
  -- Trading settings
  lot_size FLOAT,
  risk_pct FLOAT DEFAULT 1.0,
  
  -- Acceptance
  accepted_terms BOOLEAN DEFAULT FALSE,
  
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

#### `signals`
```sql
CREATE TABLE signals (
  signal_id VARCHAR PRIMARY KEY,
  asset VARCHAR NOT NULL,
  timeframe VARCHAR (1h|4h|1d),
  
  direction VARCHAR (LONG|SHORT),
  entry FLOAT NOT NULL,
  stop_loss FLOAT NOT NULL,
  take_profit FLOAT NOT NULL,
  
  -- Scoring
  score FLOAT (0-100),
  strength VARCHAR (weak|moderate|strong),
  regime VARCHAR (bullish|bearish|ranging),
  strategy_name VARCHAR,
  ml_probability FLOAT (0-1),
  
  -- Expiry & archiving
  created_at TIMESTAMP DEFAULT NOW(),
  expires_at TIMESTAMP DEFAULT NOW() + '12 hours',
  archived_at TIMESTAMP
);
```

#### `outcomes`
```sql
CREATE TABLE outcomes (
  outcome_id BIGSERIAL PRIMARY KEY,
  signal_id VARCHAR UNIQUE REFERENCES signals(signal_id),
  
  status VARCHAR (tp1|tp2|tp3|sl|expired|invalidated),
  canonical_outcome VARCHAR (win|loss|neutral),
  
  -- Financial
  r_multiple FLOAT,
  percent FLOAT,
  
  closed_at TIMESTAMP DEFAULT NOW(),
  meta JSONB
);
```

#### `subscriptions`
```sql
CREATE TABLE subscriptions (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT REFERENCES users(id),
  
  tier VARCHAR (FREE|PREMIUM|VIP),
  status VARCHAR (active|expired|cancelled),
  
  expires_at TIMESTAMP,
  paystack_reference VARCHAR UNIQUE,
  
  created_at TIMESTAMP DEFAULT NOW()
);
```

#### `api_tokens`
```sql
CREATE TABLE api_tokens (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT REFERENCES users(id),
  
  token_hash VARCHAR UNIQUE NOT NULL,
  scope VARCHAR (signals:read),
  
  expires_at TIMESTAMP,
  last_used_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW()
);
```

#### `outcome_notifications`
```sql
CREATE TABLE outcome_notifications (
  id BIGSERIAL PRIMARY KEY,
  signal_id VARCHAR REFERENCES signals(signal_id),
  telegram_user_id BIGINT,
  
  delivery_state VARCHAR (pending|sent|failed),
  delivered_at TIMESTAMP,
  retry_count INTEGER DEFAULT 0
);
```

#### Supporting Tables
- `market_candles` - OHLCV data (indexed by symbol, timeframe, time)
- `market_ticks` - Latest price ticks
- `mt_links` - Broker account connections
- `user_webhooks` - Custom webhook registrations
- `trades` - Position tracking
- `decision_log` - Engine decision audit trail
- `apscheduler_jobs` - Scheduled job store
- Additional auxiliary tables for analytics, caching, etc.

### Key Indexes
```sql
-- Performance-critical
CREATE INDEX idx_signals_asset_tf_created ON signals(asset, timeframe, created_at);
CREATE INDEX idx_outcomes_signal_status ON outcomes(signal_id, status);
CREATE INDEX idx_users_tier_created ON users(tier, created_at);
CREATE INDEX idx_candles_symbol_tf_time ON market_candles(symbol, timeframe, open_time_ms);
```

---

## Configuration & Deployment

### Local Development Setup

```bash
# 1. Clone repo
git clone <repo-url>
cd SignalRankAI

# 2. Python venv
python3.11 -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Database (PostgreSQL)
# Create local PostgreSQL instance
createdb signalrank_ai

# 5. Environment (.env file)
cp .env.complete .env
# Edit with your local values:
#   DATABASE_URL=postgresql://user:pass@localhost:5432/signalrank_ai
#   TELEGRAM_BOT_TOKEN=<from BotFather>
#   OWNER_TELEGRAM_ID=<your ID>

# 6. Run migrations
python -m alembic upgrade head

# 7. Start bot (local development)
python main.py  # Uses RUN_MODE=engine or railway_main.py for all-in-one

# OR for full monolith:
uvicorn railway_main:app --reload
```

### Railway Deployment

```bash
# 1. Connect Railway project
railway link

# 2. Add PostgreSQL plugin
railway add --plugin postgres

# 3. Add Redis plugin (optional but recommended)
railway add --plugin redis

# 4. Set environment variables
railway environment add TELEGRAM_BOT_TOKEN "..."
railway environment add OWNER_TELEGRAM_ID "..."
... (add all from .env template)

# 5. Deploy
railway deploy

# 6. View logs
railway logs
```

### Key Environment Variables Explained

| Variable | Purpose | Example |
|----------|---------|---------|
| `DATABASE_URL` | PostgreSQL connection | `postgresql+asyncpg://...` |
| `TELEGRAM_BOT_TOKEN` | Bot authentication | `123456789:ABCdef...` |
| `OWNER_TELEGRAM_ID` | Admin user ID | `987654321` |
| `RUN_MODE` | Service mode | `all` (monolith) |
| `ENGINE_CYCLE_SLEEP_SECONDS` | Signal generation frequency | `30` |
| `STARTUP_STRICT_SCHEMA_READY` | Wait for DB before starting | `1` |
| `AUTO_MIGRATE` | Run migrations automatically | `0` (manual) |
| `REDIS_URL` | Cache backend | `redis://...` or empty |
| `ML_TRAIN_ENABLED` | ML retraining | `true` |
| `WEBHOOK_QUEUE_USE_REDIS` | Queue backend | `1` |

---

## Troubleshooting Guide

### Issue: Signals Not Generating

**Symptoms**: No `[engine] heartbeat: cycle=X` logs, no signals in database

**Diagnosis**:
```python
# Check if engine loop started
# Look for "[startup] Engine loop task created" in logs
# Look for "[engine] heartbeat:" every 30s

# If missing:
# 1. Check RUN_ENGINE_LOOP=1
# 2. Check no syntax errors: python -m py_compile engine/core.py
# 3. Check DB connection: psql $DATABASE_URL
```

**Solutions**:
1. **Verify DB connection**: 
   ```bash
   railway conn postgres
   # Or locally: psql postgresql://user:pass@localhost:5432/signalrank_ai
   ```

2. **Set environment variables**:
   ```bash
   RUN_ENGINE_LOOP=1
   ENGINE_CYCLE_SLEEP_SECONDS=30
   AUTO_MIGRATE=0
   STARTUP_STRICT_SCHEMA_READY=1
   ```

3. **Check asset availability**:
   - Ensure `TRADABLE_ASSETS` env var is set, OR
   - Ensure Binance API is working (crypto discovery), OR
   - Ensure at least one FX_PAIR is configured

4. **Restart service**:
   ```bash
   railway redeploy  # or restart locally
   ```

### Issue: Webhook Not Receiving Telegram Updates

**Symptoms**: Commands don't trigger, no `[webhook] ingress received update_id=X` logs

**Diagnosis**:
```python
# Check webhook registration
/ops_health  # Should show webhook_url registered

# Check railway domain
# Railway auto-generates https://<random>.railway.app
```

**Solutions**:
1. **Verify webhook URL**:
   ```bash
   # Should match Railway domain
   TELEGRAM_WEBHOOK_URL should be https://<your-railway>.railway.app
   ```

2. **Register webhook manually**:
   ```bash
   # Restart app or send /ops_health to bot
   ```

3. **Check Telegram bot token**:
   ```bash
   # Must be valid and not revoked
   # Regenerate from @BotFather if needed
   ```

### Issue: Command Handler Crashes

**Symptoms**: Bot is responsive but commands return errors like "Unknown command" or timeout

**Root Cause**: Usually missing user schema columns (fresh DB)

**Solutions**:
```bash
# 1. Trigger schema bootstrap
STARTUP_SCHEMA_BOOTSTRAP=1
STARTUP_STRICT_SCHEMA_READY=1

# 2. Or manually run migrations
python -m alembic upgrade head

# 3. Check schema has these columns:
SELECT * FROM information_schema.columns WHERE table_name='users';
# Should include: max_daily_drawdown_pct, execution_mode, auto_signals_daily_limit
```

### Issue: Database Connection Errors

**Symptoms**: `asyncpg: Future attached to a different loop`, connection timeouts

**Root Cause**: Event loop/connection pooling mismatch on Railway

**Solutions**:
```bash
# 1. Use NullPool (no pooling)
DB_POOL_SIZE=1
DB_MAX_OVERFLOW=0

# 2. Reduce pool recycle
DB_POOL_RECYCLE_SECONDS=300  # Recycle every 5 min

# 3. Increase timeout
DB_POOL_TIMEOUT_SECONDS=30
DB_RETRY_ATTEMPTS=5
```

### Issue: Redis Connection Failing

**Symptoms**: `webhook_queue_use_redis=False` despite REDIS_URL set

**Diagnosis**:
```python
# Redis may not be reachable from app container
# Check: redis-cli ping
```

**Solutions**:
1. **Disable Redis** (use in-process queue):
   ```bash
   WEBHOOK_QUEUE_USE_REDIS=0
   ```

2. **Fix Redis URL**:
   ```bash
   # Railway auto-detects these (in order):
   REDIS_URL
   REDIS_PRIVATE_URL
   REDIS_PUBLIC_URL
   REDIS_INTERNAL_URL
   ```

3. **Check Redis service**:
   ```bash
   railway logs -s redis
   ```

### Issue: High Memory Usage / Out of Memory

**Symptoms**: Service crashes with OOMKilled, low Postgres query performance

**Root Cause**: Railway free tier has 256 MB limit; queries, caching, and models consume memory

**Solutions**:
```bash
# 1. Reduce model threading
XGB_NTHREAD=1  # Default 2

# 2. Limit candle cache
MARKET_DATA_CACHE_TTL_SECONDS=30  # Shorter TTL

# 3. Reduce batch size
CYCLE_BATCH_SIZE=10  # Process fewer assets per cycle

# 4. Disable optional features
CRYPTO_WS_ENABLED=false
ML_TRAIN_ENABLED=false
ENABLE_NEWS=false

# 5. Upgrade to Railway paid tier if needed
```

### Issue: Background Tasks Restarting Unexpectedly

**Symptoms**: Engine/Worker logs show crashes and auto-restarts (every few minutes)

**Debug**:
```bash
# Check full exception logs
railway logs --follow | grep -i "crashed"

# Check memory/CPU
# If out of memory, see above solutions

# Check for infinite loops or blocking I/O
```

---

## Testing & Verification

### Automated Test Suite

```bash
# Run all tests
pytest tests/ -v

# Specific test file
pytest tests/test_engine_loop.py -v

# With coverage
pytest tests/ --cov=engine --cov=signalrank_telegram --cov=db
```

### Manual Testing Checklist

**1. Signal Generation**:
```bash
# Send command
/signals

# Check logs
railway logs | grep -i "pipeline\|heartbeat\|dispatch"

# Expected:
# [engine] heartbeat: cycle=X running
# [engine] batch_complete assets=Y dispatched=Z
```

**2. Outcome Detection**:
```bash
# Send command
/history  # Should show past signals

# Check logs
railway logs | grep -i "outcome\|tp\|sl"

# Expected:
# [outcome] signal_id=X matched status=tp at 1.234
```

**3. Command Execution**:
```bash
# In Telegram
/help
/account
/status
/performance

# All should respond instantly (< 5s)
```

**4. Payment Integration** (if enabled):
```bash
# Check Paystack webhook
# Attempt /upgrade
# Verify subscription is created
# Check database: SELECT * FROM subscriptions;
```

### Load Testing (Optional)

```bash
# Simulate users
locust -f tests/locustfile.py --host=http://localhost:8000

# Monitor Railway
railway logs -f
```

---

## Feature Matrix

### By Tier

| Feature | FREE | PREMIUM | VIP | ADMIN | OWNER |
|---------|------|---------|-----|-------|-------|
| View Signals | ❌ Limited | ✅ | ✅ | ✅ | ✅ |
| Daily Signal Limit | 3 | 10 | Unlimited | N/A | N/A |
| Min Score Filter | 80 | 75 | 70 | N/A | N/A |
| Outcome Updates | SL only | Final TP | All (TP1/TP2/TP3/SL) | All | All |
| API Access | ❌ | ✅ Limited | ✅ | ❌ | ✅ |
| Custom Webhooks | ❌ | ✅ | ✅ | ❌ | ✅ |
| MT5 Link | Limited | ✅ | ✅ | ✅ | ✅ |
| Auto-Execution | ❌ | 1/day max | 10/day max | 10/day | Unlimited |
| Referral Bonuses | ❌ | ✅ | ✅ | N/A | N/A |
| Dedicated Support | ❌ | Limited | 24h | Yes | Yes |

### Asset Classes

| Asset | Availability | Default Timeframes | Strategies |
|-------|--------------|-------------------|-----------|
| Crypto (Binance) | ✅ | 1h, 4h, 1d | Trend, Momentum, Volatility, Confluence |
| Forex (OANDA) | ✅ | 1h, 4h, 1d | Trend, Momentum, Structure |
| Stocks (yfinance) | ✅ | 1h, 4h, 1d | Trend, Momentum |
| Commodities (OANDA) | ✅ | 1h, 4h, 1d | Volatility, Structure |

### External Service Integration

| Service | Purpose | Status | Free Tier | Notes |
|---------|---------|--------|-----------|-------|
| Telegram | Bot hosting | ✅ Core | Yes | 100+ users free |
| PostgreSQL | Database | ✅ Core | Railway | 256GB free (Railway plugin) |
| Redis | Cache | ⚠️ Optional | Railway | Fallback to in-process |
| Binance | Crypto data | ✅ | Yes | 1200 REQ/min limit |
| OANDA | Forex data | ✅ | Yes | Limited historical |
| yfinance | Stock data | ✅ | Yes | Rate limited |
| NewsAPI | Sentiment | ✅ | 100 req/day | Sentiment analysis |
| Paystack | Payments | Optional | No | ~5% fee |
| Sentry | Error tracking | Optional | 5k events/month | Error monitoring |
| Gemini | AI Analysis (NEW) | Coming | Limited | Experimental |

---

## API Endpoints

### Public Endpoints

#### GET /health
Health check endpoint
```bash
curl http://localhost:8000/health
# Response: {"status":"ok"}
```

#### GET /metrics
Prometheus metrics
```bash
curl http://localhost:8000/metrics | grep signalrankai_
```

### Webhook Endpoints (Async)

#### POST /telegram/webhook
Receives Telegram updates
- Automatic via Telegram when registered
- Processes commands and messages

#### POST /paystack/webhook (if enabled)
Receives payment events
- Verify HMAC signature
- Update subscription tier
- Send confirmation

### User API (if enabled)

- **GET** `/api/signals` - List recent signals
- **GET** `/api/signals/<id>` - Signal details
- **GET** `/api/account` - User account info
- **POST** `/api/tokens` - Generate API token

Requires `Authorization: Bearer <token>` header

---

## Enhancement Roadmap

### Q2 2026 - In Progress

✅ **Gemini AI Integration**
- AI-powered signal analysis
- Enhanced trade recommendations
- Risk assessment automation

✅ **Improved Error Logging**
- Structured log output
- Sentry integration
- Better debugging info

✅ **Performance Optimization**
- Memory profiling complete
- Connection pooling hardened
- Query optimization done

### Q3 2026 - Planned

🔶 **Multi-Broker Execution**
- Binance native integration
- Bybit support
- Alpaca integration

🔶 **Advanced DCA**
- Volatility-adaptive DCA
- ML-based profit-taking
- Correlation-aware allocation

🔶 **Portfolio Analysis**
- Real portfolio sync (via API)
- Multi-broker tracking
- Tax reporting

### Q4 2026 - Future

🔵 **Machine Learning Enhancements**
- Reinforcement learning for strategy selection
- Adaptive model weighting
- Live feature importance tracking

🔵 **Mobile App**
- iOS/Android apps
- Push notifications
- Offline portfolio view

🔵 **Community Features**
- Signal marketplace
- Strategy sharing
- Group risk management

---

## Quick Reference

### Directory Structure

```
SignalRankAI/
├── main.py                      # Entry point (standard)
├── railway_main.py              # Entry point (Railway monolith)
├── config.py                    # Configuration management
├── requirements.txt             # Python dependencies
│
├── core/                        # Core utilities
│   ├── settings.py             # Pydantic settings
│   ├── redis_state.py          # Redis state management
│   └── tier_constants.py       # Tier definitions
│
├── db/                          # Database layer
│   ├── models.py               # SQLAlchemy ORM models
│   ├── session.py              # Async session management
│   ├── repository.py           # Data access layer
│   ├── pg_compat.py            # PostgreSQL write helpers
│   ├── pg_features.py          # Query builders
│   └── migrations/             # Alembic auto-migrations
│
├── engine/                      # Signal generation engine
│   ├── core.py                 # Main loop
│   ├── strategies/             # Strategy implementations
│   ├── filters.py              # Pre-delivery filters
│   ├── advanced_filters.py     # ML/regime filters
│   ├── risk_manager.py         # Position sizing
│   ├── ml.py                   # XGBoost integration
│   ├── scoring.py              # Signal scoring
│   ├── consensus.py            # Multi-indicator agreement
│   └── realtime_outcome_tracker.py  # Outcome detection
│
├── data/                        # Market data providers
│   ├── fetcher.py              # Unified data API
│   ├── providers.py            # Provider implementations
│   ├── indicators.py           # Technical indicators
│   ├── market_data.py          # Data processing
│   └── connectors/             # Exchange connectors
│
├── signalrank_telegram/         # Telegram bot
│   ├── bot.py                  # Bot entry point
│   ├── commands.py             # User commands
│   ├── owner_commands.py       # Admin commands
│   ├── tier_delivery.py        # Tier-based filtering
│   ├── formatter.py            # Message formatting
│   └── payment_handler.py      # Payment processing
│
├── worker/                      # Background worker
│   ├── worker.py               # Worker loop
│   ├── market_monitor.py       # Market alerts
│   └── ...
│
├── web/                         # FastAPI app
│   └── app.py                  # Web endpoints
│
├── ml/                          # Machine learning
│   ├── retrain.py              # Model training
│   └── model.json              # XGBoost model
│
├── tests/                       # Test suite
│   └── test_*.py               # Various test files
│
└── alembic/                     # Alembic migrations
    ├── versions/               # Migration scripts
    └── env.py                  # Alembic config
```

### Common Commands

```bash
# Run locally
uvicorn railway_main:app --reload --port 8000

# Deploy to Railway
railway up

# View logs
railway logs -f

# Connect to database
railway conn postgres

# Run tests
pytest tests/ -v --tb=short

# Format code
black .

# Check types
mypy engine/core.py

# Lint
flake8 . --max-line-length=120
```

---

##Summary

SignalRankAI is a **production-grade, multi-asset signal generation platform** with:
- ✅ 60+ Telegram commands
- ✅ Crypto, Forex, Stock, & Commodity signals
- ✅ ML-powered filtering
- ✅ Outcome tracking
- ✅ Payment processing
- ✅ Railway-optimized monolith architecture
- ✅ Comprehensive error handling &auto-recovery

For support, consult the `/help` command in Telegram or check logs with `railway logs`.

