# SignalRankAI Fixes TODO

## Issue 1: SyntaxError in engine/core.py (line ~161)
- **Problem**: Extra `)` at `_threshold_optimizer = _FallbackThresholdOptimizer())`
- **Fix**: Remove the extra closing parenthesis

## Issue 2: Candle Data Normalization Across Providers
- **Problem**: Different providers return candles in different formats
- **Fix**: Add a normalization function in fetcher.py or indicators.py

## Issue 3: Skip Signal Generation When All Providers Fail
- **Problem**: Assets like USDTIDR, BTCIDR, etc. generate signals even with no data
- **Fix**: Skip signal generation when no valid market data is available

## Issue 4: Market Hours Check During Signal Generation
- **Problem**: Signals generated for assets when market is closed
- **Fix**: Add explicit market hours check in the pipeline

## Status
- [x] Syntax Error Fix
- [ ] Provider Data Normalization
- [ ] Skip Signals When No Data
- [ ] Market Hours Check
