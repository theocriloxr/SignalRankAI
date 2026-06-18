# Command Fix Plan

## Issues Identified:

1. **Multiple commands not registered in COMMAND_TIERS** - Commands exist but missing from access dict
2. **Inconsistent tier assignments** - Some commands have wrong tier mappings
3. **Missing help menu entries** - Some registered commands not showing in help display

## Plan:

### 1. Update COMMAND_TIERS with missing commands
- Add ALL commands from commands.py that are missing from COMMAND_TIERS
- Fix tier assignments where inconsistent

### 2. Update COMMAND_HELP for new/changed commands  
- Ensure all tier help sections include registered commands
- Fix any descriptions or footer text

### 3. Verify /signals command is working
- The critical fix was already applied in pg_features.py
- Verify list_unresolved_signals_for_user works correctly

### 4. Test all commands work properly
- Test /help shows all commands by tier
- Test tier-gated commands properly blocked/allowed
- Test /signals returns signals correctly

## Commands to add to COMMAND_TIERS:
- simulate (VIP)
- drawdown (PREMIUM)
- tiers (FREE) - should show tier comparison
- all MT5 variants (mt5, mt5link, etc.)  
- setrisk (VIP or PREMIUM)
- confirm_sender (check if exists)

## Status:
- [ ] Audit all command functions in commands.py against COMMAND_TIERS
- [ ] Add missing commands to COMMAND_TIERS
- [ ] Update COMMAND_HELP if needed
- [ ] Test /help displays correctly for each tier
- [ ] Test /signals returns signals
- [ ] Verify no breaking changes
