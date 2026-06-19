# SignalRankAI Critical Fix Execution Plan

## Priority 1: Command System Fix (CRITICAL)

### Issue 1.1: Unknown Command Handler Shadowing
**Location**: bot.py ~line 4590

**Problem**: The generic `MessageHandler(filters.COMMAND)` catches ALL commands before specific CommandHandlers get a chance, causing "Unknown command" for commands that ARE registered.

**Root Cause**: 
- The MessageHandler(filters.COMMAND) pattern matches ANY text starting with "/"
- Even though it's registered after specific handlers, the combination of audit_handler wrapping and the pattern may cause issues
- Some commands may genuinely not be registered

**Fix**:
1. Replace the generic MessageHandler with a more selective approach
2. Add command verification with explicit check against registered commands
3. Ensure the handler only catches TRULY unknown commands

### Issue 1.2: Missing Handler Audit
**Problem**: No systematic verification that all commands in COMMAND_TIERS have actual handlers

**Fix**: Add automated audit at startup to log missing handlers

---

## Priority 2: Signal Lifecycle Fix (CRITICAL)

### Issue 2.1: Repetitive Signals
**Problem**: Signals like AVAXUSDT generate multiple times across timeframes

**Fix**:
1. Add signal family grouping (asset + direction + entry_zone)
2. Add multi-timeframe confirmation scoring
3. Implement dedupe policy: if 1D and 4H have same thesis, use only 1D

---

## Priority 3: Trade Tracking Fix (CRITICAL)

### Issue 3.1: Duplicate Trade Opening
**Problem**: Same signal with different signal_ids reopens trades

**Fix**:
1. Add market fingerprint: asset + direction + entry_zone + stop_structure
2. Check open trades before opening new ones

---

## Implementation Steps

### Step 1: Fix Unknown Command Handler
```python
# Replace the current handler with:
async def _handle_unknown_command(update, context):
    """Only handle truly unknown commands - not those with registered handlers."""
    if not update.message or not update.message.text:
        return
    
    # Get the command that was attempted
    command_text = update.message.text.strip().split()[0].lower()
    command = command_text.lstrip('/')
    
    # Check if it's a registered command from our registry
    from signalrank_telegram.command_access import COMMAND_TIERS
    if command in COMMAND_TIERS:
        # This command IS registered - the issue is handler order or other problem
        await update.message.reply_text(
            f"Command /{command} is available but not working correctly. "
            "Please contact support or try /help for available commands."
        )
        return
    
    # Truly unknown command
    await update.message.reply_text(
        f"Unknown command: /{command}\n\nSend /help for available commands."
    )
```

### Step 2: Add Startup Handler Audit
```python
# Add to run_bot() after handler registration
def _audit_handler_registration():
    """Verify all registered commands."""
    from signalrank_telegram.command_access import COMMAND_TIERS
    # ... audit logic
```

---

## Files to Modify

1. **signalrank_telegram/bot.py** (~4590)
   - Replace unknown command handler
   - Add startup audit

2. **signalrank_telegram/command_access.py**
   - Verify all commands have handlers

3. **engine/signal_lifecycle.py** (new or existing)
   - Add signal family grouping
   - Add multi-timeframe confirmation

4. **core/trade_tracker.py**
   - Add market fingerprint

---

## Verification Commands

After fix, test:
- `/mode` - Should work
- `/connect_broker` - Should work  
- `/help` - Should show all commands
- `/unknown` - Should show "Unknown command"
