# TODO Fix List

## Priority 1: Database Pool Exhaustion Fix (CRITICAL)

### Issue: TooManyConnectionsError
The logs show:
```
[db] async engine initialised ... pool_size=3 max_overflow=5
asyncpg.exceptions.TooManyConnectionsError: sorry, too many clients already
```

The root cause: Railway's PostgreSQL tier has a very low connection limit (usually ~20). With multiple background loops (ML train loop, News Filter, Gemini CRO, Shadow Tracker, etc.), each opening its own connections, we hit the ceiling quickly.

### Fix Steps:
1. [ ] Modify db/session.py to lower pool_size to 2
2. [ ] Modify db/session.py to set max_overflow to 0
3. [ ] Lower DB_POOL_SIZE_RAILWAY and DB_MAX_OVERFLOW_RAILWAY values

## Priority 2: Missing google-generativeai Library

### Issue: Gemini Validator Not Running
The logs show:
```
WARNING GeminiValidator: [GeminiValidator] google-generativeai not installed - will use fallback
```

The cause: The google-generativeai library is missing from requirements.txt.

### Fix Steps:
1. [ ] Add google-generativeai to requirements.txt

## Priority 3: Binance Regional Restriction (INFO ONLY)

### Issue: Binance pairs disabled
```
WARNING data.pair_discovery: Binance pairs disabled: Service unavailable from a restricted location
```

This is due to Railway's IP being in a restricted region. The system already uses CryptoCompare as a fallback, so this is informational only - no fix needed.

## Summary of Fixes Required

### File 1: db/session.py
- Change pool_size from 3 to 2
- Change max_overflow from 5 to 0
- Change DB_POOL_SIZE_RAILWAY from 3 to 2
- Change DB_MAX_OVERFLOW_RAILWAY from 5 to 0

### File 2: requirements.txt  
- Add google-generativeai>=0.1.0

## Verification After Fix
- [ ] Check logs for "too many clients" errors are gone
- [ ] Verify Gemini CRO is using actual google-generativeai library (not fallback)
- [ ] Restart Railway deployment to clear connection states
