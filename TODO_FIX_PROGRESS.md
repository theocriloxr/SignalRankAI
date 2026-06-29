# SignalRankAI Bug Fixes - Implementation Progress

## Priority 1: Critical Production Bugs

- [x] 1.1 Signal Deduplication - Fix fingerprint (remove timestamp fields, add Redis lock)
- [x] 1.2 Active Signal Protection - Add active_signal_exists() check
- [x] 1.3 Telegram Delivery Cooldown - Add per-user tier-based cooldown

## Priority 2: Buttons Not Working

- [ ] 2.1 Consolidate callback handlers in single router
- [ ] 2.2 Add logging for button presses

## Priority 3: Outcome Tracking

- [ ] 3.1 Unify outcome ownership to RealtimeOutcomeTracker
- [ ] 3.2 Add signal_state enum

## Priority 4: Freshness Bug

- [ ] 4.1 Fix signal.created_at vs candle.timestamp inconsistency

## Priority 5: Stale Signal Logic

- [ ] 5.1 Refactor stale_signal_validator.py

## Priority 6: Railway Stability

- [ ] 6.1 Add Redis health monitor
- [ ] 6.2 Add PostgreSQL health monitor
- [ ] 6.3 Add engine_health heartbeat table

## Priority 7: Database Indexes

- [ ] 7.1 Add indexes to Signals, Outcomes, Deliveries tables

## Priority 8: Signal Lifecycle

- [ ] 8.1 Implement signal statusUpdates (NEW → UPDATED → TP1 HIT → TP2 HIT → CLOSED)

## Priority 9: ML System

- [ ] 9.1 Add confidence calibration

## Priority 10: Advanced Features

- [ ] 10.1 Trade Journal
- [ ] 10.2 Portfolio Exposure Engine
- [ ] 10.3 Market Regime Detection
- [ ] 10.4 Institutional Scoring
