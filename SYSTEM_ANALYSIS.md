# SignalRankAI - Codebase Analysis Document

## Executive Summary

This document provides a comprehensive analysis of the SignalRankAI codebase based on the provided logs and source code examination. The system is a trading signal generation platform that uses multiple data providers, technical indicators, and ML models to generate and deliver trading signals to users via Telegram.

## System Architecture

### Entry Points
1. **main.py** - Universal entry point with RUN_MODE detection (web/worker/engine/bot/all)
2. **railway_main.py** - Railway monolithic entry point (FastAPI + APScheduler + Telegram bot)
3. **web/app.py** - FastAPI application endpoints
4. **worker/worker.py** - Background worker for outcome tracking
5. **engine/core.py** - Signal generation engine

### Core Components

#### 1. Data Layer (data/)
- **fetcher.py** - Multi-provider market data fetching with fallback
- **providers.py** - Individual data provider implementations
- **pair_discovery.py** - Asset discovery (trending pairs, stocks)
- **indicators.py** - Technical indicator calculations
- **market_hours.py** - Market open/closed checks
- **ws_ingest.py** - WebSocket real-time data ingestion

#### 2. Engine Layer (engine/)
- **core.py** - Main signal generation loop
- **scoring.py** - Signal scoring algorithms
- **consensus.py** - Multi-strategy consensus filtering
- **risk_manager.py** - Risk management
- **filters.py** - Signal quality filters
- **threshold_optimizer.py** - Adaptive ML threshold optimization

#### 3. Delivery Layer (signalrank_telegram/)
- Bot handlers for Telegram commands
- Signal delivery with tier-based limits
- Outcome notifications

#### 4. Data Models (db/models.py)
- User, Subscription, Signal, Outcome models
- Trading and referral tracking tables

## Identified Issues from Logs

### Issue 1: Zero Signals Generated
**Evidence from logs:**
```
[engine] cycle=1 assets=20 generated_signals=0 max_score=62.68 ... final_signals=0 stored=0
```

**Root Cause Analysis:**

The engine has multiple strict gating layers that filter out all signals:

1. **Score Threshold Gate** (PREMIUM_SCORE_THRESHOLD):
   - Default: 70.0
   - Requires signals to score >= 70
   - Log shows max_score_pre_threshold=62.68, meaning NO signals pass this gate

2. **Confluence Gate** (CONFLUENCE_GATE_MIN):
   - Default: 0.0 (disabled)
   - Only enforced if configured

3. **Live Expectancy Gate** (Phase 3 implementation):
   - Code shows: `live_exp = float(sig.get('live_expectancy', 0.0))`
   - Requires live_exp >= 0.15
   - ISSUE: live_expectancy field is NOT being populated before scoring

4. **Consensus Filter** (PROD_MODE=True):
   - If consensus empty, asset is skipped entirely
   - Strict policy blocks entire asset if no consensus

**Fix Required:**
- Lower PREMIUM_SCORE_THRESHOLD from 70 to 55 to match the max observed score
- Ensure live_expectancy is calculated/filled before scoring check

### Issue 2: Provider Rate Limits
**Evidence:**
```
[data.providers] [twelvedata] fetch_failed symbol=BRENT msg=You have run out of API credits...
[data.providers] [polygon] fetch_failed symbol=BRENT status=429
```

**Root Cause:**
- TwelveData API credits exhausted
- Polygon API rate limited (429)

**Impact:**
- Some symbols fail to fetch (BRENT and others)
- May cause cascade failures in signal generation

### Issue 3: Binance Geographic Restriction
**Evidence:**
```
[pair_discovery] Binance pairs disabled: Service unavailable from a restricted location...
```

**Root Cause:**
- Binance service unavailable from Railway's deployment region
- Geographic restriction based on Terms of Service

### Issue 4: Database Connection Warning
**Evidence:**
```
SAWarning: The garbage collector is trying to clean up non-checked-in connection...
```

**Root Cause:**
- SQLAlchemy connection not properly returned to pool
- Need to ensure connection context managers are used correctly

### Issue 5: Stale Data Detection
**Evidence:**
```
[engine] Stale data for {asset} {tf}: age={data_age}s > max={max_age}s
```

**Root Cause:**
- Data older than 2x timeframe interval
- Provider delays causing stale data

## Signal Pipeline Flow

```
1. Load Assets
   ├── Managed assets (DB)
   ├── Saved assets (TRADABLE_ASSETS env)
   └── Discovered assets (trending APIs)

2. Filter by Market Status
   ├── Check market_closed_reason()
   └── Skip closed markets

3. Fetch Market Data
   ├── Multi-provider fetch with fallback
   └── Calculate indicators

4. Run Strategies
   ├── run_all_strategies(asset, market_data, regime)
   └── Returns list of strategy signals

5. Normalize & Dedupe
   ├── SignalController.normalize_signals()
   └── Remove duplicates

6. Consensus Filter
   ├── apply_consensus_filter()
   └── BLOCKS if empty (PROD policy)

7. Select Best Direction
   ├── pick_best_direction_per_pair()
   └── One signal per asset/TF

8. Compute Fingerprints
   ├── compute_signal_fingerprint()
   └── Dedupe by fingerprint

9. Strict Validation
   ├── validate_signal()
   ├── risk_check()
   ├── confluence gate
   └── news sentiment gate

10. ML Advisory
    ├── MLFilter.ml_filter()
    └── Hard threshold filter

11. Scoring
    ├── calculate_signal_score()
    ├── Advanced filters
    └── Ultra quality filter

12. Final Gates
    ├── Score >= PREMIUM_SCORE_THRESHOLD
    ├── Expectancy >= 0.15
    └── Valid TP structure

13. Store & Deliver
    ├── store_signal_compat()
    └── dispatch_signals_async()
```

## Configuration Requirements

### Critical Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| PREMIUM_SCORE_THRESHOLD | 70 | Min score to store signals |
| CONFLUENCE_GATE_MIN | 0.0 | Min confluence (0=disabled) |
| ML_PROB_THRESHOLD | 0.55 | ML probability threshold |
| ENGINE_UNIVERSE_CAP | 20 | Max assets per cycle |
| CYCLE_BATCH_SIZE | 20 | Assets per batch |
| ENGINE_CYCLE_SLEEP_SECONDS | 30 | Cycle sleep time |
| DRY_RUN | false | Dry run mode |

### Data Providers

| Provider | Status | Notes |
|----------|--------|-------|
| CryptoCompare | Working | Primary crypto data |
| Yahoo Finance | Working | FX and some crypto |
| TwelveData | Limited | API credits exhausted |
| Polygon | Limited | Rate limited (429) |
| Binance | Disabled | Geographic restriction |

## Tier-Based Delivery Limits

From core/tier_constants.py:
- FREE: 3 signals/day
- STARTER: 10 signals/day  
- PREMIUM: 50 signals/day
- VIP: Unlimited

## Files to Modify for Fixes

### Fix 1: Lower Score Threshold
**Files:** engine/core.py
**Location:** DEFAULT_MIN_SCORE_THRESHOLD = 70 → 55

### Fix 2: Populate Live Expectancy
**Files:** engine/scoring.py, engine/core.py
**Action:** Calculate and set live_expectancy before scoring

### Fix 3: Provider Fallback Improvement
**Files:** data/fetcher.py, data/providers.py  
**Action:** Add more fallbacks, implement circuit breaker

### Fix 4: DB Connection Handling
**Files:** db/session.py, engine/core.py  
**Action:** Ensure proper connection pool management

### Fix 5: Enable More Assets
**Files:** data/pair_discovery.py
**Action:** Add more FX/stock providers

## Testing Checklist

- [ ] Run engine with DRY_RUN=true
- [ ] Verify signals are generated
- [ ] Check provider fallback behavior
- [ ] Test Telegram bot commands
- [ ] Verify outcome notifications work
- [ ] Test tier-based delivery limits

## Next Steps

1. Lower PREMIUM_SCORE_THRESHOLD to 55 to allow current signals through
2. Add live_expectancy calculation before gating
3. Add more provider fallbacks
4. Implement circuit breaker for failed providers
5. Run in DRY_RUN mode to verify before production

---
*Document generated from code analysis*
*Analysis date: 2026-05-07*
