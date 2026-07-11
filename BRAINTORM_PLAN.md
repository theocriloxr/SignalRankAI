# SignalRankAI Comprehensive Fix Plan

## Executive Summary

Based on diagnostic log analysis, three main issues require attention:

1. **Binance geo-blocking** - IP from Railway restricted location
2. **Rate limiting (429 errors)** - Polygon and TwelveData for BRENT
3. **SL-before-entry invalidations** - Price hitting stop loss before entry price

---

## Issue 1: Binance Geo-Blocking

### Root Cause
Railway's data center IP is in a restricted location (geo-blocked by Binance).

### Current Mitigation in Place
The system already has fallbacks in:
- `data/fetcher.py`: `_BINANCE_BLOCKED_REASON` global flag
- `data/fetcher.py`: `is_binance_blocked()` function
- Fallback chain: Binance → Bybit → CryptoCompare

### Proposed Solutions

#### Option A: Use Proxy (Recommended)
Set environment variable for proxy:
```
HTTP_PROXY=socks5://your-proxy-ip:port
HTTPS_PROXY=socks5://your-proxy-ip:port
```

#### Option B: Prioritize Bybit/CryptoCompare
Ensure fallback providers are tried first:
```python
# In data/fetcher.py - crypto provider priority
CRYPTO_PREFERRED_PROVIDER=bybit  # or cryptocompare
```

### Files to Modify
- `config.py` or environment variables
- `data/fetcher.py` (already has fallback logic)

---

## Issue 2: Rate Limiting (429 Errors) - Polygon & TwelveData for BRENT

### Root Cause
Excessive polling for BRENT commodity - API rate limits being hit.

### Current Mitigation in Place
- `_rate_limit_cooldown_seconds()` in `data/providers.py` sets:
  - TwelveData: 12-hour cooldown after 429
  - Polygon: 1-hour cooldown after 429

### Proposed Solutions

#### Solution 1: Increase polling interval for BRENT
```bash
# Add to environment
BRENT_POLL_INTERVAL_SECONDS=300  # 5 minutes instead of frequent
```

#### Solution 2: Cache BRENT data longer
```bash
BRENT_CACHE_TTL_SECONDS=600  # 10 minute cache
```

#### Solution 3: Implement smarter polling
- Only poll BRENT during high-liquidity hours (7am-10pm UTC)
- Skip BRENT if market is closed

### Files to Modify
- `data/fetcher.py` - add BRENT-specific logic
- `data/market_hours.py` - ensure commodity hours are correct

---

## Issue 3: SL-Before-Entry Invalidations

### Root Cause Analysis
From logs: "SL hit before entry" - This means:
1. Signal generated with entry price X
2. Price moved down and hit stop loss Y BEFORE reaching entry X
3. Signal invalidated

### Where This Happens
- `core/trade_tracker.py`: Checks if current price <= stop_loss
- `engine/realtime_outcome_tracker.py`: Marks signals as invalidated when SL hit pre-entry

### Root Causes
1. **Entry price not refreshed** - Signal entry doesn't update to live price
2. **Too wide SL** - SL too far from entry in volatile markets
3. **Market gap** - Price gaps down past SL at market open
4. **Stale signal** - Signal sits too long before execution

### Proposed Fixes

#### Fix 1: Tighten SL calculation in volatile markets
In `engine/signal.py` or strategies, add volatility-aware SL:
```python
# Use tighter SL in high volatility
atr_percent = indicators.get('atr_percent', 0)
if atr_percent > 3:  # >3% ATR
    sl_multiplier = 1.5  # Reduce from 2x to 1.5x ATR
else:
    sl_multiplier = 2.0
```

#### Fix 2: Add maximum SL distance from entry (as %)
```python
MAX_SL_DISTANCE_PCT = 0.05  # 5% max
sl_distance = abs(entry - sl)
if sl_distance / entry > MAX_SL_DISTANCE_PCT:
    sl = entry * (1 - MAX_SL_DISTANCE_PCT)  # Cap at 5%
```

#### Fix 3: Force entry price refresh before outcome check
In `core/trade_tracker.py`:
```python
def check_entry_status(signal):
    # Always get fresh price before checking
    current_price = get_live_price(signal['asset'])
    
    # Only check if price has reached entry
    direction = signal['direction']
    if direction == 'long' and current_price >= signal['entry']:
        # Allow outcome tracking
        pass
    elif direction == 'short' and current_price <= signal['entry']:
        pass
    else:
        # Price hasn't reached entry yet - don't check SL
        return 'pending'
```

#### Fix 4: Add "entry timeout" 
- If signal doesn't reach entry within N minutes, invalidate
- Prevents hanging stale signals

---

## Priority Implementation Order

### Phase 1: Immediate (Quick Wins)
1. [ ] Set CRYPTO_PREFERRED_PROVIDER=bybit in env
2. [ ] Add BRENT_CACHE_TTL_SECONDS=600 in env
3. [ ] Reduce DEFAULT_RR from 2.0 to 1.8 for tighter TP

### Phase 2: Core Fixes
1. [ ] Fix SL-before-entry in trade_tracker.py
2. [ ] Add volatility-aware SL multiplier
3. [ ] Add maximum SL distance cap (5%)

### Phase 3: Infrastructure
1. [ ] Set up proxy for Binance
2. [ ] Implement smart polling for commodities

---

## Environment Variables to Add

```bash
# Quick fix - Prioritize Bybit for crypto
CRYPTO_PREFERRED_PROVIDER=bybit

# Reduce rate limit hits on BRENT  
BRENT_CACHE_TTL_SECONDS=600
BRENT_POLL_INTERVAL_SECONDS=300

# Tighter risk management
DEFAULT_RR=1.8
MAX_SL_DISTANCE_PCT=0.05
VOLATILITY_WIDEN_ATR_MULT=2.5  # Stricter volatility detection
```

---

## Files Referenced

| File | Purpose | Changes Needed |
|------|---------|---------------|
| `data/fetcher.py` | Provider routing | Add BRENT-specific caching |
| `data/providers.py` | Rate limiting | Already has cooldowns |
| `core/trade_tracker.py` | Trade monitoring | Fix SL-before-entry check |
| `engine/signal.py` | Signal generation | Volatility-aware SL |
| `config.py` | Configuration | Add new env vars |

---

## Verification Checklist

After implementation:
- [ ] Binance pairs working (or fallback to Bybit)
- [ ] No more 429 errors on BRENT
- [ ] Reduced SL-before-entry invalidations
- [ ] Engine cycles completing successfully

---

*Generated: 2025-01-27*
*Based on diagnostic log analysis*
