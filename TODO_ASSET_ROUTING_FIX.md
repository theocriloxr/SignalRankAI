# Asset Routing Fix Implementation Plan

## Phase 1: Ticker Namespacing (Priority: HIGH)
### 1.1 Add namespace helper functions to `data/fetcher.py`
- Add `parse_symbol()` function to extract namespace prefix and raw symbol
- Add `normalize_symbol()` function to add appropriate namespace prefix
- Update `is_stock()`, `is_commodity()`, `is_crypto()`, `is_fx()` to handle namespaced symbols

### 1.2 Update connector_registry.py
- Modify `get_providers_for_asset()` to check asset type from namespaced symbol first
- Add logic to route based on namespace prefix

### 1.3 Update ManagedAsset model (Optional)
- Add migration to backfill asset_type for existing assets

## Phase 2: Market Hours Check (Priority: HIGH)
### 2.1 Add is_market_open() function to `data/market_hours.py`
- Combine holiday + hours check
- Return True/False with reason if closed

### 2.2 Update engine/loop.py
- Add pre-check in `_process_asset_timeframe()` or `run_once()` 
- Skip assets that are closed

### 2.3 Update engine/signal_validator.py
- Add market hours validation before generating signals

## Phase 3: Provider Prioritization Fix (Priority: MEDIUM)
### 3.1 Update connector_registry.py
- Change to prefer TwelveData over Polygon for stocks/commodities
- Use env vars for provider preference override

### 3.2 Add rate limit awareness
- Track calls per minute per provider
- Slow down when approaching limits

### 3.3 Create slower polling for stocks
- Stock updates every 2 minutes instead of 20 seconds
- Crypto stays at 20 seconds

## Phase 4: Strict Routing Enforcement (Priority: MEDIUM)
### 4.1 Enhance fetcher_router.py
- Strict namespace-based routing (fail if wrong provider)
- Log clearly when wrong provider is attempted

### 4.2 Add ghost price detection
- Validate fetched price against reasonable range
- Reject prices that are 10x different from last known

## Files to Edit:
1. data/fetcher.py - Add namespace functions
2. data/market_hours.py - Add is_market_open()
3. data/connector_registry.py - Update routing logic
4. engine/loop.py - Add market hours check
5. engine/signal_validator.py - Add validation

## Follow Up Steps:
1. Test the changes in dev environment
2. Check logs for ghost price errors
3. Verify market hours skip working
4. Monitor for Polygon 429 errors reduction
