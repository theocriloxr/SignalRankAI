# 📊 TIER SYSTEM - CODE ARCHITECTURE

**Overview of all tier system components and their relationships**

---

## 🏗️ File Structure

```
signalrank/
├── signalrank_telegram/
│   ├── formatter.py                    [MODIFIED - Enhanced]
│   ├── tier_delivery.py                [NEW - Delivery Manager]
│   ├── commands.py                     [TO UPDATE - Add tier routing]
│   └── bot.py                          [TO UPDATE - Pass user_tier]
│
├── db/
│   ├── models.py                       [TO VERIFY - User.tier field]
│   └── repository.py                   [TO UPDATE - Tier queries]
│
├── core/
│   ├── signal_governor.py              [TO UPDATE - Dispatch with tier]
│   └── trade_tracker.py                [TO UPDATE - TP tracking]
│
├── test_tier_formatter.py              [NEW - Test Suite ✅]
├── TIER_SYSTEM_IMPLEMENTATION.md       [NEW - Documentation]
├── TIER_INTEGRATION_GUIDE.md           [NEW - Integration Guide]
└── TIER_SYSTEM_COMPLETE.md             [NEW - Completion Summary]
```

---

## 🔄 Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ Engine generates signal (asset, entry, tp, score, confidence)   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │ TierDeliveryMgr│
                    └────────┬───────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
      ┌─────────┐      ┌─────────┐      ┌──────────┐
      │  ADMIN  │      │   VIP   │      │ PREMIUM  │
      │ Tier    │      │  Tier   │      │  Tier    │
      └────┬────┘      └────┬────┘      └────┬─────┘
           │                │                │
           └────────────────┼────────────────┤
                            │                │
                       ┌─────┴────┐          │
                       │           │          │
                    No ▼           ▼ Yes   No ▼
              ┌─────────────────────┐     ┌──────┐
              │ Score ≥ 65? ✅/❌  │     │ FREE │
              └─────────────────────┘     │ Tier │
                       │                  └──────┘
                       ▼
              Check: Score ≥ 55? ✅/❌
                       │
        ┌──────────────┼──────────────┐
        │              │              │
       YES            NO             │
        ▼              ▼              │
    ┌─────┐       FILTER OUT         │
    │ VIP │                          │
    └─────┘                          │
                                     ▼
                            Only ADMIN sees it

Format signal → Send via Telegram → Log delivery
```

---

## 📦 Core Components

### 1. Tier Constants (formatter.py)

```python
TIER_FREE = 'free'       # Proof only
TIER_PREMIUM = 'premium'  # More signals, more details
TIER_VIP = 'vip'         # Best quality, all features
TIER_ADMIN = 'admin'     # All signals, admin info
TIER_OWNER = 'owner'     # Alias for admin
```

### 2. Quality Gate Functions (formatter.py)

```python
def _get_user_tier(tier):
    """Normalize tier name to standard form."""
    # Handles 'free', 'premium', 'vip', 'admin', 'owner'
    # Returns normalized tier string

def _should_send_signal_for_tier(tier, score):
    """Check if signal should be sent to tier based on score."""
    # FREE: score ≥ 80.0
    # PREMIUM: score ≥ 65.0
    # VIP: score ≥ 55.0
    # ADMIN: score ≥ 0.0 (always True)
    # Returns: Boolean
```

### 3. Tier-Specific Formatters (formatter.py)

```python
def format_signal_free(signal):
    """Format for FREE tier (proof only)."""
    # Returns: Asset | Timeframe | Entry | SL | 1 TP | Risk warning
    # Type: Minimal, trust-building

def format_signal_premium(signal):
    """Format for PREMIUM tier (medium details)."""
    # Returns: + Session | Multi-TP | Confidence % | Validity | Updates
    # Type: Revenue tier, active traders

def format_signal_vip(signal):
    """Format for VIP tier (full details)."""
    # Returns: + Market Regime | HTF Bias | R/R | Invalidation | Strategy
    # Type: Premium experience, institutional-style

def format_signal_admin(signal):
    """Format for ADMIN tier (admin info)."""
    # Returns: VIP format + Admin metadata
    # Type: Full visibility for operations
```

### 4. Alert Formatters (formatter.py)

```python
def format_signal_update_tp_hit(signal, tp_number):
    """TP HIT alert (PREMIUM+)."""
    # Sent when take profit is hit

def format_signal_no_trade_alert():
    """NO-TRADE alert (VIP only)."""
    # Sent when market too choppy to trade

def format_performance_summary_vip(stats):
    """Weekly performance summary (VIP)."""
    # Sent every Sunday with week's stats
```

### 5. Main Router (formatter.py)

```python
def format_signal(signal, user_tier=None, limited=False, ...):
    """Main entry point - routes to appropriate tier formatter."""
    
    # Normalize tier
    tier = _get_user_tier(user_tier)
    
    # Check quality gate
    if not _should_send_signal_for_tier(tier, signal['score']):
        return None  # Signal filtered
    
    # Route to tier formatter
    if tier == 'free':
        return format_signal_free(signal)
    elif tier == 'premium':
        return format_signal_premium(signal)
    elif tier == 'vip':
        return format_signal_vip(signal)
    elif tier == 'admin':
        return format_signal_admin(signal)
    
    return None
```

### 6. TierDeliveryManager (tier_delivery.py)

```python
class TierDeliveryManager:
    """Manages tier-based signal delivery, routing, and logging."""
    
    # Quality thresholds
    MIN_SCORE_FREE = 80.0
    MIN_SCORE_PREMIUM = 65.0
    MIN_SCORE_VIP = 55.0
    
    # Daily limits (soft)
    MAX_SIGNALS_PER_DAY = {
        'free': 3,
        'premium': 10,
        'vip': None,      # No limit
        'admin': None      # No limit
    }
    
    def should_send_signal(self, user_tier, score, user_id=None):
        """Check if signal should be sent to user."""
        # Quality gate + daily limit check
        # Returns: Boolean
    
    def format_for_delivery(self, signal, user_tier):
        """Format signal + apply gates."""
        # Calls format_signal() with tier routing
        # Returns: Formatted message or None if filtered
    
    def get_users_for_signal(self, signal):
        """Get list of users who should receive signal."""
        # Query database for users by tier
        # Apply filtering
        # Returns: List of user objects
    
    def create_update_alert(self, signal, tp_number, user_tier):
        """Create TP HIT alert (PREMIUM+)."""
        # Returns: Formatted update message
    
    def create_no_trade_alert(self, user_tier):
        """Create NO-TRADE alert (VIP only)."""
        # Returns: Formatted alert or None
    
    def get_tier_features(self, tier):
        """Get feature matrix for tier."""
        # Returns: Dict of features and their availability
    
    def log_delivery(self, signal_id, user_id, tier, delivered, reason=''):
        """Log delivery attempt."""
        # Records: signal_id, user_id, tier, success, reason
    
    def get_delivery_stats(self, days=7):
        """Get delivery statistics."""
        # Returns: Stats by tier, filter reasons, success rates
```

### 7. Global Access

```python
def get_delivery_manager():
    """Get global delivery manager instance."""
    # Singleton pattern
    # Used by all dispatch code
```

---

## 🔌 Integration Points

### Current State (Before Integration)
```python
# OLD: No tier awareness
def dispatch_signal(signal):
    msg = format_signal(signal)  # Single format
    send_to_all_users(msg)        # Everyone gets same message
```

### After Integration
```python
# NEW: Tier-aware dispatch
async def dispatch_signal(signal):
    manager = get_delivery_manager()
    
    for user in db.get_all_users():
        # Quality gate check
        if not manager.should_send_signal(user.tier, signal['score']):
            continue  # Skip this user
        
        # Format for user's tier
        msg = manager.format_for_delivery(signal, user.tier)
        
        if msg:
            # Send to user
            await send_telegram_message(user.chat_id, msg)
            
            # Log delivery
            manager.log_delivery(
                signal['signal_id'],
                user.id,
                user.tier,
                True
            )
```

---

## 📊 Tier Routing Decision Tree

```
Signal generated with score X
    │
    ├─ Is user ADMIN?
    │  └─ YES → format_signal_admin()
    │
    ├─ Is score ≥ 55?
    │  ├─ NO → FILTER OUT (only ADMIN sees it)
    │  └─ YES → Check further
    │
    ├─ Is score ≥ 65?
    │  ├─ NO → format_signal_vip() if tier=VIP
    │  └─ YES → Check further
    │
    ├─ Is score ≥ 80?
    │  ├─ NO → format_signal_premium() if tier=PREMIUM
    │  └─ YES → format_signal_free() if tier=FREE
    │
    └─ Route to appropriate formatter
       └─ Return formatted message
```

---

## 🧪 Test Coverage

### [test_tier_formatter.py](test_tier_formatter.py) - ALL PASSING ✅

```
Test 1: FREE tier formatting
  ✅ Minimal format (proof only)
  ✅ Score filtering (80+ required)

Test 2: PREMIUM tier formatting
  ✅ Medium format (more details)
  ✅ Score filtering (65+ required)

Test 3: VIP tier formatting
  ✅ Full format (all features)
  ✅ Score filtering (55+ required)

Test 4: ADMIN tier formatting
  ✅ Admin format (+ admin info)
  ✅ No score filtering

Test 5: Tier filtering logic
  ✅ Score 85 → All tiers ✅
  ✅ Score 72 → PREMIUM, VIP ✅
  ✅ Score 60 → VIP only ✅
  ✅ Score 50 → ADMIN only ✅

Test 6: Update alerts
  ✅ TP HIT update formats correctly
  ✅ Filters to PREMIUM+ only

Test 7: No-trade alerts
  ✅ NO-TRADE alert formats correctly
  ✅ VIP only

Result: ALL TESTS PASSED ✅
```

---

## 📝 Code Examples

### Example 1: Simple Signal Send

```python
from signalrank_telegram.formatter import format_signal

signal = {
    'asset': 'BTCUSDT',
    'timeframe': '15m',
    'signal': 'buy',
    'entry': 41250,
    'stop_loss': 40980,
    'tp1': 41700,
    'score': 82.0,
}

# For each user
for user in get_all_users():
    # Format for their tier
    msg = format_signal(signal, user_tier=user.tier)
    
    if msg:
        # Send only if not filtered
        await send_telegram(user.chat_id, msg)
```

### Example 2: With Quality Gate

```python
from signalrank_telegram.tier_delivery import get_delivery_manager

manager = get_delivery_manager()

# Check before formatting
if manager.should_send_signal(user.tier, signal['score']):
    msg = manager.format_for_delivery(signal, user.tier)
    await send_telegram(user.chat_id, msg)
else:
    # Signal filtered for this user
    pass
```

### Example 3: Batch Dispatch

```python
async def broadcast_signal(signal):
    manager = get_delivery_manager()
    
    for user in db.get_all_users():
        if manager.should_send_signal(user.tier, signal['score']):
            msg = manager.format_for_delivery(signal, user.tier)
            if msg:
                await send_telegram(user.chat_id, msg)
                manager.log_delivery(signal['id'], user.id, user.tier, True)
```

---

## 🔐 Data Flow Security

### Tier Validation
```
Input: user.tier (from database)
  ↓
_get_user_tier() normalizes it
  ↓
Check if in [free, premium, vip, admin]
  ↓
Return or default to 'free'
```

### Score Validation
```
Input: signal.score (from engine)
  ↓
_should_send_signal_for_tier() checks threshold
  ↓
Tier='free' → requires ≥ 80.0
Tier='premium' → requires ≥ 65.0
Tier='vip' → requires ≥ 55.0
Tier='admin' → always ≥ 0.0
  ↓
Return True/False
```

---

## 📈 Logging Architecture

```
TierDeliveryManager.log_delivery()
  ├─ Signal ID
  ├─ User ID
  ├─ Tier
  ├─ Delivered (Boolean)
  ├─ Reason (if not delivered)
  └─ Timestamp
       │
       ↓
   Store in delivery_log table
       │
       ↓
   Used by get_delivery_stats()
       │
       ├─ Total by tier
       ├─ Success rate by tier
       ├─ Filter reasons
       └─ Daily totals
```

---

## 🎯 Feature Matrix Implementation

| Feature | Implementation | Location |
|---------|----------------|----------|
| Score gates | Hard-coded thresholds | `_should_send_signal_for_tier()` |
| Tier routing | if/elif in `format_signal()` | formatter.py |
| Feature matrix | Dict in `get_tier_features()` | tier_delivery.py |
| TP updates | `format_signal_update_tp_hit()` | formatter.py |
| No-trade alerts | `format_signal_no_trade_alert()` | formatter.py |
| Stats summary | `format_performance_summary_vip()` | formatter.py |
| Daily limits | Check in `should_send_signal()` | tier_delivery.py |
| Delivery logging | `log_delivery()` method | tier_delivery.py |
| Stats retrieval | `get_delivery_stats()` method | tier_delivery.py |

---

## ✅ Validation Checklist

- ✅ Tier constants defined and exported
- ✅ Quality gate functions working
- ✅ All tier formatters implemented
- ✅ Alert formatters implemented
- ✅ Main router with filtering
- ✅ TierDeliveryManager class complete
- ✅ Feature matrix available
- ✅ Delivery logging implemented
- ✅ All syntax validated (NO ERRORS)
- ✅ All tests passing (100%)
- ✅ Documentation complete

---

## 🚀 Ready for Integration

Next steps in [TIER_INTEGRATION_GUIDE.md](TIER_INTEGRATION_GUIDE.md):

1. Update signal dispatch with tier routing
2. Connect user tier from database
3. Implement TP tracking for updates
4. Implement market monitoring for alerts
5. Deploy and monitor

---

**Architecture is complete and validated ✅**

All components working correctly. Ready for production integration.

