# SignalRankAI Implementation Roadmap

## Phase 1: Stability & Signal Flow (FIXES)
Status: ✅ COMPLETED - Most fixes already applied in codebase

### ✅ ALREADY APPLIED (Code-level fixes):
1. **Engine Scoring Fix** (`engine/scoring.py`):
   - Soft-cap divisor: 75.0 → 50.0 
   - CONFIDENCE_MIN: 0.35 → 0.20
   - MIN_RR: 1.5 (restored from 1.0)

2. **DB Pool Settings** (`config.py`):
   - DB_POOL_SIZE=8
   - DB_MAX_OVERFLOW=3
   - DB_SYNC_POOL_SIZE=3
   - DB_SYNC_MAX_OVERFLOW=2
   - YFINANCE_CACHE_TTL=60

3. **Tier Thresholds** (`core/tier_constants.py`):
   - FREE: 75.0 (lowered from 80.0)
   - PREMIUM: 73.0 (lowered from 80.0)
   - VIP: 73.0 (lowered from 80.0)

4. **ML Threshold** (`config.py`):
   - ML_PROB_THRESHOLD=0.15 (lowered from 0.25)
   - PREMIUM_SCORE_THRESHOLD=25.0 (lowered from 35.0)

### ✅ ALREADY CONFIGURED (Environment variables to set):
Add to Railway .env:
```
DB_POOL_SIZE=8
DB_MAX_OVERFLOW=3
DB_SYNC_POOL_SIZE=3
DB_SYNC_MAX_OVERFLOW=2
PREMIUM_SCORE_THRESHOLD=0
PREMIUM_SCORE_THRESHOLD_FORCE=1
YFINANCE_CACHE_TTL=60
```

---

## Phase 2: MT5 Automated Trading Integration
Status: Not Started | Priority: High

### Tasks:
1. **Create mt5_bridge.py service**
   - Connect to MetaTrader 5 via `MetaTrader5` Python library
   - Implement `signal → order_send()` conversion
   - Support multiple MT5 accounts per user

2. **Database Schema Updates**
   - Add `mt5_accounts` table
   - Track linked accounts per user

3. **Signal Delivery Enhancement**
   - Route signals to MT5 for automated execution
   - Return trade sync to paper ledger

### Files to create:
- `services/mt5_bridge.py` - Main MT5 integration
- `db/mt5_models.py` - Account tracking models

---

## Phase 3: Payment System Hardening (Paystack)
Status: Not Started | Priority: Medium

### Tasks:
1. **Webhook Signature Validation**
   - Verify Paystack webhook signatures
   - Prevent replay attacks

2. **Subscription State Machine**
   - Implement: active → expired → grace period → downgrade
   - Add proper transitions

3. **Retry Logic**
   - Handle failed payment webhooks
   - Queue and retry机制

4. **Invoice Generation**
   - Generate invoices for purchases
   - Email receipts

### Files to update:
- `payments/paystack_webhook.py`
- `services/subscription_manager.py`

---

## Phase 4: ML & Signal Quality
Status: In Progress | Priority: High

### Tasks:
1. **Fix Gemini Audit Pipeline**
   - Current: Has issues with async session
   - Already partially fixed

2. **Walk-Forward Optimization**
   - Implement rolling window optimization
   - Track performance over time

3. **Backtesting Against Live Data**
   - Compare backtest vs live outcomes
   - Identify overfitting

4. **Signal Calibration**
   - Track win rate by asset class
   - Adjust weights dynamically

### Files to update:
- `ml/model_optimizer.py`
- `engine/backtest.py`

---

## Phase 5: Competitive Features
Status: Not Started | Priority: Medium

### Tasks:
1. **Copy Trading**
   - Mirror signals to follower accounts
   - Track leader performance

2. **Risk-Adjusted Position Sizing**
   - Size positions per user account equity
   - Implement portfolio-level risk

3. **Signal Leaderboard**
   - Public win rate page
   - Transparent performance tracking

4. **Multi-Exchange Support**
   - Binance, Bybit, OKX direct execution
   - Unified execution layer

5. **Mobile Push Notifications**
   - iOS/Android push alongside Telegram
   - Use FCM or similar

6. **Backtesting Dashboard**
   - Visual equity curve per strategy
   - Performance charts

7. **Community Tier**
   - Users vote on signal quality
   - Reputation system

---

## Implementation Notes

### Testing Checklist:
- [ ] Test signal generation flow
- [ ] Verify score distribution
- [ ] Check ML filter pass rate
- [ ] Validate delivery pipeline
- [ ] Test tier gating

### Deployment Steps:
1. Apply Phase 1 fixes first
2. Monitor signal generation for 24h
3. Adjust thresholds as needed
4. Begin Phase 2 (MT5) after stabilization

### Monitoring Metrics:
- `generated_signals` - Total signals generated per cycle
- `final_signals` - Signals passing all filters
- `max_score` - Highest scoring signal
- `delivery_rate` - Signals delivered vs stored
- `win_rate` - Outcome tracking

---

Last Updated: 2024
Owner: SignalRankAI Team
