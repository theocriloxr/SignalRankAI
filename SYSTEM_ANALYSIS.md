# SignalRankAI System Analysis

## Overview
SignalRankAI is a trading signal generation and delivery system that:
1. Fetches market data from multiple providers (Binance, CryptoCompare, TwelveData, Polygon, Yahoo Finance)
2. Runs trading strategies to generate signals
3. Validates/deduplicates/scores signals
4. Delivers signals to users via Telegram with tier-based access control

## Architecture

### Entry Points
- **main.py**: Determines RUN_MODE (all/web/bot/worker/engine) from Railway service name
- **railway_main.py**: FastAPI app with `/telegram/webhook` endpoint for Telegram bot updates

### Core Components
1. **Engine Loop** (`engine/core.py`): Generates signals every ~30 seconds
2. **Worker Loop** (`worker/worker.py`): Tracks trade outcomes
3. **Telegram Bot** (`signalrank_telegram/bot.py`): Handles user commands
4. **Web Server** (`web/app.py`): API endpoints

### Data Flow
```
Market Data Providers → Strategies → Normalize/Dedupe → Consensus → 
Risk/ML → Scoring → Advanced Filters → Store → Delivery
```

## Issues Identified from Logs

### 1. Engine Generates 0 Final Signals
```
engine] cycle=1 assets=20 generated_signals=0 max_score=62.68 
max_score_pre_threshold=62.68 strategy_signals=120 normalized=120 
consensus=64 selected=29 unique=29 strict_candidates=26 risk_passed=26 
final_signals=0 stored=0
```

**Analysis**: 
- 120 strategy signals generated → 120 normalized → 64 after consensus
- But final_signals=0 - signals dropped somewhere in scoring/filtering
- This can happen if:
  - Score threshold too high (PREMIUM_SCORE_THRESHOLD=70)
  - Confluence gate blocking
  - ML hard filter threshold
  - Expectancy gate (< 0.15)

**Likely Causes**:
1. Score threshold blocking: min_score_threshold=70 in `_current_min_score_threshold()`
2. Expectancy gate: `live_exp < 0.15` causes rejection
3. The max_score=62.68 is below the 70 threshold!

### 2. Binance Pairs Disabled
```
[data.pair_discovery] Binance pairs disabled: Service unavailable from 
a restricted location according to 'b. Eligibility' in 
https://www.binance.com/en/terms.
```
- Cannot use Binance for data (location restriction)

### 3. Data Provider Rate Limits
```
[data.providers] [twelvedata] fetch_failed symbol=BRENT msg=You 
have run out of API credits for the current minute
[data.providers] [polygon] fetch_failed symbol=BRENT status=429
```
- TwelveData quota exceeded
- Polygon rate limited

### 4. SAWarning - Connection Not Returned to Pool
```
SAWarning: The garbage collector is trying to clean up non-checked-in 
connection <AdaptedConnection <asyncpg.connection.Connection object>>
Please ensure that SQLAlchemy pooled connections are returned to the pool 
explicitly, either by calling `close()` or by using appropriate 
context managers.
```
- Connection leak in engine/core.py around line 2160

### 5. Zero Final Signals Issue
The max_score_pre_threshold=62.68 is BELOW the default threshold of 70!

**Root Cause**: Engine generates signals but they're scored around 62.68 max, which is below the 70 threshold, so all get filtered out.

## Solutions

### Priority 1: Fix Signal Generation to Meet Threshold
1. Lower `PREMIUM_SCORE_THRESHOLD` to ~60 or calculate dynamically
2. Adjust scoring algorithm to produce scores in 70+ range
3. Or adjust threshold based on average signal quality

### Priority 2: Fix DB Connection Leak
Ensure all DB operations use context managers or explicit close()

### Priority 3: Provider Fallbacks
Ensure CryptoCompare/Yahoo Finance work when Binance unavailable

### Priority 4: Data Provider Rate Limits
- Upgrade TwelveData plan or use more providers
- Cache data more aggressively
- Reduce BRENT/commodity queries

## Configuration

### Critical Environment Variables
```
TELEGRAM_BOT_TOKEN - Telegram bot token
DATABASE_URL - PostgreSQL connection
REDIS_URL - Redis connection
OWNER_IDS - Admin user IDs
PREMIUM_SCORE_THRESHOLD - Min score (default 70)
ML_PROB_THRESHOLD - ML confidence threshold (default 0.55)
TRADABLE_ASSETS - Comma-separated asset list
ENGINE_CYCLE_SLEEP_SECONDS - Cycle interval (default 30)
ENGINE_UNIVERSE_CAP - Max assets per cycle (default 20)
```

## Tier System
- **free**: 3 signals/day
- **silver**: 10 signals/day  
- **gold**: 25 signals/day
- **platinum/premium**: Unlimited

## Telegram Bot Commands
- `/start` - Register user
- `/signals` - Get recent signals
- `/status` - Account status
- `/price <symbol>` - Current price
- `/subscribe <tier>` - Change subscription
- `/help` - Show commands

## Database Models

### Core Tables
- **users**: Telegram user records with tier
- **signals**: Generated trading signals
- **outcomes**: Signal resolution (TP/SL)
- **subscriptions**: User tier subscriptions
- **signal_deliveries**: Sent signal tracking
- **mt5_executions**: MetaTrader execution records
- **decision_log**: Engine decision tracking
- **ml_rejected_signals**: ML-filtered signals for training

## Health Checks
- `/healthz` - Fast liveness probe
- `/telegram/webhook_status` - Bot diagnostics
