# Signal Correction System

## Overview
SignalRankAI includes an automated signal validation and correction system to detect erroneous signals before they reach users, and notify users when corrections are needed.

## Features

### 1. Automated Signal Validation

Every signal is validated before storage:

**Validation Checks:**
- ✅ Required fields present (asset, direction, entry, SL, TP)
- ✅ Valid direction (long/short)
- ✅ Positive price levels
- ✅ Correct price relationships:
  - LONG: SL < Entry < TP
  - SHORT: SL > Entry > TP
- ✅ Minimum RR ratio (>= 0.5)
- ✅ SL width check (<20% crypto, <10% stocks)

**Example Validation:**
```python
# INVALID: Entry below SL for LONG
{
    "asset": "BTCUSDT",
    "direction": "long",
    "entry": 42000,
    "stop_loss": 43000,  # ❌ SL above entry
    "take_profit": 45000
}
# Rejected: "LONG: Entry (42000) must be above SL (43000)"

# VALID: Proper LONG setup
{
    "asset": "BTCUSDT",
    "direction": "long",
    "entry": 42000,
    "stop_loss": 41000,  # ✅ SL below entry
    "take_profit": 44000  # ✅ TP above entry
}
```

### 2. Signal Correction Tracking

Database table `signal_corrections`:

| Field | Type | Description |
|-------|------|-------------|
| original_signal_id | String | Signal that was incorrect |
| corrected_signal_id | String | Replacement signal (optional) |
| error_type | String | Type of error (invalid_entry, data_error, etc.) |
| error_description | Text | Human-readable error description |
| users_notified | Integer | Count of users notified |
| correction_sent_at | DateTime | When correction was sent |

### 3. User Notification

When a signal is corrected, all users who received it get a notification:

**Example Correction Message:**
```
⚠️ SIGNAL CORRECTION

Reference: abc12345

Issue: Invalid entry level due to data error

❌ This signal has been invalidated.
Do not trade this signal. We apologize for the error.
```

**With Replacement Signal:**
```
⚠️ SIGNAL CORRECTION

Reference: abc12345

Issue: Stop loss level recalculated

✅ Corrected signal sent: def67890
Please use /signal command to view the corrected signal.
```

## Manual Correction

### Owner Command: `/correct_signal`

**Usage:**
```bash
/correct_signal <signal_ref> <error_description>
```

**Example:**
```bash
/correct_signal abc123 Invalid entry level due to data fetch error
```

**Process:**
1. Finds signal by reference (full or partial)
2. Counts users who received the signal
3. Creates correction record in database
4. Sends notification to all recipients
5. Reports completion status

**Owner Response:**
```
✅ Signal correction complete:
• Signal: abc12345
• Error: Invalid entry level due to data fetch error
• Users notified: 7/7
```

### Automated Correction

Signals failing validation are automatically rejected:

**Log Output:**
```bash
[VALIDATION FAILED] BTCUSDT 1h: LONG: Entry (42000) must be above SL (43000)
```

**Cycle Stats:**
```bash
[engine] cycle=5 candidates=64 scored=17 stored=14 rejected_validation=3
```

## Error Types

Common error types tracked:

1. **invalid_entry**: Entry level violates price relationship rules
2. **invalid_sl**: Stop loss too wide or in wrong direction
3. **invalid_tp**: Take profit below entry (LONG) or above entry (SHORT)
4. **poor_rr**: Risk/reward ratio below minimum threshold
5. **data_error**: Data fetch or calculation error
6. **calc_error**: Indicator calculation error
7. **manual_correction**: Owner-initiated correction

## Database Schema

```sql
CREATE TABLE signal_corrections (
    id SERIAL PRIMARY KEY,
    original_signal_id VARCHAR(36) REFERENCES signals(signal_id),
    corrected_signal_id VARCHAR(36) REFERENCES signals(signal_id),
    error_type VARCHAR(64) NOT NULL,
    error_description TEXT NOT NULL,
    users_notified INTEGER DEFAULT 0,
    correction_sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    meta JSONB DEFAULT '{}'
);

CREATE INDEX idx_signal_corrections_original ON signal_corrections(original_signal_id);
CREATE INDEX idx_signal_corrections_corrected ON signal_corrections(corrected_signal_id);
CREATE INDEX idx_signal_corrections_error_type ON signal_corrections(error_type);
```

## Configuration

### Enable Validation Debug Logging

```bash
ENGINE_SIGNAL_DEBUG=true  # Shows validation failures in logs
```

### Validation Thresholds

```python
# engine/signal_validator.py
MIN_RR_RATIO = 0.5  # Minimum risk/reward
MAX_SL_CRYPTO = 20.0  # Max SL width for crypto (%)
MAX_SL_STOCK = 10.0  # Max SL width for stocks (%)
```

## Workflow

### Signal Generation → Validation → Storage

```
1. Strategy generates signal
   ↓
2. Scoring (base + ML)
   ↓
3. VALIDATION ← New step
   ├─ VALID → Store signal
   └─ INVALID → Reject (log error)
   ↓
4. Dispatch to users
```

### Manual Correction Flow

```
1. Owner notices error
   ↓
2. /correct_signal <ref> <reason>
   ↓
3. System finds signal
   ↓
4. Creates correction record
   ↓
5. Notifies all recipients
   ↓
6. Confirmation to owner
```

## Statistics

Track correction rates in database:

```sql
-- Total corrections
SELECT COUNT(*) FROM signal_corrections;

-- Corrections by error type
SELECT error_type, COUNT(*) 
FROM signal_corrections 
GROUP BY error_type 
ORDER BY COUNT(*) DESC;

-- Recent corrections
SELECT 
    original_signal_id,
    error_type,
    error_description,
    users_notified,
    created_at
FROM signal_corrections
ORDER BY created_at DESC
LIMIT 10;
```

## Best Practices

1. **Always validate before storing**: Prevents bad signals from reaching users
2. **Log validation failures**: Helps identify data/indicator issues
3. **Prompt correction**: Notify users within minutes of discovering error
4. **Clear descriptions**: Error descriptions should be actionable
5. **Monitor correction rate**: High rate indicates upstream issues

## Migration

Run migration to add signal_corrections table:

```bash
# Migrations run automatically on Railway deployment
# Or manually:
alembic upgrade head
```

## Testing

### Test Validation

```python
from engine.signal_validator import validate_signal

# Test invalid LONG
signal = {
    "asset": "BTCUSDT",
    "direction": "long",
    "entry": 42000,
    "stop_loss": 43000,  # Wrong: SL above entry
    "take_profit": 45000
}

is_valid, error = validate_signal(signal)
print(is_valid)  # False
print(error)  # "LONG: Entry (42000) must be above SL (43000)"
```

### Test Manual Correction

```bash
# As owner in Telegram
/correct_signal abc123 Test correction for validation
```

## Monitoring

### Check Validation Failures

```bash
# Railway logs
railway logs --service signalrank-ai | grep "VALIDATION FAILED"
```

### Check Correction History

```sql
-- PostgreSQL
SELECT * FROM signal_corrections ORDER BY created_at DESC LIMIT 5;
```

## Support

Signal correction system is fully integrated:
- ✅ Automated validation before storage
- ✅ Manual correction via owner command
- ✅ User notification for all corrections
- ✅ Database tracking of all corrections
- ✅ Clear error descriptions and types

No additional configuration needed - works out of the box!
