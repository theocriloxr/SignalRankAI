"""
SignalRankAI All Bugs Implementation TODO
=======================================

Priorities from task analysis. Implement in order of criticality.

Priority 1 (Critical Production Bugs)
===================================
- [ ] 1.1 Signal Deduplication Fix
      - [x] Remove candle_timestamp/generated_at/created_at from fingerprint
      - [ ] Add Redis lock: signal_lock:SOLUSDT:BUY:4H with 4h TTL
      - [ ] Add PostgreSQL uniqueness constraint
- [ ] 1.2 Active Signal Protection  
      - [ ] Add active_signal_exists() check before signal creation
      - [ ] Check asset/direction/timeframe/status=active
- [ ] 1.3 Telegram Delivery Cooldown
      - [ ] Add Redis key: delivery:user_id:SOLUSDT:BUY
      - [ ] TTL by tier: VIP=4h, Premium=6h, Free=12h

Priority 2: Buttons Not Working  
=============================
- [ ] 2.1 Unify callback handlers
- [ ] 2.2 Single callback router with logging

Priority 3: Outcome Tracking
=========================
- [ ] 3.1 Make RealtimeOutcomeTracker sole owner
- [ ] 3.2 Add signal_state enum

Priority 4: Freshness Bug
========================
- [ ] 4.1 Use single source for timestamp

Priority 5: Stale Signal Logic
============================
- [ ] 5.1 Refactor validate() to return VALID/INVALID/ENTRY_ZONE_OVERRIDE

Priority 6: Railway Stability
===========================
- [ ] 6.1 Redis health monitor (PING every minute)
- [ ] 6.2 PostgreSQL health monitor
- [ ] 6.3 Engine heartbeat table

Priority 7: Database Indexes
===========================
- [ ] 7.1 Add indexes for Signals, Outcomes, Deliveries tables

Priority 8: Signal Lifecycle
=========================
- [ ] 8.1 Single message thread with updates (NEW → UPDATED → TP1 HIT → etc.)

Priority 9: ML System
==================
- [ ] 9.1 Confidence calibration (store predicted_probability vs actual_result)

Priority 10: Features
====================
- [ ] 10.1 Trade Journal
- [ ] 10.2 Portfolio Exposure Engine  
- [ ] 10.3 Market Regime Detection
- [ ] 10.4 Institutional Scoring
"""
