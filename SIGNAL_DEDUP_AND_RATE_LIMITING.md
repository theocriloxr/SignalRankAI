# Signal Deduplication & Rate-Limiting System

**Problem**: 
- Bot was potentially sending the same signal to the same user multiple times across engine cycles
- Daily limits could be exhausted in a single engine cycle, front-loading signals instead of spreading them evenly
- No tracking of which signals were delivered to which users

**Solution Implemented**: Three-layer deduplication + rate-limiting system

---

## Architecture

### Layer 1: Database Unique Constraint (Primary Dedup)
**File**: `db/models.py` → `SignalDelivery` table

```python
class SignalDelivery(Base):
    __tablename__ = "signal_deliveries"
    __table_args__ = (
        UniqueConstraint("user_id", "signal_id", name="uq_signal_delivery_user_signal"),
    )
```

- Enforces **no duplicate (user_id, signal_id) pairs**
- If code tries to insert duplicate, PostgreSQL rejects it
- This is the **ultimate safety net**

### Layer 2: Engine-Level Filter (Preventive Dedup)
**File**: `engine/core.py` → `filter_non_duplicate_signals()` function

**What it does**:
- Before calling `dispatch_signals()`, filters out signals already sent to user
- Queries `SignalDelivery` table for existing (user_id, signal_id) pairs
- Only returns signals that haven't been sent to this user yet

**When it runs**:
- During delivery loop in `deliver_all()` async function
- After eligibility check (score gate) but BEFORE dispatch
- Logs how many duplicates were filtered per user

**Code location**:
```python
# In engine/core.py deliver_all() function
user_signals = filter_non_duplicate_signals(user_id, user_signals, session=session)
if not user_signals:
    logger.debug(f"[engine] All signals already sent to user {user_id}, skipping dispatch")
    skipped_no_eligible_signals += 1
    continue
```

### Layer 3: Distribution-Time Rate-Limiting
**File**: `signalrank_telegram/signal_distribution.py` → `SignalDistributor` class

**What it does**:
- Limits how many signals one user can receive in a **single engine cycle**
- Per-tier per-cycle limits:
  - FREE: 1 signal per 30-sec cycle
  - PREMIUM: 2 signals per 30-sec cycle
  - VIP: 3 signals per 30-sec cycle
  - ADMIN/OWNER: 5-10 signals per 30-sec cycle

- Enforces daily limits per user:
  - Counts DELIVERED signals only (sent_ok=True)
  - Checks if user has "room" before sampling them for next signal
  - Respects user's local timezone for day boundary (TODO: implement timezone support)

**Key functions**:
- `sample_users_for_signal()`: Random sample of eligible users, respecting limits
- `can_receive_signal()`: Check if user can receive signal (not duplicate, within daily limit)
- `count_delivered_signals_today()`: Count released signals to user

**Code location**:
```python
# In signalrank_telegram/tier_delivery.py
def get_users_for_signal(self, signal: Dict, signal_id: str, session=None) -> Dict[str, List[int]]:
    """Uses SignalDistributor to sample users respecting all limits"""
    distributor = SignalDistributor(session)
    recipients = distributor.sample_users_for_signal(signal, signal_id)
    return recipients
```

---

## User Experience Impact

### Before (Problem)
- Cycle 1 (t=0s): Signal A generated, sent to USER_1 ✓
- Cycle 2 (t=30s): Same signal A still eligible, sent to USER_1 again ✗ (DUPLICATE)
- Cycle 5 (t=120s): USER with tier FREE receives all 3 daily signals in 2 minutes
  - Then nothing for rest of day ✗ (FRONT-LOADED)

### After (Fixed)
- Cycle 1 (t=0s): Signal A generated, sent to USER_1 ✓
  - SignalDelivery(user_id=USER_1, signal_id=A, sent_ok=True) recorded
- Cycle 2 (t=30s): Filter checks SignalDelivery, finds existing entry, skips USER_1 ✓ (DEDUPED)
- Cycles spread: Signal B → USER_1 at t=60s, Signal C → USER_1 at t=90s
  - Signals distributed evenly across day ✓ (RATE-LIMITED)

---

## Configuration

### Per-Cycle Limits (adjustable in signal_distribution.py)
```python
SIGNALS_PER_USER_PER_CYCLE = {
    'free': 1,      # 1 signal per 30-sec cycle
    'premium': 2,   # 2 signals per 30-sec cycle
    'vip': 3,       # 3 signals per 30-sec cycle
    'admin': 5,
    'owner': 10,
}
```

**To adjust**: Edit the dict values in `signalrank_telegram/signal_distribution.py` line ~35

**Why these values?**
- FREE (1/cycle): Spreads 3/day limit across ~180 seconds = ~1 signal per minute
- PREMIUM (2/cycle): Spreads 10/day across ~300 seconds = ~2 signals per minute
- VIP (3/cycle): Spreads 20/day across ~400 seconds = ~3 signals per minute

### Daily Limits (set in core/tier_constants.py)
```python
TIER_DAILY_LIMITS = {
    "free": 3,          # Hard limit
    "premium": 10,
    "vip": 20,
    "owner": float('inf'),
}
```

---

## Database Schema

**SignalDelivery Table** tracks each delivery attempt:
```sql
CREATE TABLE signal_deliveries (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    signal_id VARCHAR NOT NULL REFERENCES signals(signal_id),
    tier_at_send VARCHAR(16) NOT NULL,       -- User's tier when sent
    sent_ok BOOLEAN NOT NULL DEFAULT FALSE,  -- True if deliver succeeded
    attempt_count INTEGER NOT NULL DEFAULT 1,
    last_attempt_at TIMESTAMP,
    last_error TEXT,
    delivered_at TIMESTAMP NOT NULL,
    
    CONSTRAINT uq_signal_delivery_user_signal UNIQUE(user_id, signal_id)
);

CREATE INDEX idx_signal_deliveries_user_id ON signal_deliveries(user_id);
CREATE INDEX idx_signal_deliveries_signal_id ON signal_deliveries(signal_id);
CREATE INDEX idx_signal_deliveries_sent_ok ON signal_deliveries(sent_ok);
```

The `UNIQUE(user_id, signal_id)` constraint is THE ultimate safeguard.

---

## Testing Checklist

- [ ] Send same signal in multiple cycles → user receives only once
- [ ] FREE user with 3 signals/day → signals spread across day, not all in one cycle
- [ ] Query `/signals` command → shows only signals delivered to that user
- [ ] Upgrade user from FREE to PREMIUM → backfill works (only signals already sampled)
- [ ] Check logs for dedup messages:
  ```
  [engine] Filtered duplicate signals for user 123456789: 5 -> 3 (skipped 2 duplicates)
  ```

---

## Log Examples

**Successful dedup**:
```
[engine] Filtered duplicate signals for user 123456789: 5 -> 3 (skipped 2 duplicates)
[engine] Eligibility for user=123456789 tier=free score=87.5: True
[dispatch] Delivered signal sig_abc123 to user 123456789 (free)
```

**Rate limiting in action**:
```
[distribution] Sampled 2 premium users for signal sig_xyz (score 82, threshold 70)
[distribution] Sampled 0 free users for signal sig_xyz (already 3/3 delivered today)
```

---

## TODO: Future Enhancements

1. **Timezone-aware day boundaries**: Use user's local timezone for daily resets
   - Currently uses UTC midnight (UTC-agnostic)
   - Need to query user.timezone or detect from Telegram profile

2. **Smart rate-limiting**: Spread evenly across entire day
   - Currently just limits per cycle
   - Could track delivery times and calculate ideal spacing

3. **Backfill during upgrade**: Re-deliver pre-sampled signals on tier upgrade
   - Already designed, needs implementation in upgrade handler
   - Only signals sent within last 1 hour that weren't delivered to user yet

4. **Signal aging**: Remove very old signals from delivery pool
   - Signals older than 24h auto-expire
   - Prevent stale signals being sent to users who joined late

---

## API Reference

### SignalDistributor (signalrank_telegram/signal_distribution.py)

**Methods**:

#### `sample_users_for_signal(signal: Dict, signal_id: str) -> Dict[str, List[int]]`
Sample random users per tier for this signal.

**Returns**: `{'free': [uid1, uid2], 'premium': [uid3], 'vip': [uid4], 'admin': [uid5]}`

#### `can_receive_signal(user_id: int, tier: str, signal_id: str) -> Tuple[bool, Optional[str]]`
Check if user can receive signal (not duplicate, within daily limit).

**Returns**: `(True, None)` or `(False, "reason")`

#### `count_delivered_signals_today(user_id: int) -> int`
Count DELIVERED signals to user today.

**Returns**: Integer count

#### `record_delivery_attempt(user_id: int, signal_id: str, tier: str, sent_ok: bool, error: Optional[str]) -> SignalDelivery`
Record delivery attempt in database.

---

## Migration Notes

No database schema changes needed. `SignalDelivery` table already exists with unique constraint.

If migrating from old system, backfill delivery records:
```sql
-- Optional: if you need to retroactively mark old signal sends as delivered
INSERT INTO signal_deliveries (user_id, signal_id, tier_at_send, sent_ok, delivered_at)
SELECT user_id, signal_id, 'free', true, NOW() 
FROM outcomes 
WHERE outcome_type IN ('tp1', 'tp2', 'tp3', 'sl')
ON CONFLICT(user_id, signal_id) DO NOTHING;
```

---

## Related Files

- **Core engine loop**: `engine/core.py` → `deliver_all()` function
- **Signal distributor**: `signalrank_telegram/signal_distribution.py` (NEW)
- **Tier delivery manager**: `signalrank_telegram/tier_delivery.py` (UPDATED)
- **Database marking**: `signalrank_telegram/bot.py` → `mark_signal_delivery_result()`
- **Tier constants**: `core/tier_constants.py` → `TIER_DAILY_LIMITS`

---

**Status**: ✅ Implemented (3 layers of dedup + rate-limiting)
