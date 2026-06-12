# SignalRankAI Starvation Fix V3 - Implementation Checklist

## Problem
Binance geo-blocked on Railway → CryptoCompare fallback → Insufficient data (< 20 candles) → 0 generated signals

## Root Cause
- Code in `data/market_data.py` has strict validation: `if len(df) < 20: return None`
- This threshold is too strict for degraded mode operation

## Solution Steps

### Step 1: Critical Fix - Lower Candle Threshold (CRITICAL)
- [x] Edit market_data.py: Change threshold from 20 to 5
- [x] Add forward-fill for missing data
- File: data/market_data.py

### Step 2: Create New Adapter Files
- [x] Create alphavantage_adapter.py
- [x] Create fcsapi_adapter.py  
- [x] Update connectors/__init__.py to export new adapters
- Path: data/connectors/

### Step 3: Update Connector Registry
- [x] Add new providers to get_providers_for_asset()
- [x] Add new providers to get_async_providers_for_asset()
- File: data/connector_registry.py

### Step 4: Update Fetcher Router
- [x] Add universal fallback chain for all asset classes
- File: data/fetcher_router.py

### Step 5: Environment Variables (Railway)
- Add to Railway dashboard:
  - DEGRADED_MODE_MIN_CANDLES=5
  - ALPHAVANTAGE_API_KEY=<key>
  - FCS_API_KEY=<key>

## Completion Status
Status: IN_PROGRESS
Last Updated: 2026-06-12
