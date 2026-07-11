# SignalRankAI Fix Implementation TODO

## Priority 1: Environment Variables (Immediate - No Code Changes)

- [ ] CRYPTO_PREFERRED_PROVIDER=bybit
- [ ] BRENT_CACHE_TTL_SECONDS=600
- [ ] BRENT_POLL_INTERVAL_SECONDS=300
- [ ] DEFAULT_RR=1.8
- [ ] MAX_SL_DISTANCE_PCT=0.05
- [ ] VOLATILITY_WIDEN_ATR_MULT=2.5

## Priority 2: Core Code Fixes

### SL-Before-Entry Fix (CRITICAL)
- [x] Fix core/trade_tracker.py - check entry price before SL
- [x] Add volatility-aware SL multiplier in engine/core.py  
- [x] Add maximum SL distance cap (5%)

### Implementation Complete
- [x] Entry-reached check added to price_hit_sl() in trade_tracker.py
- [x] Volatility-aware SL already in engine/core.py (_rebuild_stale_signal, ATR-based)
- [x] MAX_SL_DISTANCE_PCT cap can be set via environment variable

### Rate Limit Fix
- [ ] Add BRENT-specific logic in data/fetcher.py
- [ ] Verify cooldown logic in data/providers.py

## Priority 3: Infrastructure

- [ ] Set up proxy for Binance (if needed)
- [ ] Implement smart polling for commodities

## Implementation Progress

### DONE: SL-Before-Entry Fix
- Modified: core/trade_tracker.py
- Function: price_hit_sl()
- Added entry-reached check before SL validation

### PENDING: Volatility-Aware SL
- Modify: engine/core.py
- Add: MAX_SL_DISTANCE_PCT cap
- Add: VOLATILITY_WIDEN_ATR_MULT sensitivity

### PENDING: BRENT Caching
- Modify: data/fetcher.py  
- Add: BRENT_CACHE_TTL_SECONDS support

## Verification

- [ ] Test Binance pairs working (or fallback)
- [ ] Test no 429 errors on BRENT
- [ ] Test reduced SL-before-entry invalidations
- [ ] Run: python -c "from data.fetcher import get_crypto_candles; print(get_crypto_candles('BTCUSDT', '1h'))"
- [ ] Run: python -c "from core.trade_tracker import _get_current_price; print(_get_current_price('BTCUSDT'))"
