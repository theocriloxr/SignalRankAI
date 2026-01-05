# 🧪 Testing Guide - Signal-Only Bot

## Quick Test Commands

### 1. Test in DRY_RUN Mode

```bash
# In PowerShell on Railway or local
python main.py --dry-run
```

**What to look for**:
- Console shows: `[engine] cycle=1 start`
- Signals printed with all new fields (entry_zone, htf_bias, session)
- Filter rejections if `ENGINE_SIGNAL_DEBUG=true`

### 2. Test Individual Modules

#### Test MTF Analyzer
```python
from engine.mtf_analysis import MultiTimeframeAnalyzer
from data.market_data import fetch_market_data_cached
import asyncio

# Fetch data
candles = asyncio.run(fetch_market_data_cached('BTCUSDT', ['5m', '15m', '1h', '4h']))

# Test HTF bias
analyzer = MultiTimeframeAnalyzer()
htf_bias = analyzer.get_htf_bias('BTCUSDT', '5m', candles)
print(f"HTF Bias: {htf_bias}")

# Should show: {'bias': 'bullish', 'confidence': 80, 'tf': '1h', ...}
```

#### Test Signal Context
```python
from engine.signal_context import SignalContext

context = SignalContext()

# Test entry zone
zone = context.calculate_entry_zone(45000, atr=500, direction='long')
print(f"Entry Zone: {zone}")
# Should show: {'entry_price': 45000, 'zone_low': 44750, 'zone_high': 45250, ...}

# Test session detection
session = context.detect_trading_session()
print(f"Current Session: {session}")
# Should show: ASIA, LONDON, NY, or LONDON_NY_OVERLAP
```

#### Test Advanced Filters
```python
from engine.advanced_filters import SmartFilterSuite

filters = SmartFilterSuite()

# Test all filters
passed, rejections = filters.run_all_filters(
    signal={'symbol': 'BTCUSDT', 'direction': 'long', 'trigger': 'trend'},
    market_data={
        'price': 45000,
        'ema_20': 44800,
        'ema_50': 44500,
        'atr': 500,
        'candles': [],  # Add real candles
        'adx': 25,
        'atr_pct': 4.5
    },
    session='LONDON'
)

print(f"Passed: {passed}, Rejections: {rejections}")
```

#### Test Tier Notifications
```python
from engine.tier_notifications import TierNotificationManager

notifier = TierNotificationManager()

# Test Premium signal
signal = {
    'symbol': 'BTCUSDT',
    'direction': 'long',
    'timeframe': '1h',
    'entry_price': 45000,
    'sl_price': 44400,
    'sl_pct': -1.33,
    'tp_levels': [
        {'price': 46200, 'pct': 2.67, 'exit_percent': 33},
        {'price': 47400, 'pct': 5.33, 'exit_percent': 33}
    ],
    'score': 85,
    'confluence_count': 5,
    'confluence_total': 5,
    'rr_ratio': 2.4,
    'id': 'test123'
}

msg = notifier.format_new_signal(
    signal,
    'premium',
    {'zone_low': 44800, 'zone_high': 45200, 'status': 'BUY'},
    {'bias': 'bullish', 'confidence': 80, 'tf': '4h'},
    {'score': 75},
    'LONDON'
)

print(msg)
```

### 3. Test Signal Generation End-to-End

Create a test file `test_signal_generation.py`:

```python
import asyncio
from engine.core import main_loop
import os

# Set test environment
os.environ['DRY_RUN'] = 'true'
os.environ['ENGINE_CYCLE_LOG'] = 'true'
os.environ['ENGINE_SIGNAL_DEBUG'] = 'true'
os.environ['CYCLE_SLEEP_SECONDS'] = '0'  # No sleep for testing
os.environ['TRADABLE_ASSETS'] = 'BTCUSDT,ETHUSDT'

# Run one cycle
main_loop(DRY_RUN=True)
```

Run:
```bash
python test_signal_generation.py
```

**What to verify**:
1. Signals have `entry_zone`, `htf_bias`, `session`, `mtf_confluence`
2. No signals show mid-candle (all should be on candle close)
3. Cooldown prevents duplicate signals
4. HTF validation rejects counter-trend signals
5. Advanced filters reject bad setups

### 4. Test Database Integration

```python
from db.pg_compat import store_signal_compat
from datetime import datetime

test_signal = {
    'symbol': 'BTCUSDT',
    'direction': 'long',
    'timeframe': '1h',
    'entry_price': 45000,
    'sl_price': 44400,
    'tp_levels': [{'price': 46200, 'pct': 2.67}],
    'score': 85,
    'htf_bias': {'bias': 'bullish', 'confidence': 80, 'tf': '4h'},
    'entry_zone': {'zone_low': 44800, 'zone_high': 45200},
    'session': 'LONDON',
    'expires_at': datetime.utcnow(),
    'invalid_if_price': 44200
}

try:
    store_signal_compat(test_signal)
    print("✅ Signal stored successfully")
except Exception as e:
    print(f"❌ Error storing signal: {e}")
```

### 5. Test Telegram Integration

Update `signalrank_telegram/formatter.py` first (Task #6), then:

```python
from signalrank_telegram.formatter import TelegramFormatter

formatter = TelegramFormatter()

# Test signal formatting
msg = formatter.format_signal(test_signal, user_tier='premium')
print(msg)

# Verify:
# - Entry zone shows as range
# - HTF bias displayed
# - Session tag present
# - Confluence score shown
# - Premium details included
```

## 🔍 What to Look For

### Good Signs ✅
- Signals have score >= 75
- HTF bias matches signal direction
- Entry zone is realistic (±1% or 0.5 ATR)
- Session tags present (🌏🇬🇧🇺🇸)
- No signals during chop (ADX <20)
- Cooldown prevents spam
- Premium notifications have detailed advice

### Bad Signs ❌
- Signals with conflicting HTF bias (should be rejected)
- Mid-candle signals (should wait for close)
- Same pair/TF signals within 60 min (cooldown failure)
- Multiple directions for same pair/TF (one-bias violation)
- Signals during news events (filter failure)
- Missing entry_zone or htf_bias fields

## 📊 Expected Output Examples

### Console Output (DRY_RUN):
```
[engine] cycle=1 start
[engine] cycle=1 assets_split crypto=2 fx=0 sample=BTCUSDT,ETHUSDT
[engine] signal rejected: BTCUSDT 5m - ['HTF bearish (conf 80%)']
[engine] signal rejected: ETHUSDT 15m - ['Choppy market (ADX 15)']
[DRY RUN] {'symbol': 'BTCUSDT', 'direction': 'long', 'score': 85, 'entry_zone': {...}, 'htf_bias': {...}, ...}
[engine] cycle=1 candidates=12 scored>=75.00=1 stored=1
```

### Signal Output (Premium):
```
🔥 STRONG LONG SIGNAL | 🇬🇧 LONDON
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 BTCUSDT | 1H
Entry Zone: $44,800 - $45,200
Current: $45,000 ✅ BUY
...
```

### Signal Output (Free):
```
🔥 STRONG LONG SIGNAL | 🇬🇧 LONDON
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 BTCUSDT | 1H
Entry Zone: $44,800 - $45,200
Current: $45,000 ✅ BUY
...
Score: 85/100
R:R: 2.4:1
```

## 🐛 Common Issues & Fixes

### Issue: No signals generated
**Cause**: Filters too strict
**Fix**: 
```bash
# Check filter rejections
ENGINE_SIGNAL_DEBUG=true python main.py --dry-run

# Temporarily lower threshold
MIN_SCORE_THRESHOLD=65 python main.py --dry-run
```

### Issue: HTF bias always None
**Cause**: Not enough candles for higher timeframe
**Fix**: Ensure candles fetched for all TFs (5m, 15m, 1h, 4h, 1d)

### Issue: Candle close check fails
**Cause**: Candle data missing 'is_final' field
**Fix**: Falls back to time-based check automatically

### Issue: Advanced filters reject everything
**Cause**: Market conditions genuinely bad OR missing data
**Fix**: 
- Check `market_data` has all required fields
- Test during active trading hours
- Verify ADX, ATR calculations working

## ✅ Testing Checklist

Before deploying:

- [ ] MTF analyzer returns HTF bias correctly
- [ ] Signal context calculates entry zones
- [ ] Advanced filters reject bad signals
- [ ] Tier notifications format correctly (Premium vs Free)
- [ ] Candle close check prevents mid-candle signals
- [ ] Cooldown prevents signal spam
- [ ] One-bias-per-TF enforced
- [ ] Session detection accurate
- [ ] Signal expiration calculated
- [ ] Database stores all new fields
- [ ] Telegram formatter uses new format
- [ ] Outcome tracking sends notifications
- [ ] NO TRADE alerts work
- [ ] Full end-to-end test passes

## 🚀 Ready for Production When:

1. ✅ All tests pass
2. ✅ Sample signals look correct
3. ✅ No errors in console
4. ✅ Database updates work
5. ✅ Telegram messages format properly

---

**After testing**: Deploy to Railway, monitor first few cycles, adjust filters as needed.
