# SignalRankAI Implementation TODO

## Progress Tracker

- [ ] Phase 1: Fix Score Collapse (CRITICAL)
- [ ] Phase 2: Fix risk_passed=0 (CRITICAL)
- [ ] Phase 3: Enforce Market Hours (HIGH)
- [ ] Phase 4: Signal Lifecycle (HIGH)
- [ ] Phase 5: Threshold Drift Protection (MEDIUM)
- [ ] Phase 6: Backtesting and Walk-Forward (MEDIUM)
- [ ] Phase 7: News and Macro-Event Gating (MEDIUM)
- [ ] Phase 8: Portfolio-Level Risk Control (MEDIUM)
- [ ] Phase 9: Data Ingestion Resilience (MEDIUM)
- [ ] Phase 10: New Features (LOW)
- [ ] Phase 11: Tests (CRITICAL)

---

## Phase 1: Score Collapse Fix
- [ ] Add soft cap in engine/scoring.py
- [ ] Add score_components tracking
- [ ] Add raw_score and display_score fields

## Phase 2: Risk Passed Fix
- [ ] Add best_target_for_direction helper
- [ ] Add RR rejection tracking
- [ ] Add risk stats logging

## Phase 3: Market Hours
- [ ] Add is_market_open call in engine/core.py

## Phase 4: Signal Lifecycle
- [ ] Add status fields to signal orchestrator

## Phase 5: Threshold Drift
- [ ] Add minimum sample check
- [ ] Add hysteresis band
- [ ] Add rollback logic

## Phase 6: Backtesting
- [ ] Create ml/walk_forward.py
- [ ] Create engine/backtest_runner.py

## Phase 7: News Gating
- [ ] Wire news_filter into core.py

## Phase 8: Portfolio Risk
- [ ] Create portfolio_risk.py

## Phase 9: Data Resilience
- [ ] Add fallback to fetcher.py

## Phase 11: Tests
- [ ] test_score_distribution.py
- [ ] test_rr_best_target.py
- [ ] test_market_hours_gate.py
- [ ] test_signal_dedup.py
- [ ] test_threshold_rollback.py
