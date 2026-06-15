# TODO: Fix All Issues

## Issues to Fix

### Issue 1: audit_recent Import Error
- Location: `signalrank_telegram/commands.py` - gemini_audit_command
- Problem: Cannot import 'audit_recent' from 'services.gemini_ml'
- Fix: Verify the function is correctly exported in gemini_ml.py and fix the import in commands.py

### Issue 2: Max Score Showing 100
- Location: Engine scoring logic
- Problem: max_score=100.0 showing consistently, not calculating real scores
- Fix: Review scoring algorithm in engine/core.py

### Issue 3: /signals Command Returns Empty
- Location: signals_command in commands.py
- Problem: "No active unresolved signals in your range right now"
- Fix: Debug database query and filtering logic

### Issue 4: PostgreSQL "Too Many Clients" Errors
- Location: DB Configuration
- Problem: asyncpg connection pool exhausted
- Fix: Review connection pool settings and ensure proper cleanup

### Issue 5: No Timeframe Data - All Assets
- Location: Data providers
- Problem: "No timeframe data for [ALL ASSETS]"
- Fix: Check provider initialization and data fetching

### Issue 6: Dynamic Threshold Not Working
- Location: ml/dynamic_threshold.py
- Problem: ML threshold not adjusting based on AUC
- Fix: Verify dynamic threshold logic

### Issue 7: /gemini_audit Command Failing
- Location: gemini_audit_command
- Problem: Import error (same as Issue 1)
- Fix: Ensure audit_recent is properly exported

## Additional Updates Requested

### Broker Map Update
- Add all used brokers to commands.py broker_map
- Include: BINANCE, BYBIT, COINBASE, KRAKEN, BITSTAMP, OANDA, FXCM, FOREXCOM, TVC, NASDAQ, NYSE

### Asset Class Coverage
- FX: All major and minor pairs based on market hours
- Crypto: All tradeable crypto assets
- Commodities: XAUUSD, XAGUSD, WTI, BRENT, natural gas, etc.
- Indices: US30, US500, SPX, DJI, VIX, etc.
- Stocks/Equities: Major stock symbols

### Market Hours Support
- FX market hours (Sydney, Tokyo, London, New York sessions)
- Crypto market hours (24/7)
- Commodity market hours
- Stock market hours (exchange-specific)
- Index market hours

## Implementation Plan

1. Fix audit_recent import and gemini_audit_command
2. Fix max_score 100.0 issue
3. Fix /signals command query
4. Fix PostgreSQL connection handling
5. Fix data provider issues
6. Fix dynamic threshold
7. Update broker_map with all brokers
8. Update asset coverage for all asset classes
9. Add market hours logic

## Status: IN PROGRESS
