# SignalRankAI - Command & Help Update Plan

## Task Summary
1. Fix `/signals` command showing "no signals" even though signals were received
2. Update `/help` with all new commands based on tier
3. Ensure all commands in `/help` are working and registered

---

## Completed/Fixed Items

### ✅ 1. `/signals` Command Fix (signal_commands.py)
- The bug was in the query filter `SignalDelivery.sent_ok.is_(True)` which excluded signals that existed but weren't marked as successfully sent
- FIX: Removed the `sent_ok` filter in signal_commands.py to show ALL delivered signals regardless of delivery status
- Also added fallback to `list_unresolved_signals_for_user` if first query returns empty
- The fix is in place in signalrank_telegram/signal_commands.py (~line 200-250)

---

## Remaining Tasks

### 2. Update `/help` COMMAND_TIERS and COMMAND_HELP
Need to add missing commands to command_access.py:
- `liveprice_command` - FREE tier (already in bot.py)
- `portfolio_command` - PREMIUM tier
- `market_command` - FREE tier 
- `tiers_command` - FREE tier
- `setlot_command` - PREMIUM tier
- `setrisk_command` - VIP tier
- `setwebhook_command` - VIP tier
- `drawdown_command` - PREMIUM tier
- `mystats_command` - PREMIUM tier
- `referral_command` - PREMIUM tier
- `execution_command` - PREMIUM tier
- `connect_broker_conversation` - PREMIUM tier

### 3. Verify All Commands Registered in bot.py
Commands that should be handlers in bot.py:
- [x] start
- [x] status  
- [x] help
- [x] about
- [x] faq
- [x] disclaimer
- [x] support
- [x] performance
- [x] quality
- [x] gemini
- [x] gemini_review
- [x] gemini_analyze
- [x] gemini_audit
- [x] gemini_predict
- [x] pricing
- [x] upgrade
- [x] signals
- [x] proof
- [x] signal
- [x] outcome
- [x] invite
- [x] stats
- [x] history
- [x] simulate
- [x] risk
- [x] alerts
- [ ] liveprice (NEW - needs registration)
- [ ] portfolio (NEW - needs registration)
- [ ] market (NEW - needs registration)
- [ ] tiers (NEW - needs registration)
- [ ] elite
- [ ] early
- [ ] report
- [ ] policy
- [ ] refunds
- [ ] recap
- [ ] selfcheck
- [ ] ops_health
- [ ] myid
- [ ] account
- [ ] dashboard
- [ ] notify
- [ ] feedback
- [ ] analyze
- [ ] filter
- [ ] apikey
- [ ] language
- [ ] reports
- [ ] referral_leaderboard
- [ ] referral_rewards
- [ ] admin_top_assets
- [ ] admin_top_strategies
- [ ] admin_user_engagement
- [ ] assets
- [ ] unlock (owner)
- [ ] dev_pause (owner)
- [ ] dev_resume (owner)
- [ ] dev_force_signal (owner)
- [ ] dev_invalidate (owner)
- [ ] owner_users (owner)
- [ ] owner_revenue (owner)
- [ ] correct_signal (owner)
- [ ] provider_status (owner)
- [ ] qa_report (owner)
- [ ] broadcast (owner)
- [ ] version (owner)
- [ ] mt5_link / mt5 / mt5link
- [ ] mt5_status
- [ ] setlot
- [ ] setrisk
- [ ] setwebhook
- [ ] drawdown
- [ ] execution
- [ ] tiers
- [ ] mystats
- [ ] referral
- [ ] cancel
- [ ] leaderboard
- [ ] admin
- [ ] admin_dashboard
- [ ] admin_broadcast
- [ ] force_market_scan
- [ ] blast_terms

### 4. Command Handler Audit
Need to verify these commands have proper handlers in bot.py:
- liveprice_command (need to verify imports)
- portfolio_command (need to verify imports)
- market_command (need to verify imports)

---

## Execution Steps

### Step A: Update COMMAND_TIERS in command_access.py
Add missing commands to global dict:
```
"liveprice": "FREE",
"portfolio": "PREMIUM", 
"market": "FREE",
"tiers": "FREE",
"setlot": "PREMIUM",
"setrisk": "VIP",
"setwebhook": "VIP",
"drawdown": "PREMIUM",
"mystats": "PREMIUM",
"referral": "PREMIUM",
"execution": "PREMIUM",
```

### Step B: Update COMMAND_HELP sections
Add command descriptions to FREE, PREMIUM, VIP help sections

### Step C: Register any missing handlers in bot.py
Ensure all new commands have CommandHandler registration

---

## Status: IN PROGRESS
