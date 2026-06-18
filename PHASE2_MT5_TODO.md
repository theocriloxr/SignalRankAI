# Phase 2: MT5 Integration Implementation TODO

## Step 1: Create Enhanced MT5 Models
- [x] Create `db/mt5_models.py` - Enhanced account tracking with multi-account per user
- [x] Add MT5Account table to track linked accounts

## Step 2: Create Signal Router
- [x] Create `services/mt5_signal_router.py` - Route signals to MT5 or paper
- [x] Integrate tier gating (paid users only)
- [x] Connect to paper_ledger for sync

## Step 3: Test Integration
- [ ] Test signal routing
- [ ] Test paper ledger sync

## Phase 3: Payment Hardening - COMPLETED
- [x] `services/subscription_manager.py` - PostgreSQL-backed subscription state machine
- [x] `payments/invoice_service.py` - Invoice and receipt generation

## Phase 4: ML Signal Quality - COMPLETED
- [x] `ml/signal_calibrator.py` - Dynamic weight adjustment

## Start Date: 2024
