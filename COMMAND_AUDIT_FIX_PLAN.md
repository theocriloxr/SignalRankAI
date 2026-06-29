# Command Audit & Signal Status Fix Implementation Plan

## Issues Identified

1. **Signal Status Mismatch** - `/signals` says "No active unresolved signals" while trades exist
2. **Missing Command Audit** - No startup verification of registered handlers
3. **Missing /diag command** - No health verification command
4. **Missing Delivery Telemetry** - No visibility into signal delivery stages
5. **AUDUSD Pricing Bug** - 4430% drift (0.01570 vs 0.71124)
6. **No Threshold Persistence** - Dynamic thresholds recalculated every cycle

## Implementation Plan

### Phase 1: Signal Status Fix (CRITICAL)

**File: db/pg_features.py**
- Create ACTIVE_SIGNAL_STATUSES = {"issued", "open", "active", "pending"}
- Update list_active_signals() to use this set
- Update list_unresolved_signals_for_user() to not filter by sent_ok

**File: signalrank_telegram/signal_commands.py**
- Fix signals_command to show ALL delivered signals
- Include unresolved, resolved, invalidated signals

### Phase 2: Startup Command Audit

**File: signalrank_telegram/bot.py**
- Add expected commands list (COMMAND_TIERS from command_access.py)
- Log registered vs expected at startup
- Log missing handlers with ERROR level

### Phase 3: /diag Command

**File: signalrank_telegram/commands.py**
- Add diag_command showing:
  - Commands registered count
  - Database connectivity
  - Redis connectivity
  - Last signal generated
  - Delivery queue status
  - Tier distribution status

### Phase 4: Delivery-Stage Telemetry

**File: db/models.py**
- Add delivery_stage column to SignalDelivery

**File: signalrank_telegram/bot.py**
- Track: GENERATED → STORED → QUEUED → TIER_PASSED → TELEGRAM_SENT → DELIVERED
- Log each stage

### Phase 5: Multi-Source Price Sanity Check

**File: data/fetcher.py**
- Create validate_price_sanity() that:
  - Fetches from multiple providers (Yahoo, Polygon, TwelveData)
  - Computes median price
  - Detects outliers using standard deviation
  - Returns confidence score

**File: engine/price_validator.py**
- Integrate multi-source validation
- Add price_source_track column
- Reject prices with low confidence

### Phase 6: Threshold Persistence

**File: core/redis_state.py**
- Add threshold persistence keys
- Load thresholds at startup
- Save thresholds on update
- Add TTL for automatic refresh

## Commands to Verify

High-risk commands needing audit:
- /portfolio - No DB query found
- /quality - Missing HELP entry
- /reports - Handler registered but returns error
- /outcome - Query returns wrong data
- /provider_status - Legacy stub
- /assets - Discovery-first approach
- /market - Partial implementation
- /gemini_review - Multiple code paths
- /referral_rewards - Tier routing issue

## Files to Modify

1. db/pg_features.py - Signal status fix
2. signalrank_telegram/signal_commands.py - /signals command fix
3. signalrank_telegram/bot.py - Command audit + /diag
4. signalrank_telegram/commands.py - Add /diag command
5. data/fetcher.py - Multi-source price validation
6. engine/price_validator.py - Integrate validation
7. core/redis_state.py - Threshold persistence
8. db/models.py - Add delivery_stage
