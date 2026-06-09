# TODO: Multi-Asset Pipeline Stabilization Plan

## Overview
Based on the comprehensive analysis of the SignalRankAI codebase, the following fixes are required to stabilize all asset classes (Crypto, Forex, Commodities, Stocks) and implement Gemini-driven dynamic asset discovery.

## Priority 1: CRITICAL FIXES (Production Impact)

### 1.1 CoinGecko History Extension - FIX "42 Candle Trap"
**Problem**: CoinGecko only fetches ~42 hourly candles but 50-period indicators need 50+ candles. This causes indicators to return NaN and strategies to output 0 signals for Crypto.

**Location**: `data/providers.py` - `fetch_coingecko_candles()`

**Current Code**:
```python
days_map = {"5m": 1, "15m": 1, "1h": 7, "4h": 30, "1d": 365}
```

**Fix**: Increase days to fetch more history
```python
days_map = {"5m": 2, "15m": 3, "1h": 14, "4h": 60, "1d": 365}
```

**Risk**: Higher API rate limits - may need to handle 429 responses

---

### 1.2 Stock Market Hours Guard - FIX "After-Hours Flatline"
**Problem**: Bot evaluates stocks at 2 AM EST when markets closed. Volume=0, price flat. Results in false "breakout" signals when market opens.

**Location**: `engine/confluence_engine.py` or `engine/core.py` loop

**Fix Options**:
Option A - Add to confluence_engine.py:
```python
from data.market_hours import is_market_open, get_asset_class

def run_confluence_engine(candles, asset=None, asset_type=None):
    # Stock market hours check
    if asset_type == "stock" or (asset and get_asset_class(asset) == "stock"):
        if not is_market_open("stock"):
            logger.debug(f"[confluence] Skipping {asset} - US market closed")
            return {
                "long_votes": 0, "short_votes": 0, "total": 15,
                "direction": "NEUTRAL", "score": 0, "drivers": [], "passed": False,
            }
```

Option B - Add to engine loop (preferred):
```python
# In engine/loop.py or engine/core.py
for asset in assets:
    asset_type = get_asset_type(asset)
    
    # Skip stocks when market closed
    if asset_type == "stock":
        reason = market_closed_reason(asset)
        if reason:
            logger.info(f"[engine] Skipping {asset} - {reason}")
            continue
```

---

## Priority 2: FEATURE ENHANCEMENTS

### 2.1 Gemini-Driven Dynamic Pair Discovery
**Problem**: Static fallback pairs - engine checks same 20 pairs regardless of market regime

**Solution**: Implement Gemini-managed asset selection in `data/pair_discovery.py`

**New Function**: `get_gemini_curated_assets(raw_market_data, macro_regime)`

**Implementation Steps**:
1. Add `get_gemini_curated_assets()` function in pair_discovery.py
2. Create prompt for Gemini 2.0 Flash to select top 20 assets
3. Pass macro regime (VIX, DXY) context
4. Return JSON array of curated assets
5. Add graceful fallback to hardcoded pairs if Gemini fails

**Code Structure**:
```python
import json
from google.generativeai import GenerativeModel

async def get_gemini_curated_assets(raw_market_data: dict, macro_regime: dict) -> list[str]:
    """
    Pass raw market volume/volatility data to Gemini 2.0 to select 
    best 20 assets for current market regime.
    """
    model = GenerativeModel("gemini-2.0-flash")
    
    prompt = f"""
    You are the Chief Investment Officer of an algorithmic trading fund.
    Current Macro Regime: VIX is {macro_regime['VIX']}, DXY is {macro_regime['DXY']}
    
    Here is the raw data for 100 global assets today:
    {raw_market_data}
    
    Task: Select exactly 20 assets with best liquidity and volatility 
    for algorithmic day-trading under current macro regime.
    
    Return ONLY raw JSON array of strings. Example: ["BTCUSDT", "XAUUSD", "USDJPY=X"]
    """
    
    try:
        response = await model.generate_content_async(prompt)
        curated_top_20 = json.loads(response.text.strip('```json\n').strip('```'))
        return curated_top_20
    except Exception as e:
        logger.error(f"Gemini Asset Discovery Failed: {e}")
        return _HARDCODED_CRYPTO_PAIRS[:20]  # Fallback
```

---

### 2.2 Enhanced CoinGecko Error Handling
**Problem**: Need to handle 429 rate limits gracefully

**Location**: `data/providers.py` - `fetch_coingecko_candles()`

**Fix**: Add cooldown and exponential backoff
```python
if resp.status_code == 429:
    _set_cooldown("coingecko", 60.0 * (retry + 1))  # 60s, 120s, 180s
```

---

## Priority 3: MONITORING & VERIFICATION

### 3.1 SQL Verification Query
Run after fixes to verify all asset classes working:

```sql
SELECT asset_class, COUNT(*) 
FROM signals 
WHERE status IN ('active', 'pending')
GROUP BY asset_class;
```

### 3.2 Log Monitoring Points
- `[data] crypto_provider=coingecko candles=XX` - Should be 50+ for 1h
- `[confluence] Skipping XXX - Market is closed` - Stock guard working
- `[pair_discovery] Using Gemini curated assets` - Dynamic discovery enabled

---

## File Modification Summary

| File | Change Type | Priority |
|------|------------|----------|
| data/providers.py | Fix CoinGecko days + 429 handling | P1 |
| engine/confluence_engine.py | Add stock hours check | P1 |
| data/pair_discovery.py | Add Gemini dynamic discovery | P2 |
| data/market_hours.py | Verify existing checks | Review |

---

## Rollback Plan

If issues occur:
1. Revert `data/providers.py` days_map to original values
2. Disable stock check by setting `STOCK_MARKET_HOURS_CHECK=0`
3. Set `GEMINI_DYNAMIC_DISCOVERY=0` to disable feature

---

## Implementation Order

1. Day 1: CoinGecko history fix (1 file, ~10 min)
2. Day 2: Stock market hours guard (2 files, ~30 min)
3. Day 3: Gemini dynamic discovery (1 new function, ~60 min)
4. Day 4: Verification and monitoring

---

## Notes

- The fillna(0) fix for Forex is already implemented in yfinance_adapter.py
- Forward-fill TTL is already in fetcher.py
- market_hours.py functions exist and work correctly
