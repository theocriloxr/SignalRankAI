# SignalRankAI Command & Signal Status Fix Plan

## Executive Summary

Based on analysis of the codebase, the following critical issues were identified:

1. **Root cause of "No active unresolved signals"**: Signal queries filter by `sent_ok.is_(True)` but signals exist without this flag being set
2. **Signal status mismatch**: Engine stores signals with `issued`, `active`, `open`, `pending` but queries only check `active`
3. **Missing startup command audit**: No logging to verify all commands are properly registered
4. **No /diag command**: Missing health verification command
5. **No delivery-stage telemetry**: Can't track where signals die in the pipeline
6. **AUDUSD pricing bug**: No price sanity check (0.60-0.85 range)

## Phase 1: Signal Status Fix (Highest Priority)

### Issue
The `/signals` command shows "No active unresolved signals" even when trades exist because:
- Query in `pg_features.py` filters by `sent_ok.is_(True)` 
- But delivery may fail (network error) while signal exists
- Status mismatch: stored as `issued`/`open` but query looks for `active`

### Implementation
Create a shared status definition in `signalrank_telegram/signal_commands.py`:

```python
# Active signal statuses that should be displayed
ACTIVE_SIGNAL_STATUSES = {"issued", "open", "active", "pending"}
```

Update queries in:
- `signalrank_telegram/signal_commands.py` - `/signals` command
- `db/pg_features.py` - `list_unresolved_signals_for_user()`, `list_active_signals()`

## Phase 2: Startup Command Audit

### Implementation
Add startup audit in `signalrank_telegram/bot.py`:

```python
# At startup, after command registration:
def _audit_commands():
    expected = set(COMMAND_TIERS.keys())
    # Extract registered from application.handlers
    registered = _extract_registered_commands()
    
    missing = expected - registered
    extra = registered - expected
    
    logger.info(f"[command_audit] Registered: {len(registered)}")
    logger.info(f"[command_audit] Expected: {len(expected)}")
    
    if missing:
        logger.warning(f"[command_audit] MISSING HANDLERS: {missing}")
    if extra:
        logger.info(f"[command_audit] EXTRA HANDLERS: {extra}")
```

## Phase 3: /diag Command

### Implementation
Add to `signalrank_telegram/commands.py`:

```python
async def diag_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """System diagnostic command (admin only)."""
    # Check:
    # - Database connection
    # - Redis connection
    # - Data provider health
    # - Command registration status
    # - Recent signal generation status
    # - Delivery pipeline status
```

## Phase 4: Delivery Stage Telemetry

### Implementation
Add delivery_stage field tracking in Signal/SignalDelivery models.
Update signal distribution to track stages:

```python
DELIVERY_STAGES = {
    "GENERATED": "Signal created in engine",
    "STORED": "Signal saved to DB",
    "QUEUED": "Signal queued for delivery",
    "TIER_PASSED": "Signal passed tier gate",
    "TELEGRAM_SENT": "Signal sent to Telegram API",
    "DELIVERED": "User received signal"
}
```

## Phase 5: Price Sanity Check (AUDUSD Bug)

### Implementation
Enhance `validate_price_sanity()` in `data/fetcher.py`:

```python
def validate_price_sanity(asset: str, price: float, lastKnownPrice: float | None = None) -> bool:
    # Add AUDUSD-specific range check
    if asset.upper() == "AUDUSD":
        if not (0.60 <= price <= 0.85):
            logger.warning(f"[price_validator] AUDUSD out of range: {price}")
            return False
```

## Phase 6: Threshold Persistence

### Implementation
Save dynamic thresholds to Redis/DB instead of recalculating each cycle.

Add to `core/redis_state.py` or create new table `runtime_state`:

```python
# Key: "dynamic_threshold:score"
# Value: {"value": 75.0, "updated_at": "2024-01-01T00:00:00Z"}
```

## Files to Edit

1. `signalrank_telegram/signal_commands.py` - Fix signal queries
2. `signalrank_telegram/bot.py` - Add startup audit
3. `signalrank_telegram/commands.py` - Add /diag command
4. `signalrank_telegram/command_access.py` - Add diag to COMMAND_TIERS
5. `db/pg_features.py` - Fix list_active_signals query
6. `data/fetcher.py` - Add AUDUSD price sanity

## Verification Steps

After implementing:

1. Restart bot and check startup logs for `[command_audit]`
2. Run `/diag` and verify all subsystems report OK
3. Generate a test signal and verify `/signals` shows it
4. Check delivery telemetry in DB

## Confidence Assessment After Fix

| Item | Before | After |
|------|--------|-------|
| Core commands registered | High | High |
| All /help commands registered | Low | High |
| /signals logic correct | Low | High |
| Delivery visibility | Medium-Low | High |
| Command audit | None | High |

## Implementation Order

1. Add ACTIVE_SIGNAL_STATUSES constant
2. Fix /signals command query
3. Add startup command audit
4. Add /diag command
5. Add AUDUSD price sanity
6. Add delivery telemetry (optional enhancement)
7. Test and verify
