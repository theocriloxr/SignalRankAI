# SignalRankAI - Comprehensive System Analysis & Fixes

## Executive Summary

Based on my analysis of the codebase and the provided logs, I've identified multiple issues preventing the system from generating signals properly. Here's my complete understanding:

---

## System Architecture Overview

SignalRankAI is a **multi-asset signal generation platform** running as a unified Railway monolith:

```
FastAPI (railway_main.py)
├── Signal Engine Loop (generates signals every 30s)
├── Worker Loop (outcome tracking)
├── Telegram Bot (webhook mode)
└── PostgreSQL + Redis
```

### Signal Generation Pipeline
```
Assets → Fetch Data → Indicators → Strategies → Consensus → Risk/ML → Scoring → Filters → Store → Deliver
```

---

## Issues Identified from Logs

### 1. CRITICAL: Zero Final Signals Despite 120 Strategy Signals

**Log excerpt:**
```
[engine] cycle=1 assets=20 generated_signals=0 max_score=62.68 
max_score_pre_threshold=62.68 strategy_signals=120 normalized=120 
consensus=64 selected=29 unique=29 strict_candidates=26 
risk_passed=26 final_signals=0 stored=0
```

**Analysis:** 
- 120 strategy signals generated ✓
- 120 normalized ✓  
- 64 passed consensus filter
- 29 unique selected
- 26 strict candidates
- 26 risk passed
- **0 final signals stored**

**Root Cause:** The consensus filter appears to be blocking all signals AFTER passing 64 through. Looking at `engine/core.py`:

```python
# Consensus filter - NO FALLBACK IN PROD
try:
    consensus_signals = apply_consensus_filter(normalized)
    if not consensus_signals and _env_bool("PROD_MODE", True):
        logger.warning(f"Consensus empty for {asset} - blocking (PROD policy)")
        continue  # Skip asset entirely
```

**The Problem:** The `PROD_MODE` is set to True by default, and the consensus filter in production mode blocks ALL signals when consensus returns empty - but 64 went THROUGH consensus. This suggests a bug where signals are passing consensus but then getting rejected somewhere in the scoring/filtering phase.

Looking further, there's a **duplicate line** in the stats:
```python
pipeline_stats["consensus"] += len(consensus_signals)
pipeline_stats["consensus"] += len(consensus_signals)  # DUPLICATE!
```

More critically, in the final gates section:
```python
# Final gates: score + expectancy
min_score_threshold = _current_min_score_threshold()
if sig.get('score', 0) < min_score_threshold:
    sig['rejection_reason'] = f"score {sig.get('score',0)} < {min_score_threshold}"
    ...

# Expectancy gate (Phase 3 full impl)
live_exp = float(sig.get('live_expectancy', 0.15))
if live_exp < 0.15:
    sig['rejection_reason'] = f"low expectancy {live_exp:.3f}"
    ...
```

**The REAL Issue:** Signals are failing the **expectancy gate** (`live_expectancy < 0.15`). The `live_expectancy` field is likely not being populated, defaulting to 0.15 which equals the threshold, but there's a bug:
```python
live_exp = float(sig.get('live_expectancy', 0.15))
if live_exp < 0.15:  # This is 0.15 < 0.15 = False!
```

Wait, that's not right. Let me check again... Actually `0.15 < 0.15` is False. The issue might be that `live_expectancy` IS being set to something less than 0.15, or the default is intended to be compared differently.

Actually wait - if `live_expectancy` is missing (None), then `float(None)` = 0.0, so 0.0 < 0.15 = True, and signals get rejected!

---

### 2. CRITICAL: Provider Rate Limits

**Log excerpt:**
```
[err] WARNI [data.providers] [twelvedata] fetch_failed symbol=BRENT 
msg=You have run out of API credits for the current minute. 

[err] WARNI [data.providers] [polygon] fetch_failed symbol=BRENT status=429
```

**Solutions Needed:**
1. Add more fallback providers
2. Implement circuit breaker to deprioritize failing providers
3. Add Yahoo Finance as additional fallback
4. Cache data more aggressively

---

### 3. CRITICAL: Binance Pairs Disabled

**Log excerpt:**
```
[data.pair_discovery] Binance pairs disabled: Service unavailable from a 
restricted location according to 'b. Eligibility'
```

**Cause:** Binance blocked due to geographic restriction (your Railway server is in a restricted location)

**Solutions:**
1. Use alternative discovery methods (CryptoCompare, CoinGecko)
2. Add manual asset list in TRADABLE_ASSETS env var

---

### 4. SQLAlchemy Connection Pool Warning

**Log excerpt:**
```
SAWarning: The garbage collector is trying to clean up non-checked-in 
connection <AdaptedConnection <asyncpg.connection.Connection 
object at 0x7fd71247fd30>>
```

**Solution:** Ensure connections are properly returned to pool using context managers.

---

### 5. Webhook Working Fine (No Issue)

```
[webhook] periodic status: url_set=True pending=0
```

The webhook is properly registered and working.

---

## Files That Need Modification

### 1. engine/core.py
- Fix the expectancy gate logic bug
- Remove duplicate consensus stats line
- Add better logging for signal rejections

### 2. data/fetcher.py  
- Add more provider fallbacks
- Implement circuit breaker pattern
- Add Yahoo Finance

### 3. data/pair_discovery.py
- Add fallback when Binance unavailable
- Use CryptoCompare for crypto discovery

### 4. db/session.py
- Ensure proper connection cleanup

---

## Plan

### Phase 1: Fix Signal Generation
1. Fix expectancy gate (live_expectancy missing or 0)
2. Fix consensus/production mode issue
3. Add debug logging

### Phase 2: Fix Providers  
1. Add Yahoo Finance fallback
2. Improve circuit breaker
3. Better rate limit handling

### Phase 3: Fix Discovery
1. Fallback when Binance unavailable
2. Use CryptoCompare

### Phase 4: Database
1. Fix connection pool warnings
2. Ensure context managers

---

## Testing After Fixes

```bash
# Check logs for signal generation
railway logs | grep -E "final_signals|stored"

# Expected:
# final_signals=5 stored=5  (or similar)
