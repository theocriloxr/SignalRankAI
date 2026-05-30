# SignalRankAI - Multi-Provider Data & Signal Generation Fixes

## Task Summary
Completed. The system now:
1. Uses fallback data from multiple providers
2. Normalizes provider candle output
3. Gates signal generation by market-open status
4. Auto-sends signals and outcome summaries to owner/admin

## Log Issues Identified
Resolved.
- SyntaxError in engine/core.py line 161 (_FallbackThresholdOptimizer)
- Provider rate limits: TwelveData 429, Polygon 429, Gemini quota exceeded
- Symbols failing: USDTIDR, BTCIDR, BTCJPY, ETHIDR, DOGEIDR, MANTAIDR, USDTARS
- Working: Yahoo Finance (some FX), CryptoCompare (crypto)

## Plan

### 1. Fix SyntaxError (engine/core.py ~line 161)
- [x] Verify `_FallbackThresholdOptimizer` class is properly defined before instantiation

### 2. Improve Provider Fallback (data/fetcher.py)
- [x] Add Yahoo Finance as crypto fallback when Binance/Bybit/CryptoCompare fail
- [x] Add more FX providers as fallbacks
- [x] Implement circuit breaker (track/deprioritize dead providers)

### 3. Normalize Data Format (data/connectors/)
- [x] Standardize candle format: timestamp, open, high, low, close, volume

### 4. Market Hours Check (data/market_hours.py)
- [x] Already implemented in `market_closed_reason()`
- [x] Use for all asset classes: crypto (24/7), FX, stocks, commodities

### 5. Signal Auto-Delivery
- [x] Already implemented in `engine/core.py` main_loop()
- [x] Owner/admin receive all signals that meet their requirements

## Files to Modify
- engine/core.py
- data/fetcher.py  
- data/connector_registry.py
- data/connectors/*.py

## Testing
- [x] Deploy to Railway and verify logs
- [x] Check provider fallback behavior
- [x] Verify signals generate for open markets only
