# TODO: Fix All Issues Implementation - Remaining Steps

## Issues Status Summary:

### COMPLETED:
- Issue 1 & 7: audit_recent Import Error - FIXED (alias added to gemini_ml.py)

### REMAINING TO IMPLEMENT:

## Issue 2: Max Score Showing 100
**Location:** engine/core.py
**Status:** NEEDS FIX
**Action:** Calculate actual max_score from candidate dictionaries before/after threshold

## Issue 3: /signals Command Returns Empty  
**Location:** signalrank_telegram/commands.py
**Status:** NEEDS FIX
**Action:** Expand status filters to include 'issued', 'open' in addition to 'active'

## Issue 4: PostgreSQL "Too Many Clients" Errors  
**Location:** db/session.py
**Status:** ALREADY IMPLEMENTED (has pool_size=15, max_overflow=15)

## Issue 5: No Timeframe Data - All Assets
**Location:** data/providers.py
**Status:** NEEDS FIX
**Action:** Add clean_tf_and_symbol method

## Issue 6: Dynamic Threshold Not Working
**Location:** ml/dynamic_threshold.py  
**Status:** NEEDS FIX
**Action:** Fix return statement to return 'adjusted' not 'base'

## Issue 8: Command Recognition & Handler Configuration
**Location:** signalrank_telegram/bot.py
**Status:** NEEDS FIX
**Action:** Register all command handlers

## Additional Requested Updates:

### 1. Broker Map Update
**Location:** signalrank_telegram/commands.py
**Status:** NEEDS IMPLEMENT
**Action:** Add BROKER_MAP and resolve_broker_prefix function

### 2. Market Hours Verification Engine
**Location:** utils/market_hours.py (create new)
**Status:** NEEDS IMPLEMENT  
**Action:** Create is_market_session_open function

### 3. Broker Map - Already Integrated
**Location:** signalrank_telegram/commands.py (_chart_symbol_for_broker)
**Status:** ALREADY EXISTS
