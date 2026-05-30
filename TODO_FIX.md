# SignalRankAI Fixes TODO
Status: Complete.

## Issue 1: SyntaxError in engine/core.py (line ~161)
- [x] **Problem**: Extra `)` at `_threshold_optimizer = _FallbackThresholdOptimizer())`
- [x] **Fix**: Remove the extra closing parenthesis

## Issue 2: Candle Data Normalization Across Providers
- [x] **Problem**: Different providers return candles in different formats
- [x] **Fix**: Add a normalization function in fetcher.py or indicators.py

## Issue 3: Skip Signal Generation When All Providers Fail
- [x] **Problem**: Assets like USDTIDR, BTCIDR, etc. generate signals even with no data
- [x] **Fix**: Skip signal generation when no valid market data is available

## Issue 4: Market Hours Check During Signal Generation
- [x] **Problem**: Signals generated for assets when market is closed
- [x] **Fix**: Add explicit market hours check in the pipeline

## Status
- [x] Syntax Error Fix
- [x] Provider Data Normalization
- [x] Skip Signals When No Data
- [x] Market Hours Check
