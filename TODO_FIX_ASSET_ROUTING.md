# TODO: Fix Asset Routing for Multi-Asset Support

## Task Summary
Fix the bot treating stocks (MA) and commodities (WTI) like crypto, causing "Ghost Price" and "Sensor Misalignment" errors.

## Implementation Plan

### Phase 1: Market Hours Check
- [ ] 1.1 Add `is_open_now()` function to market_hours.py to check if NYSE is currently open
- [ ] 1.2 Add `get_asset_class()` function to determine asset class from ticker
- [ ] 1.3 Add market hours check in engine/loop.py to skip signal generation when markets closed

### Phase 2: Strict Asset Routing  
- [ ] 2.1 Update fetcher_router.py to use TwelveData as primary for stocks/commodities (not Polygon)
- [ ] 2.2 Add asset class detection in the router
- [ ] 2.3 Ensure crypto providers are disabled when fetching equity/commodity data

### Phase 3: Ticker Namespacing
- [ ] 3.1 Add namespaced ticker support (EQUITY:MA, COMMODITY:WTI, CRYPTO:BTC)
- [ ] 3.2 Update price_validator.py to parse namespaced tickers
- [ ] 3.3 Update db/models.py if needed for namespaced ticker storage

### Phase 4: Provider Priority Changes
- [ ] 4.1 Prioritize TwelveData over Polygon for stocks (Polygon has 5 calls/min limit)
- [ ] 4.2 Configure slow-poll strategy for stocks (update every 2 min vs crypto 20s)

## Technical Details

### Changes to market_hours.py
```python
def is_open_now(asset_class: str = "stock") -> Tuple[bool, str]:
    """Check if market is currently open for given asset class."""
    # For stocks: check if NYSE is open (9:30 AM - 4:00 PM ET, Mon-Fri)
    # For crypto: always open (24/7)
    # For commodities: check CME hours
    # For FX: check major market hours
```

### Changes to engine/loop.py
```python
# Before processing asset:
if not is_open_now(asset_class):
    logger.info(f"Market closed for {asset_class}, skipping {asset}")
    return []
```

### Changes to fetcher_router.py
```python
# Stock providers priority:
# Twelve Data -> Polygon -> Yahoo (Polygon last due to rate limits)
```

### Ticker Namespacing Format
- EQUITY:MA (Mastercard stock)
- CRYPTO:BTC (Bitcoin)
- COMMODITY:WTI (Crude Oil)
- FORX:EURUSD (EUR/USD forex)
