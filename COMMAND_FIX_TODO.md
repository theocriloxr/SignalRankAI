# SignalRankAI Command Fix Implementation Plan

## Executive Summary

Based on comprehensive codebase analysis, the following critical issues have been identified:

1. **Root Cause of "/signals says no signals"**: Signal query filters by `sent_ok=True` but signals exist even when delivery failed
2. **Command Audit Missing**: No startup verification that all /help commands are registered
3. **Missing /diag command**: No health verification command
4. **Delivery Telemetry**: No visibility into where signals die in the pipeline
5. **AUDUSD Pricing Bug**: No explicit sanity check for AUDUSD (0.60-0.85 range)
6. **Duplicate Telegram Stacks**: Found legacy stub in `telegram/` (already disabled)

---

## Implementation Plan

### Phase 1: Fix Signal Status Query (CRITICAL)

**Problem**: `/signals` command shows "No active unresolved signals" while trades exist

**Root Cause**: 
- `list_unresolved_signals_for_user()` filters by `sent_ok.is_(True)`
- Signals can exist without being marked as successfully delivered

**Solution**:
1. Create ACTIVE_SIGNAL_STATUSES constant
2. Update signal_commands.py to query ALL delivered signals (not just sent_ok=True)
3. Include resolved/expired signals in history

**Files to Edit**:
- `signalrank_telegram/signal_commands.py`
- `db/pg_features.py` (for `list_unresolved_signals_for_user`)

### Phase 2: Add Startup Command Audit

**Problem**: No verification that commands in /help are actually registered

**Solution**:
1. Add logging at bot startup that compares:
   - EXPECTED_COMMANDS (from /help text)
   - REGISTERED_COMMANDS (from bot handlers)
   - IMPLEMENTED_COMMANDS (functions with working DB queries)

2. Log missing handlers with ERROR level

**Files to Edit**:
- `signalrank_telegram/bot.py` (in run_bot() function)

### Phase 3: Add /diag Command

**Problem**: No admin diagnostic command for health verification

**Solution**:
1. Create new diagnostic command that checks:
   - Database connectivity
   - Redis connectivity
   - Provider health status
   - Recent signal generation count
   - Command registration status
   - Delivery pipeline status

**Files to Create/Edit**:
- `signalrank_telegram/commands.py` (add diag_command)
- `signalrank_telegram/bot.py` (register /diag handler)

### Phase 4: Add Delivery-Stage Telemetry

**Problem**: "stored=5 but users received nothing" - no visibility

**Solution**:
1. Add delivery_stage field to signal tracking:
   - GENERATED → STORED → QUEUED → TELEGRAM_SENT → DELIVERED

2. Log each stage transition

**Files to Edit**:
- `db/pg_features.py`
- `engine/core.py`
- `signalrank_telegram/tier_delivery.py`

### Phase 5: Fix AUDUSD Price Sanity

**Problem**: 4430% drift (0.01570 vs 0.71124) - provider returns inverse rate

**Solution**:
1. Add explicit AUDUSD sanity check in validate_price_sanity()
2. Check: AUDUSD should be in 0.60-0.85 range
3. Reject corrupted prices before they corrupt outcome tracking

**Files to Edit**:
- `data/fetcher.py` (update validate_price_sanity)

### Phase 6: Add Threshold Persistence

**Problem**: Dynamic thresholds recalculated every cycle, no persistence

**Solution**:
1. Save thresholds to Redis or DB
2. Load on startup
3. Only recalculate when stale

**Files to Edit**:
- `core/redis_state.py`
- `engine/core.py`

---

## Command Categories (85 total)

### Core Commands (Always Available)
- /start, /help, /pricing, /upgrade, /status, /signals, /signal, /performance, /invite, /support

### Premium Commands (Tier-gated)
- /stats, /history, /simulate, /risk, /alerts, /quality
- /portfolio, /market, /assets, /liveprice, /apikey, /language
- /account, /dashboard, /notify, /feedback, /analyze, /filter

### VIP Commands (Tier-gated)
- /elite, /early, /report, /setrisk

### Admin/Owner Commands (Silent)
- /unlock, /dev_pause, /dev_resume, /dev_force_signal, /dev_invalidate
- /owner_users, /owner_revenue, /provider_status, /correct_signal
- /admin, /admin_dashboard, /admin_broadcast, /force_market_scan
- /gemini, /gemini_review, /gemini_analyze, /gemini_predict, /gemini_audit
- /referral, /referral_leaderboard, /referral_rewards
- /selfcheck, /ops_health, /myid

### MT5 Commands
- /mt5, /mt5_link, /mt5_status, /setlot, /setwebhook
- /drawdown, /execution, /tiers, /mystats, /cancel

---

## High-Risk Commands (Need Audit First)

These are the commands most likely to be broken:

1. **/portfolio** - May have missing DB query
2. **/quality** - May rely on ML subsystem
3. **/reports** / **/report** - Analytics commands
4. **/outcome** - May have wrong status mapping
5. **/provider_status** - May not be wired correctly
6. **/assets** - Asset discovery
7. **/market** - Market data
8. **/gemini_review** / **/gemini_predict** - Gemini commands
9. **/referral_rewards** / **/referral_leaderboard** - Referral system
10. **/alerts** / **/notify** - Notification system

---

## Status: Ready for Implementation

The implementation plan is confirmed. Ready to proceed with fixes.

## Next Steps

1. Implement Phase 1 (Signal Status Fix) - CRITICAL
2. Add /diag command
3. Add startup audit
4. Test all high-risk commands
5. Deploy to Railway
6. Verify /signals shows signals correctly
