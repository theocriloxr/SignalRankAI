# SignalRankAI Implementation Roadmap

## Executive Summary

This document outlines the implementation plan for the remaining phases of SignalRankAI. Based on codebase analysis, most foundational components already exist but need integration and enhancement.

**Key Findings:**
- MT5 bridge/client already implemented in `services/mt5_bridge.py` and `services/mt5_client.py`
- Paystack webhook already has signature validation in `payments/paystack_webhook.py`
- Backtest engine with walk-forward analysis exists in `engine/backtest.py`
- Paper ledger exists in `core/paper_ledger.py`
- Gemini validator exists in `services/gemini_ml.py`

---

## Phase 2: MT5 Automated Trading Integration
Status: **Integration Needed** | Priority: High

### Tasks:
1. ✅ **Create mt5_bridge.py service** - ALREADY EXISTS at `services/mt5_bridge.py`
2. ✅ **Create mt5_client.py** - ALREADY EXISTS at `services/mt5_client.py` (MetaApi cloud)
3. **Database Schema Updates** - Enhanced tracking for multi-account per user
4. **Signal Delivery Enhancement** - Route signals to MT5 for paid users
5. **Paper Ledger Sync** - Trade sync between MT5 and paper ledger

### Files to Update/Create:
- [`db/mt5_models.py`](db/mt5_models.py) - NEW: Account tracking models (enhanced)
- [`services/mt5_signal_router.py`](services/mt5_signal_router.py) - NEW: Route signals to MT5/paper
- Update [`db/models.py`](db/models.py) - Add `mt5_accounts` table

### Integration Points:
- Connect to existing `core/paper_ledger.py` for paper trading sync
- Connect to `services/mt5_client.py` for MetaApi execution
- Connect to tier system in `core/tier_constants.py` for paid user gating

---

## Phase 3: Payment System Hardening (Paystack)
Status: **Enhancement Needed** | Priority: Medium

### Tasks:
1. ✅ **Webhook Signature Validation** - Already exists in `payments/paystack_webhook.py`
2. **Subscription State Machine** - Enhance transitions
3. **Retry Logic** - Handle failed webhooks with queue
4. **Invoice Generation** - Generate invoices/receipts

### Files to Update/Create:
- Update [`payments/paystack_webhook.py`](payments/paystack_webhook.py) - Enhance state machine
- Create [`services/subscription_manager.py`](services/subscription_manager.py) - NEW: PostgreSQL-backed manager
- Update [`payments/invoice_service.py`](payments/invoice_service.py) - NEW: Invoice generation

### Integration Points:
- Connect to `db/models.py` Subscription table
- Connect to User tier field
- Queue failed webhooks for retry

---

## Phase 4: ML & Signal Quality
Status: **In Progress** | Priority: High

### Tasks:
1. **Fix Gemini Audit Pipeline** - Async session issues in `services/gemini_ml.py`
2. **Walk-Forward Optimization** - Already exists in `engine/backtest.py`
3. **Backtesting Against Live Data** - Compare backtest vs live
4. **Signal Calibration** - Track win rate by asset class

### Files to Update:
- [`services/gemini_ml.py`](services/gemini_ml.py) - Fix async session
- [`engine/backtest.py`](engine/backtest.py) - Live comparison
- Create [`ml/signal_calibrator.py`](ml/signal_calibrator.py) - NEW: Dynamic weight adjustment

---

## Phase 5: Competitive Features
Status: **Not Started** | Priority: Medium

### Tasks:
1. **Copy Trading** - Mirror signals to followers
2. **Risk-Adjusted Position Sizing** - Per-user equity sizing
3. **Signal Leaderboard** - Public win rate page
4. **Multi-Exchange Support** - Binance, Bybit, OKX
5. **Mobile Push Notifications** - iOS/Android
6. **Backtesting Dashboard** - Visual charts
7. **Community Tier** - Reputation system

### Files to Update/Create:
- Create [`services/copy_trading.py`](services/copy_trading.py) - NEW: Mirror signals
- Create [`services/position_sizer.py`](services/position_sizer.py) - NEW: Risk-adjusted sizing
- Create [`web/leaderboard.py`](web/leaderboard.py) - NEW: Public leaderboard
- Create [`services/exchange_router.py`](services/exchange_router.py) - NEW: Multi-exchange
- Create [`services/push_notifications.py`](services/push_notifications.py) - NEW: FCM push

---

## Implementation Notes

### Testing Checklist:
- [ ] Test MT5 signal routing for paid users only
- [ ] Verify paper ledger sync after MT5 execution
- [ ] Verify webhook signature validation
- [ ] Test subscription state transitions
- [ ] Verify Gemini async session fixes
- [ ] Validate walk-forward metrics

### Deployment Order:
1. Phase 2 - Connect MT5 integration
2. Phase 3 - Enhance payment system  
3. Phase 4 - Fix ML pipeline
4. Phase 5 - Competitive features

### Monitoring Metrics:
- `mt5_executions` - MT5 trades executed
- `paper_trades_synced` - Paper ledger syncs
- `subscription_state_transitions` - State machine events
- `gemini_audit_pass_rate` - Audit approval rate
- `wfo_degradation` - Walk-forward optimization degradation

---

Last Updated: 2024
Owner: SignalRankAI Team
