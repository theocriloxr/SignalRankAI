# TODO: Fix All Issues Implementation Plan

## Phase 1: Critical ML & Database Fixes
- [ ] 1. Fix audit_recent Import Error (signalrank_telegram/commands.py) - Already has function
- [ ] 2. Fix Max Score 100.0 (engine/core.py) - Fix >= operator
- [ ] 3. Fix /signals Command Returning Empty (signalrank_telegram/commands.py) - Expand statuses
- [ ] 4. Fix PostgreSQL "Too Many Clients" (db/session.py) - Check current settings
- [ ] 5. Fix No Timeframe Data (Rate Limits) (engine/core.py) - Add semaphore waterfall

## Phase 2: Core ML Stability
- [ ] 6. Fix Dynamic Threshold (ml/dynamic_threshold.py) - Return adjusted value
- [ ] 7. Create Broker Map & Market Hours Support (utils/market_hours.py)
- [ ] 8. Add ML scale_pos_weight (ml/train_model.py)
- [ ] 9. Add EMA Smoothing to Dynamic Threshold

## Phase 3: Advanced Features
- [ ] 10. Add Trade Correlation Blocker
- [ ] 11. Add Redis Market Data Caching
- [ ] 12. Add Graceful Shutdown

## Status: Ready to implement
