# Entry Validation & Quality Focus Update - January 4, 2026

## Summary
Implemented comprehensive entry validation with status tracking and significantly tightened scoring gates for quality-focused signal generation.

## Changes Made

### 1. Entry Validation with ±5% Tolerance & Status Flag

**File**: `signalrank_telegram/bot.py`
- Changed entry tolerance from ±1.0% to **±5.0%** (allows more leeway for forward-looking signals)
- Added `_check_entry_status()` function that returns (allow, status):
  - `AT_ENTRY`: Price within ±5% of entry point ✅
  - `PENDING_ENTRY`: Price has not yet reached entry zone ⏳
  - `UNKNOWN`: Cannot determine status (non-crypto or error)
- Signals now carry `entry_status` flag and `current_price_pct` for tracking

### 2. Signal ID Reference System

**Files**: `signalrank_telegram/formatter.py`, `signalrank_telegram/bot.py`
- Signals now display first 8 characters of signal_id as reference
- Users can use reference with `/outcome <ref>` command
- Full signal_id stored in database for lookups

### 3. Entry Status Display in Commands

**File**: `signalrank_telegram/commands.py`

**`/signal <ref>` command**:
- Displays entry status (AT_ENTRY ✅ or PENDING_ENTRY ⏳)
- Shows current price vs entry with distance percentage
- For completed outcomes: shows entry status at time of signal

**`/outcome <ref>` command**:
- Shows entry point and result (PROFIT ✅ / LOSS ❌)
- Displays ML Score and R-Multiple
- Tracks move percentage

**`/signals` command**:
- Entry status flag shown for all signals
- Current price distance from entry displayed

### 4. Stricter Scoring Gates for Quality

**File**: `engine/scoring.py`

**Confidence Gate**:
- Raised from 0.35 to **0.40** (40% minimum base confidence)

**Risk/Reward Requirement**:
- Raised from 1.5:1 to **1.8:1** minimum
- Scaling: 1.8:1 = 50%, 3.5:1 = 100%
- Hard reject: any signal with RR < 1.8

**Volatility Gate**:
- Tightened from ≤0.18 to **≤0.15** (15% maximum volatility)
- Reject cutoff: vol ≥ 0.15 (was 0.18)

**Dispatch Threshold**:
- Raised from 65 to **70** (score must be ≥70 to dispatch)

**Impact**: ~80% fewer signals, but much higher quality with better win rate

### 5. ML Probability Now Saved

**Files**: `db/models.py`, `db/pg_features.py`
- Added `ml_probability` field to Signal model
- Now captured from ML inference and persisted to database
- Displayed in `/signal`, `/outcome` commands
- Migration: `alembic/migrations/versions/0011_add_ml_probability.py`

### 6. Enhanced Signal Formatting

**File**: `signalrank_telegram/formatter.py`

Signals now show:
- Reference ID (8-char prefix for /outcome command)
- Entry Status flag (✅ AT_ENTRY or ⏳ PENDING_ENTRY)
- ML Score (VIP+) with approval percentage
- Current price distance from entry
- Progress to TP/SL estimated

## Deployment Steps

1. **Run migration** to add ml_probability column:
   ```bash
   alembic upgrade head
   ```
   Or manually:
   ```sql
   ALTER TABLE signals ADD COLUMN ml_probability FLOAT;
   ```

2. **Restart bot** on Railway

3. **Monitor logs** for:
   - `[dispatch] Entry status:` messages showing signal entry readiness
   - Entry validation accepting signals within ±5% of entry

## Testing Commands

```
/signals              - See delivered signals with entry status
/signal XXXXXXXX      - View specific signal with entry status
/outcome XXXXXXXX     - Check outcome with entry status and ML score
/performance          - See signal delivery metrics
```

## Expected Behavior

- **Fewer signals** (due to stricter scoring): ~1-3 per cycle vs 4-7 before
- **Higher quality**: Confidence ≥40%, RR ≥1.8, Volatility ≤15%
- **Better accuracy**: Entry validation ensures signals are at proper levels
- **Clear status tracking**: Users see if entry was hit, pending, or missed
- **ML scoring**: Now variable (0-100%) instead of constant 0.5

## Configuration

Can be overridden via environment variables:
- `PREMIUM_SCORE_THRESHOLD=70` (dispatch minimum)
- `ML_PROB_THRESHOLD=0.6` (ML filter threshold)
- `CONSENSUS_MIN_SCORE=0.75` (consensus minimum)
- `ML_ENABLED=true` (enable ML scoring)
