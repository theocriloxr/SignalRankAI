# TODO: Fix Signal Generation - ML Drift, Strategies, and Thresholds

## Information Gathered

From startup logs analysis:
- Engine running with 20 assets but generating 0 signals per cycle
- ML Drift detected: Δacc=0.120, Δauc=0.333 with many drifted features
- Max score = None, strategy_signals = 0
- Binance disabled due to geo-restriction but uses fallback

### Root Causes Identified:
1. ✅ **Thresholds properly lowered**: Score 40, ML 0.40 (already fixed in config.py)
2. ✅ **Strategy code fixed**: get_htf_bias() properly structured (no bug)
3. ⚠️ **ML Drift**: Informational warning (logs to ml_drift.json), not blocking
4. ⚠️ **Data providers**: May fail in Nigeria location - needs verification

## Plan

### Step 1: Ensure Fallback Strategies Always Run (CRITICAL)
- [x] 1.1: Confirmed fallback_strategies exist in strategies/fallback.py
- [x] 1.2: Logic in strategies/__init__.py properly triggers fallback

### Step 2: Verify Data Provider Chain
- [ ] 2.1: Check CRYPTOCOMPARE_API_KEY is set in Railway env
- [ ] 2.2: Verify BYBIT_API_KEY is set as fallback
- [ ] 2.3: Check provider chain logs for failures

### Step 3: Lower Degraded Mode Threshold (Emergency)
- [x] 3.1: Already lowering to 5 candles in fetcher.py

### Step 4: Thresholds (Already Fixed)
- [x] 4.1: Score threshold = 40 (FIXED in config.py)
- [x] 4.2: ML probability = 0.40 (FIXED in config.py)

### Step 5: Force Strategy Generation (Override)
- [ ] 5.1: Add emergency env var to bypass all filtering

## Code Changes Made

### Change 1: config.py - Thresholds already at 40
```python
self.PREMIUM_SCORE_THRESHOLD = 40.0
self.ML_PROB_THRESHOLD = 0.40
```

### Change 2: data/fetcher.py - Degraded mode 5 candles
```python
return 5  # Lowered from 10 to 5 on 2026-06-12
```

## What's Working
- ✅ Thresholds properly lowered (Score 40, ML 0.40)
- ✅ Fallback strategies system in place
- ✅ Multi-provider fallback chain (Binance → Bybit → CryptoCompare)
- ✅ Degraded mode (5 candles minimum)
- ✅ Forward-fill cache for stale data
- ✅ ML drift logging (informational, not blocking)

## Most Likely Issue: Provider Failures in Nigeria

The logs show "Binance geo-blocked" but the provider chain should fall back to:
1. Bybit (usually works worldwide)
2. CryptoCompare (requires API key)

### Action Required

1. **Must set in Railway environment variables:**
   - `CRYPTOCOMPARE_API_KEY` - Get free key from cryptocompare.com
   - `BYBIT_API_KEY` (optional) - Already has public API

2. **Verify with logs:** Look for lines like:
   - `[data] crypto_provider=cryptocompare symbol=BTCUSDT tf=1h candles=150`
   - `[fetcher] Insufficient candles for BTCUSDT 1h: got 0, need >= 5`

### Emergency Override (if needed)
Set `USE_FALLBACK_STRATEGIES=true` and ensure assets are being fetched correctly.

## Railway Deployment Notes

### Environment Variables to Set in Railway Dashboard:

| Variable | Required | Source |
|----------|----------|--------|
| `CRYPTOCOMPARE_API_KEY` | YES - Get free key from cryptocompare.com | cryptocompare.com |
| `BYBIT_API_KEY` | Optional | Bybit account (public API available) |
| `BYBIT_SECRET` | Optional | Bybit account |

### Startup Log Indicators:

Success (signals should generate):
```
[data][BYBIT] symbol=BTCUSDT tf=1h candles=150
[data][CRYPTO] provider=bybit
[engine] strategy_signals generated: count=1
[engine] max_score=65
```

Failure (no signals):
```
[data][FETCHER] All providers failed for BTCUSDT
[engine] Data Starvacion: returned empty candles
[engine] No strategy signals for BTCUSDT
```

### Check Railway Logs for:
1. `[data]` lines showing provider success
2. `[engine] pipeline` logs showing asset processing
3. `[engine] strategy_signals generated` - confirms strategies ran

## Followup Steps
1. Deploy with CRYPTOCOMPARE_API_KEY set in Railway
2. Monitor logs for provider success/failure
3. Expected output: `[data] crypto_provider=bybit symbol=... candles=...` or `cryptocompare`
4. If still no signals, check `[engine] No strategy signals for` lines
