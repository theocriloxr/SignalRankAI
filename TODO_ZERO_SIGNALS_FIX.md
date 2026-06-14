# Zero Signals Fix Plan

## Problem
Engine generates 0 signals across all cycles despite processing 20 assets.

## Root Cause Analysis
1. Binance API blocked in Railway deployment region (Nigeria)
2. Fallback providers (CryptoCompare, Bybit) may also be blocked
3. IMP strategy requires strict multi-timeframe data (50+ candles on 4h, 30+ on 1h)

## Fix Plan

### Phase 1: Enable Fallback Providers
1. Set CRYPTO_DATA_PROVIDER=cryptocompare in Railway env vars
2. Ensure CRYPTOCOMPARE_API_KEY is set
3. Test with reduced candle requirements

### Phase 2: Lower Strategy Thresholds
1. Reduce IMP strategy candle requirements:
   - 4h: 50 → 20 candles
   - 1h: 30 → 15 candles
2. Make strategy more lenient for degraded mode

### Phase 3: Add More Aggressive Fallbacks
1. Add Yahoo Finance as crypto fallback (if not in use)
2. Enhance degraded mode detection

### Phase 4: Debug Logging
1. Add more verbose logging for data fetching
2. Track which assets get data vs not

## Implementation Steps
1. [ ] Add env var check for CRYPTOCOMPARE_API_KEY
2. [ ] Modify IMP strategy candle minimums
3. [ ] Test with direct API calls
4. [ ] Deploy and monitor

## Quick Diagnostic
Run this to test providers manually:
```python
from data.fetcher import get_candles
candles = get_candles("BTCUSDT", "1h")
print(f"Got {len(candles)} candles")
