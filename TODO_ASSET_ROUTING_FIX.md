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

## Status: In Progress
