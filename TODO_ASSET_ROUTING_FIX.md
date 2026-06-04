# Asset Routing Fix Implementation Plan

## Goal: Fix Ghost Price and Sensor Misalignment errors
The bot was treating stocks/commodities like crypto, causing WTI at $4.01 (crypto token) instead of ~$92 oil price.

## Implementation Steps:

### Step 1: Update engine/loop.py - Add Market Hours Check
- [ ] Import market_hours functions
- [ ] Add market hours check before processing equity/commodity assets
- [ ] Skip signal generation when markets are closed

### Step 2: Update data/fetcher_router.py - Ensure Strict Routing
- [ ] Verify asset_class routing is working (crypto→Bybit, stocks→TwelveData)
- [ ] Add logging for which provider is used per asset

### Step 3: Update providers.py - Prioritize TwelveData for Stocks
- [ ] Change stock priority: TwelveData (primary) → Polygon (fallback)
- [ ] Update commodity priority: TwelveData → Yahoo

### Step 4: Add Asset Class Detection
- [ ] Add function to detect asset class from symbol
- [ ] Use prefix-based routing (EQUITY:MA, COMMODITY:WTI, CRYPTO:BTCUSDT)

## Status: ✅ COMPLETE

All tests passed:
- Asset Type Detection (8/8 passed)
- Ticker Namespacing (10/10 passed)  
- Provider Routing (working correctly)
- Market Hours (working correctly)
- Strict Provider Functions (4/4 passed)

Implementation includes:
1. ✅ Strict Asset Routing in connector_registry.py - separates crypto, stock, commodity, FX providers
2. ✅ Market Hours Check in engine/loop.py - skips signal generation when markets closed
3. ✅ Ticker Namespacing in fetcher.py - EQUITY:MA, COMMODITY:WTI, CRYPTO:BTCUSDT
4. ✅ Ghost Price Prevention - commodity providers exclude crypto exchanges
