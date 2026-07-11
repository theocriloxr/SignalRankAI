# TODO: Institutional Grade Trading System Upgrades

## Overview
Implementing advanced institutional trading features: Derivatives Microstructure (Squeeze Detector), Flash Crash Circuit Breaker, Dynamic ATR-Based Targeting, and MFE/MAE Analytics.

## Implementation Steps

### Step 1: Create Derivatives Squeeze Detector
- **File**: `engine/derivatives.py`
- **Purpose**: Fetch Binance USD-M Futures Funding Rates to detect "Long Squeeze" or "Short Squeeze" conditions
- **Implementation**:
  - Class `SqueezeDetector` with async method `get_squeeze_bias(asset: str) -> str`
  - Returns: 'BULLISH', 'BEARISH', or 'NEUTRAL'
  - Uses Binance Futures API: `https://fapi.binance.com/fapi/v1/premiumIndex`
- **Status**: TODO

### Step 2: Create Market Circuit Breaker
- **File**: `engine/market_circuit_breaker.py`
- **Purpose**: Monitor BTC for flash crash detection, halt trading when BTC drops significantly
- **Implementation**:
  - Class `MarketCircuitBreaker` with async method `check_market_health() -> bool`
  - Monitors BTC price change over configurable period (default -4% in 1 hour)
  - Halts engine for 4 hours when triggered
- **Status**: TODO

### Step 3: Create Analytics Module (MFE/MAE)
- **File**: `engine/analytics.py`
- **Purpose**: Calculate Maximum Favorable Excursion (MFE) and Maximum Adverse Excursion (MAE) for trades
- **Implementation**:
  - Class `ExcursionCalculator` with static method `calculate_mfe_mae(entry_price, direction, price_history_df)`
  - Returns: dict with 'mfe_pct' and 'mae_pct'
- **Status**: TODO

### Step 4: Update Database Models
- **File**: `db/models.py`
- **Changes**: Add `mfe_pct` and `mae_pct` columns to `Trade` model
- **Status**: TODO

### Step 5: Integrate Squeeze Detector into Core
- **File**: `engine/core.py`
- **Integration Point**: After strategy signals generated, before ML filter
- **Logic**: 
  - If signal_direction == "LONG" and bias == "BEARISH" -> skip trade
  - If signal_direction == "SHORT" and bias == "BULLISH" -> skip trade
- **Status**: TODO

### Step 6: Integrate Circuit Breaker at Top of Loop
- **File**: `engine/core.py`
- **Integration Point**: Start of main_loop before asset processing
- **Logic**: Check BTC health, if unhealthy skip entire cycle
- **Status**: TODO

### Step 7: Enhance ATR-Based TP/SL with Multi-Level Targets
- **File**: `engine/core.py`
- **Enhancement**: Add TP1, TP2, TP3 based on ATR multiples
  - TP1: entry + 1.0 × ATR
  - TP2: entry + 2.0 × ATR  
  - TP3: entry + 3.5 × ATR
- **Status**: TODO (partially done, needs enhancement)

## Dependencies
- `aiohttp` - Already in requirements.txt
- `pandas` - Already in requirements.txt

## Testing
After implementation, test each module independently before integrating into core loop.

## Notes
- All new modules should have proper logging
- Circuit breaker should fail-open (allow trading) when API fails
- Squeeze detector should fail-neutral (allow trading) when API fails
- MFE/MAE tracking requires historical price data fetcher
