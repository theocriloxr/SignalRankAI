# SignalRankAI Table Activation Fix Plan - IMPLEMENTATION

## Status Summary

### ✅ ALREADY WORKING
- signal_deliveries - signal_distribution.py record_delivery_attempt() ✅ commits
- subscriptions - payment_handler.py activates on payment
- outcomes - realtime_outcome_tracker.py _persist_outcome() ✅ commits
- outcome_notifications - pg_features.py queue_outcome_notifications_for_outcome()
- payment_events - pg_features.py record_payment_event()
- processed_webhook_events - web/app.py paystack_webhook()
- ml_past_training_data - railway_main.py _archive_ml_history_job()
- vip_waitlist - web/app.py _check_waitlist_capacity_job()
- strategy_stats - touched when signals created

### ❌ NEEDS IMPLEMENTATION (Critical First)
1. **free_signal_queue** - queuing exists but NO distribution job
2. **api_tokens** - model exists but NO /api_key command
3. **user_webhooks** - model exists but NO /webhook set command
4. **mt5_credentials** - model exists but NO /connect_broker command
5. **mt5_executions** - model exists but NO execution logging
6. **trades** - model exists but NO trade recording
7. **managed_assets** - model exists but NO startup seeding
8. **economic_events** - model exists but NO scraper job
9. **proxy_nodes** - model exists but NO proxy management
10. **asset_live_metrics** - model exists but NO live updates
11. **strategy_live_metrics** - model exists but NO live updates
12. **rate_limit_tokens** - model exists but NO rate limiting
13. **signal_corrections** - model exists but NO correction tracking
14. **market_candles** - WARNING: Should NOT store in Postgres

---

## IMPLEMENTATION: Step 1 - CRITICAL

### 1.1 Add free_signal_queue Distribution Job
**File**: signalrank_telegram/signal_distribution.py

This is the CRITICAL missing piece. The table has data queued but NO job distributes signals TO free users.

Add this function to signal_distribution.py:

```python
async def distribute_random_signals_to_free_users_job() -> None:
    """
    APScheduler job: distribute signals to FREE users.
    Runs every minute, picks random signals, distributes to free tier.
    """
    # Implementation needed in signal_distribution.py
```

Then register in railway_main.py _build_scheduler() or signalrank_telegram/bot.py scheduler.

### 1.2 Add User Commands (for mt5_credentials, api_tokens, user_webhooks)
**Files**: signalrank_telegram/commands.py, user_commands.py

Add:
- /api_key → generate API token for user
- /webhook <url> → set user webhook URL
- /connect_broker → link MT5 account

### 1.3 Add Managed Assets Seeding
**File**: db/auto_ops.py or startup script

Add startup job to seed managed_assets with top trading pairs.

---

## CURRENT IMPLEMENTATION STATUS

### ✅ IN PROGRESS
- [ ] free_signal_queue distribution job (CRITICAL)
- [ ] managed_assets seed job
- [ ] economic_events scrape job
- [ ] strategy_stats aggregation job
- [ ] /api_key command
- [ ] /webhook command
- [ ] /connect_broker command
