# TODO: Fix Commands and /signals Issues

## Phase 1: Understand the issue with /signals showing no signals
- [ ] 1.1 Check db/pg_features.py for list_signals_sent_today function
- [ ] 1.2 Check db/pg_features.py for list_unresolved_signals_for_user function
- [ ] 1.3 Test the signals query to see what's being returned

## Phase 2: Ensure all commands are registered
- [ ] 2.1 Review command_access.py COMMAND_TIERS for completeness
- [ ] 2.2 Verify all commands in bot.py are in COMMAND_TIERS
- [ ] 2.3 Add any missing commands to COMMAND_TIERS

## Phase 3: Update /help with all new commands
- [ ] 3.1 Update COMMAND_HELP for FREE tier
- [ ] 3.2 Update COMMAND_HELP for PREMIUM tier  
- [ ] 3.3 Update COMMAND_HELP for VIP tier
- [ ] 3.4 Update COMMAND_HELP for OWNER tier

## Phase 4: Test and verify
- [ ] 4.1 Test /help command shows all commands
- [ ] 4.2 Test /signals returns signals
- [ ] 4.3 Test tier-gated commands work correctly
