# Asset Discovery Fix - TODO

## Problem
The engine shows "Total Scanned: 0" because pair discovery returns 0 assets. Root cause: Binance geoblocked + fallback logic broken.

## Root Cause
1. Railway servers in US-East (restricted region)
2. Binance API returns "restricted location" error
3. Auto-switch to CryptoCompare has timing/consistency bug

## Fix Plan

### Phase 1: Validate Current State
- [ ] Check if Binance is actually blocked (review logs)
- [ ] Check if CRYPTO_DATA_PROVIDER is set to cryptocompare
- [ ] Test CryptoCompare endpoint directly with curl

### Phase 2: Fix Auto-Switch Logic
- [ ] Ensure `_binance_top_crypto_pairs()` doesn't return [] when blocked - should try CryptoCompare immediately
- [ ] Or use explicit env var fallback before making Binance call

### Phase 3: Alternative Data Sources
- [ ] Add manual asset whitelist option for testing
- [ ] Add fallback hardcoded crypto pairs list
- [ ] Verify all provider endpoints work

### Phase 4: Database Jumpstart
- [ ] Insert test assets directly into DB
- [ ] Run query to verify assets exist: `SELECT count(*) FROM assets WHERE is_active = true`

## Commands to Run
```bash
# Test CryptoCompare API
curl "https://min-api.cryptocompare.com/data/top/totalvolfull?limit=10&tsym=USD"

# Test Binance (will fail)
curl "https://api.binance.com/api/v3/ticker/24hr"

# Check DB
SELECT count(*) FROM assets WHERE is_active = true;
```

## Status
- [ ] IN PROGRESS
