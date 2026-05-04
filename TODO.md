# SignalRankAI - Multi-Provider Data & Signal Generation Fixes

## Task Summary
Fix the SignalRankAI system to:
1. Use data from ANY provider (not specific ones)
2. Normalize data format from all providers  
3. Generate signals for open markets only (crypto, FX, stocks, commodities)
4. Auto-send signals/outcomes to owner/admin

## Log Issues Identified
- SyntaxError in engine/core.py line 161 (_FallbackThresholdOptimizer)
- Provider rate limits: TwelveData 429, Polygon 429, Gemini quota exceeded
- Symbols failing: USDTIDR, BTCIDR, BTCJPY, ETHIDR, DOGEIDR, MANTAIDR, USDTARS
- Working: Yahoo Finance (some FX), CryptoCompare (crypto)

## Plan

### 1. Fix SyntaxError (engine/core.py ~line 161)
- Verify `_FallbackThresholdOptimizer` class is properly defined before instantiation

### 2. Improve Provider Fallback (data/fetcher.py)
- Add Yahoo Finance as crypto fallback when Binance/Bybit/CryptoCompare fail
- Add more FX providers as fallbacks
- Implement circuit breaker (track/deprioritize dead providers)

### 3. Normalize Data Format (data/connectors/)
- Standardize candle format: timestamp, open, high, low, close, volume

### 4. Market Hours Check (data/market_hours.py)
- Already implemented in `market_closed_reason()`
- Use for all asset classes: crypto (24/7), FX, stocks, commodities

### 5. Signal Auto-Delivery
- Already implemented in `engine/core.py` main_loop()
- Owner/admin receive all signals that meet their requirements

## Files to Modify
- engine/core.py
- data/fetcher.py  
- data/connector_registry.py
- data/connectors/*.py

## Testing
- Deploy to Railway and verify logs
- Check provider fallback behavior
- Verify signals generate for open markets only
