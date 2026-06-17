# SignalRankAI - Comprehensive Fix Plan

## Executive Summary
Based on codebase analysis, SignalRankAI is an institutional-grade multi-asset automated trading platform that evaluates Forex, Crypto, Equities, and Commodities using technical indicators, order flow analysis, and Gemini-powered sentiment analysis. The system has several ongoing issues causing signal starvation (generated_signals=0) that need comprehensive fixing.

---

## Issue 1: Signal Generation Issues (Signal Starvation)

### Problem Analysis
- Engine returns generated_signals=0 despite market data being available
- Multiple threshold gates blocking valid signals
- Data provider failures notfalling back properly

### Root Causes Identified
1. **Threshold Gates**: 
   - ML_PROB_THRESHOLD too high (0.55 default, blocking 82.43 scores)
   - PREMIUM_SCORE_THRESHOLD at 30-85 blocking valid signals
   - ML filter hard blocking signals with prob < 0.15

2. **Data Provider Issues**:
   - Polygon rate limits (429 errors)
   - Yahoo Finance formatting issues
   - Binance geo-blocking

3. **Strategy Execution**:
   - Early-exit checks skipping ALL strategies when market data appears empty
   - Indicator validation too strict

### Fix Plan
```
Step 1.1: Adjust thresholds in config.py
- ML_PROB_THRESHOLD: 0.25 (from 0.55)
- PREMIUM_SCORE_THRESHOLD: 30 (from 85)
- ML_HARD_FILTER_MIN: 0.15 (from 0.55)

Step 1.2: Fix data providers in data/fetcher.py
- Add more aggressive fallbacks (CCXT -> Yahoo -> CryptoCompare)
- Add circuit breakers for rate limits
- Fix ticker formatting

Step 1.3: Fix strategy execution in engine/core.py
- Remove early-exit when market_data appears empty
- Allow strategies to run with fallback logic
- Make indicator validation more lenient
```

---

## Issue 2: ML Drift Monitoring

### Problem Analysis
- ML model degrades over time without detection
- Threshold doesn't adapt to model degradation
- No automated retraining triggers

### Root Causes
1. No AUC tracking in production
2. No dynamic threshold adjustment based on model accuracy
3. No drift alerts

### Fix Plan
```
Step 2.1: Enhance ml/drift_monitor.py
- Track prediction accuracy over time
- Calculate rolling AUC
- Trigger retraining alerts

Step 2.2: Add ml/dynamic_threshold.py integration
- calculate_dynamic_threshold() already exists
- Ensure it's called in engine/core.py

Step 2.3: Add Redis-backed ML metrics
- Track ml:model:auc key
- Track ml:predictions:correct key
```

---

## Issue 3: Telegram Bot Issues

### Problem Analysis
- audit_recent import error in services/gemini_ml.py
- /signals command only filters "active" status
- Missing broker map integration

### Root Causes
1. Function alias `audit_recent = audit_recent_signals` references non-existent function
2. Status filter too narrow in commands.py
3. BROKER_MAP not defined

### Fix Plan
```
Step 3.1: Fix gemini_ml.py
- Define audit_recent_signals function
- Fix alias reference

Step 3.2: Fix commands.py /signals
- Expand status filter to: ['issued', 'active', 'open']
- Add outcome status display

Step 3.3: Add broker map to commands.py
- Define BROKER_MAP dictionary
- Add resolve_broker_prefix function
```

---

## Issue 4: Risk Management

### Problem Analysis
- No equity curve protection (drawdown limits)
- No max correlated exposure checks
- Position sizing not using Fractional Kelly

### Root Causes
1. Drawdown tracking not implemented
2. Portfolio exposure checks incomplete
3. Static position sizing

### Fix Plan
```
Step 4.1: Add equity curve protection in engine/core.py
- Track 24-hour rolling P&L
- Halt LIVE signals when drawdown > X%
- Switch to SHADOW mode

Step 4.2: Implement max correlated exposure
- Check existing positions before new signals
- Block correlated pairs (e.g., EURUSD when GBPUSD long)

Step 4.3: Add Fractional Kelly sizing
- Risk % = Win_Prob - ((1-Win_Prob) / RR_Ratio)
- Implement in engine/risk_sizer.py or engine/core.py
```

---

## Issue 5: Database Optimizations

### Problem Analysis
- Slow queries on signals table
- Missing indexes
- No query performance monitoring

### Root Causes
1. Large signals table without proper indexes
2. No composite indexes for common queries
3. N+1 query problems

### Fix Plan
```
Step 5.1: Add database indexes
- Index on (asset, timeframe, status, created_at)
- Index on (status, archived, expired)
- Index on (user_id, signal_id) for deliveries

Step 5.2: Optimize queries
- Use batch queries instead of per-signal
- Add query result caching

Step 5.3: Add performance monitoring
- Log slow queries
- Monitor connection pool usage
```

---

## Implementation Order

### Phase 1: Critical Signal Generation Fixes (Day 1-2)
1. Adjust thresholds in config.py
2. Fix data provider fallbacks
3. Fix strategy execution

### Phase 2: ML Improvements (Day 3-4)
4. Enhance drift monitoring
5. Integrate dynamic thresholds
6. Add ML prediction logging

### Phase 3: Telegram Bot Fixes (Day 5)
7. Fix audit_recent import
8. Fix /signals filtering
9. Add broker map

### Phase 4: Risk Management (Day 6-7)
10. Add equity curve protection
11. Implement correlation limits
12. Add Kelly sizing

### Phase 5: Database (Day 8)
13. Add indexes
14. Optimize queries
15. Add monitoring

---

## Files to Modify

### Critical Files
1. `config.py` - Threshold adjustments
2. `engine/core.py` - Multiple fixes
3. `data/fetcher.py` - Provider fallbacks
4. `data/providers.py` - Rate limiting
5. `ml/drift_monitor.py` - Enhancement
6. `ml/dynamic_threshold.py` - Integration

### Telegram Files
7. `services/gemini_ml.py` - Fix import
8. `signalrank_telegram/commands.py` - Fix filtering, add broker map

### Risk Files
9. `engine/risk_sizer.py` - Kelly sizing
10. `engine/correlation_filter.py` - Exposure limits
11. `engine/trade_tracker.py` - Drawdown tracking

### Database Files
12. `db/models.py` - Add indexes (via migration)
13. `db/repository.py` - Optimize queries

---

## Testing Plan

### Unit Tests
- Test threshold adjustments
- Test data provider fallbacks
- Test ML drift detection

### Integration Tests
- Test full signal pipeline
- Test Telegram commands
- Test risk limits

### Manual Testing
- Run engine in dry-run mode
- Check generated signals count
- Verify Telegram delivery

---

## Success Metrics

1. **Signal Generation**: generated_signals > 0 per cycle
2. **ML Filtering**: risk_passed > 0 when data available
3. **Storage**: stored > 0 signals per cycle
4. **Delivery**: users_dispatched > 0
5. **Performance**: cycle time < 60 seconds

---

## Dependencies

- PostgreSQL database
- Redis instance
- Telegram bot token
- Data provider API keys (Polygon, Yahoo, CryptoCompare)
- Gemini API key (for ML review)

---

## Risk Mitigation

1. **Rollback Plan**: Keep backup of original config values in environment variables
2. **Gradual Rollout**: Start with SHADOW mode, then enable LIVE
3. **Monitoring**: Add detailed logging for all gates
4. **Circuit Breakers**: Auto-disable features that cause issues

---

## Timeline

- **Week 1**: Signal generation fixes + ML improvements
- **Week 2**: Telegram bot fixes + Risk management
- **Week 3**: Database optimizations + Testing
- **Week 4**: Full integration + deployment

---

## Notes

This plan addresses all issues from TODO_FIX_ALL_ISSUES_REMAINING.md while following the core engineering directives:
- Unblock the event loop (heavy computation offloaded)
- Stateful idempotency (signals persisted, not spam)
- Failover & resiliency (waterfall fallback)
- Zero look-ahead bias (training/inference separation)
