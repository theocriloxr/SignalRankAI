#!/usr/bin/env python3
"""
SignalRankAI Implementation Fix Plan - All Priorities

This document tracks all bug fixes from the 10 priorities.
Priority 1 fixes are ALREADY DONE in the codebase.
Priorities 2-10 need implementation.

STATUS:
- [x] = Complete
- [ ] = Not started
- [~] = In progress
"""

# ============================================================================
# PRIORITY 1: CRITICAL PRODUCTION BUGS (ALREADY DONE)
# ============================================================================

PRIORITY_1_DONE = """
1.1 Signal Deduplication - FIX FINGERPRINT
   Status: [x] DONE
   Files: db/pg_features.py, engine/core.py
   Changes:
   - Removed candle_timestamp from compute_signal_fingerprint()
   - Fingerprint: asset|timeframe|direction|entry|stop_loss|take_profit|strategy_group|strategy_name
   - Added timeframe-specific cooldown in engine/signal_deduplicator.py

1.2 Active Signal Protection
   Status: [x] DONE
   Files: engine/core.py, db/pg_features.py
   Changes:
   - Added active_trade check in get_or_create_signal_impl()
   - Query: check if asset has active trade within cooldown window
   - Raise SignalDedupBlocked("active_trade") if active trade exists

1.3 Telegram Delivery Cooldown
   Status: [x] DONE
   Files: signalrank_telegram/bot.py
   Changes:
   - Added _is_asset_delivery_locked() function
   - Uses asset repeat lock (ASSET_REPEAT_LOCK_HOURS = 12h default)
   - Checks delivered signals in cooldown window
"""

# ============================================================================
# PRIORITY 2: BUTTONS NOT WORKING
# ============================================================================

PRIORITY_2_TODO = """
2.1 Consolidate Callback Handlers - IN PROGRESS
   Status: [~] PARTIALLY DONE
   Files: signalrank_telegram/bot.py, signalrank_telegram/callback_handlers.py
   
   Current State:
   - callback_handlers.py has create_global_callback_handler() - GOOD
   - bot.py has inline handlers (_signal_reaction_callback, _signal_monitor_callback, etc.)
   
   The Issue:
   - Multiple callback handlers exist causing confusion
   - Button pressed → Handler A → Handler B → Nothing
   
   Fix Needed:
   - Remove inline handlers from bot.py, use callback_handlers.py exclusively
   - Add comprehensive logging for all button presses
   
   Action: Verify callback_handlers.py is working correctly

2.2 Add Button Press Logging
   Status: [ ]
   Files: signalrank_telegram/callback_handlers.py
   
   Fix:
   - Add logger.info(f"Button pressed {callback.data}") to _global_callback_handler()
"""

# ============================================================================
# PRIORITY 3: OUTCOME TRACKING
# ============================================================================

PRIORITY_3_TODO = """
3.1 Unify Outcome Ownership
   Status: [ ]
   Files: engine/realtime_outcome_tracker.py, engine/shadow_outcome_worker.py, engine/core.py
   
   Current Issue:
   - tracker A (realtime_outcome_tracker)
   - tracker B (shadow_outcome_worker)
   - engine (core.py)
   - All touch outcome state = race conditions
   
   Fix:
   - RealtimeOutcomeTracker = sole owner
   - Everything else = read-only
   
   Action: Check realtime_outcome_tracker.py and verify ownership

3.2 Add signal_state Enum
   Status: [ ]
   Files: db/models.py
   
   Fix:
   - Add status enum to Outcome or Signal table
   - Values: ACTIVE, TP1_HIT, TP2_HIT, TP3_HIT, SL_HIT, EXPIRED, CANCELLED
"""

# ============================================================================
# PRIORITY 4: FRESHNESS BUG
# ============================================================================

PRIORITY_4_TODO = """
4.1 Fix signal.created_at vs candle.timestamp
   Status: [ ]
   Files: engine/signal_formatter.py, engine/freshness.py
   
   Issue:
   - Messages show "Freshness: Aging" but "Age: 0m"
   - Impossible state - one uses created_at, another uses candle.timestamp
   
   Fix:
   - Use ONE source consistently across the codebase
   - Recommend: signal.created_at (DB timestamp)
"""

# ============================================================================
# PRIORITY 5: STALE SIGNAL LOGIC
# ============================================================================

PRIORITY_5_TODO = """
5.1 Refactor stale_signal_validator.py
   Status: [ ]
   Files: engine/stale_signal_validator.py
   
   Issue:
   - Logs show "Signal INVALIDATED" then "ACCEPTED" for same asset
   - Contradictory logic
   
   Fix:
   - Refactor validate() to return SINGLE result:
     - VALID
     - INVALID  
     - ENTRY_ZONE_OVERRIDE
"""

# ============================================================================
# PRIORITY 6: RAILWAY STABILITY
# ============================================================================

PRIORITY_6_TODO = """
6.1 Redis Health Monitor
   Status: [ ]
   Files: core/redis_state.py, railway_main.py
   
   Fix:
   - PING Redis every minute
   - Log health status

6.2 PostgreSQL Health Monitor  
   Status: [ ]
   Files: db/session.py
   
   Fix:
   - Run SELECT 1 every minute
   - Log health status

6.3 Engine Heartbeat Table
   Status: [ ]
   Files: db/models.py
   
   Fix:
   - Add engine_health table:
     - last_cycle
     - last_signal
     - last_outcome
     - last_news_sync
"""

# ============================================================================
# PRIORITY 7: DATABASE INDEXES
# ============================================================================

PRIORITY_7_TODO = """
7.1 Add Database Indexes
   Status: [ ]
   Files: db/models.py, alembic/migrations/
   
   Signals table indexes:
   - asset
   - status
   - created_at
   - signal_id
   
   Outcomes table indexes:
   - signal_id
   - status
   - closed_at
   
   Deliveries table indexes:
   - user_id
   - signal_id
   - asset
"""

# ============================================================================
# PRIORITY 8: SIGNAL LIFECYCLE
# ============================================================================

PRIORITY_8_TODO = """
8.1 Implement Signal Status Updates
   Status: [ ]
   Files: engine/core.py, signalrank_telegram/bot.py
   
   Current:
   - NEW SIGNAL
   - NEW SIGNAL
   - NEW SIGNAL (repeated)
   
   Fix:
   - Message thread with status updates:
     NEW SIGNAL → UPDATED → TP1 HIT → TP2 HIT → CLOSED
   
   This requires storing message_thread_id per user/signal
"""

# ============================================================================
# PRIORITY 9: ML SYSTEM
# ============================================================================

PRIORITY_9_TODO = """
9.1 Add Confidence Calibration
   Status: [ ]
   Files: ml/, engine/core.py
   
   Fix:
   - Store predicted_probability and actual_result
   - Recalibrate monthly
   - Improves accuracy over time
   
   Add to MLRejectedSignal or new MLCalibration table:
   - predicted_probability
   - actual_result (TP/SL)
   - timestamp
"""

# ============================================================================
# PRIORITY 10: ADVANCED FEATURES
# ============================================================================

PRIORITY_10_TODO = """
10.1 Trade Journal (New Feature)
   Status: [ ]
   Per user tracking:
   - Win rate
   - Profit factor
   - Average RR
   - Monthly ROI

10.2 Portfolio Exposure Engine (Enhancement)
   Status: [ ]
   Prevent correlated trades at once:
   - SOL BUY + ETH BUY = blocked
   - Both highly correlated

10.3 Market Regime Detection (Enhancement)
   Status: [ ]
   Detect modes:
   - TRENDING
   - RANGING
   - VOLATILE
   - NEWS
   
   Strategies adapt automatically to regime

10.4 Institutional Scoring (Enhancement)
   Status: [ ]
   Add to signal scoring:
   - Liquidity sweep
   - Fair Value Gap
   - Market Structure Shift
   - Order Block Strength
   - Volume Imbalance
"""

# ============================================================================
# QUICK WINS - THE 5 BIGGEST FIXES TO IMPLEMENT FIRST
# ============================================================================

QUICK_WINS = """
These 5 changes alone would eliminate most production issues:

1. Fix signal fingerprint (DONE ✓)
   - db/pg_features.py - removed timestamp from fingerprint
   
2. Add active-signal lock (DONE ✓)
   - engine/core.py - checks active_trades before creating signal
   
3. Add per-user delivery cooldown (DONE ✓)
   - signalrank_telegram/bot.py - _is_asset_delivery_locked()
   
4. Unify outcome ownership
   - Still needed: Make RealtimeOutcomeTracker sole owner

5. Unify Telegram callbacks
   - Still needed: Remove duplicate handlers, consolidate logging
"""

if __name__ == "__main__":
    print(__doc__)
    print("\n" + "="*60)
    print("IMPLEMENTATION STATUS")
    print("="*60)
    print(PRIORITY_1_DONE)
    print("\n--- TODO ---")
    print(PRIORITY_2_TODO)
    print(PRIORITY_3_TODO)
    print(PRIORITY_4_TODO)
    print(PRIORITY_5_TODO)
    print(PRIORITY_6_TODO)
    print(PRIORITY_7_TODO)
    print(PRIORITY_8_TODO)
    print(PRIORITY_9_TODO)
    print(PRIORITY_10_TODO)
    print("\n" + "="*60)
    print("QUICK WINS - START HERE")
    print("="*60)
    print(QUICK_WINS)
