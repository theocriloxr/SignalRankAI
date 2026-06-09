# TODO: Institutional Grade SignalRankAI Implementation

## Status: IN PROGRESS

## Overview
This TODO tracks the implementation of the institutional grade architecture as specified in the task. The goal is to move from a monolithic script to an Event-Driven Architecture.

## Components Implemented

### ✅ 1. Event Bus (Nervous System)
- [x] `core/event_types.py` - Event type constants
- [x] `core/event_bus.py` - Redis-backed event bus with pub/sub

### ✅ 2. Paper Trading Ledger (Per-User)
- [x] `core/paper_ledger.py` - Virtual accounts and positions

### ✅ 3. Dedicated Broadcaster Service
- [x] `services/broadcaster.py` - Parallel delivery with asyncio.gather

### ✅ 4. Provider Health Monitoring
- [x] `services/provider_registry.py` - Auto-failover for data providers

### ✅ 5. Dead Letter Queue
- [x] `services/dead_letter_queue.py` - Failed delivery handling

### ✅ 6. ML Feedback Loop
- [x] `ml/feedback_loop.py` - Market context collection and retraining

### ✅ 7. Dynamic Sizing
- [x] `services/dynamic_sizing.py` - Kelly Criterion + ML conviction sizing

### ✅ 8. Database Schema
- [x] `migrations/institutional_paper_trading.sql` - SQL migration

## Components Pending

### 9. Integrate Event Bus with Engine
- [ ] Modify `engine/core.py` to publish SIGNAL_READY
- [ ] Use `redis_global_stats.py` for stats (already exists)

### 10. Integrate Broadcaster with Telegram Bot
- [ ] Update signal distribution to use event bus
- [ ] Add parallel delivery to `signalrank_telegram/`

### 11. Outcome Tracker Enhancement
- [ ] Update `engine/shadow_outcome_worker.py` to update paper positions
- [ ] Auto-close positions when TP/SL hit

### 12. Gemini Validator Integration
- [ ] Add semantic filter using Gemini before signal delivery
- [ ] Block signals during high-impact news

## Implementation Steps

### Step 1: Database Migration
```bash
# Run the SQL migration
psql $DATABASE_URL -f migrations/institutional_paper_trading.sql
```

### Step 2: Update Engine to Publish Events
- Modify `engine/core.py` to call `publish_signal_ready(signal)`
- Use `global_stats.increment_scanned()` for pulse

### Step 3: Update Bot to Use Event Bus
- Subscribe to `SIGNAL_READY` events
- Use parallel delivery

### Step 4: Deploy Worker Services
- Start broadcaster service on Railway
- Start outcome tracker worker

### Step 5: Monitor and Tune
- Check Pulse reports for non-zero stats
- Review DLQ for failed deliveries

## Testing Checklist
- [ ] Test paper trade execution
- [ ] Test parallel signal delivery
- [ ] Test provider failover
- [ ] Test DLQ retry
- [ ] Test ML retraining trigger
- [ ] Test dynamic position sizing

## Files Created
- `core/event_types.py` - Event type constants
- `core/event_bus.py` - Redis-backed event bus
- `core/paper_ledger.py` - Virtual accounts and positions
- `services/broadcaster.py` - Parallel delivery service
- `services/provider_registry.py` - Provider health monitoring
- `services/dead_letter_queue.py` - Dead letter queue
- `services/dynamic_sizing.py` - Kelly criterion position sizing
- `ml/feedback_loop.py` - ML feedback loop
- `migrations/institutional_paper_trading.sql` - Database schema
- `TODO_INSTITUTIONAL_GRADE.md` - This file

## Configuration Needed
- `REDIS_URL` - For event bus and pub/sub
- `BROADCASTER_MAX_PARALLEL=50` - Parallel deliveries
- `PROVIDER_COOLDOWN_SECONDS=60` - Provider cooldown
- `ML_RETRAIN_INTERVAL_HOURS=168` - Weekly retraining

## Key Features Implemented

1. **Event-Driven Architecture**: Signals are published to Redis for instant delivery
2. **Parallel Delivery**: Using asyncio.gather for all users simultaneously
3. **Provider Auto-failover**: Switch providers on 429 errors
4. **DLQ**: Failed deliveries retry with exponential backoff
5. **Per-User Paper Trading**: Virtual accounts with position tracking
6. **Kelly Sizing**: ML probability-based position sizing
