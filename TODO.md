# SignalRankAI Implementation TODO

## Status: In Progress

### P0 - CRITICAL: Command System Fix
- [ ] 1. Fix unknown command handler shadowing in bot.py
  - The MessageHandler(filters.COMMAND) at ~line 4600 catches ALL commands before specific handlers
  - Need to remove/reorder this handler to be AFTER all specific CommandHandlers
- [ ] 2. Rebuild command registry to be source of truth
  - Verify all commands in COMMAND_TIERS have corresponding handlers
- [ ] 3. Verify /mode handler exists
  - Handler found in commands.py - OK
- [ ] 4. Verify /connect_broker not shadowed
  - Handler added via conversation - OK

### P1 - CRITICAL: Signal Lifecycle
- [ ] 1. Add signal family grouping (asset + signal thesis clustering)
- [ ] 2. Add multi-timeframe confirmation scoring
- [ ] 3. Add dedupe/fusion policy
- [ ] 4. Reduce repetitive signals (AVAXUSDT pattern)

### P2 - CRITICAL: Trade Tracking
- [ ] 1. Add market fingerprint for open-trade protection
- [ ] 2. Normalize fingerprint: asset + direction + entry_zone + stop_structure
- [ ] 3. Add idempotent trade opening

### P3 - CRITICAL: Outcome Tracking
- [ ] 1. Add outcome provider fallback routing
- [ ] 2. Add asset-class aware provider routing
- [ ] 3. Fix "No candles found" failure mode
- [ ] 4. Consolidate single writer authority

### P4 - IMPORTANT: Stale Signal Handling
- [ ] 1. Add asset-class aware staleness tolerances
- [ ] 2. Different tolerances: crypto < forex < stocks < indices < commodities
- [ ] 3. Respect timeframe and volatility regime

### P5 - IMPORTANT: Scoring & Filtering
- [ ] 1. Audit threshold calibration
- [ ] 2. Improve score explanation
- [ ] 3. Add rejection reason breakdown

### P6 - IMPORTANT: Asset Model
- [ ] 1. Add indices as first-class asset
- [ ] 2. Fix ticker parsing
- [ ] 3. Add provider mapping per asset class

### P7 - Tier-based Execution
- [ ] 1. Build execution policy engine
- [ ] 2. Add /mode command with tier-aware options
- [ ] 3. Map execution modes: signals_only, copy_trade, auto, paper

### P8 - Growth Features
- [ ] 1. Referral system v2 commands
- [ ] 2. AI coaching commands
- [ ] 3. Performance analytics

---

## Current Focus: P0 - Command System Fix

### Step 1: Fix the unknown command handler
The issue is in bot.py around line 4600:
```python
application.add_handler(MessageHandler(filters.COMMAND, _audit_handler("unknown_command", _handle_unknown_command)))
```

This catches ALL command-like messages before the specific CommandHandlers get a chance.

### Fix Approach:
1. Remove the generic MessageHandler(filters.COMMAND) fallback
2. Or move it to be LAST in the handler chain
3. Verify all expected commands have proper handlers

### Commands to Verify:
- /connect_broker - Conversation handler
- /mode - CommandHandler
- /execution - CommandHandler  
- /setlot - CommandHandler
- /setrisk - CommandHandler
- /referral - CommandHandler
- /leaderboard - CommandHandler
