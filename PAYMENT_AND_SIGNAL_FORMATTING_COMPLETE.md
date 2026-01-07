# Payment Confirmation & Tier-Specific Signal Formatting - Implementation

## Overview
Implemented payment confirmation flow and tier-specific signal formatting with partial TP handling for PREMIUM, VIP, ADMIN, and OWNER tiers.

## Components Implemented

### 1. Payment Handler Module (`payment_handler.py`)

**Functions**:

#### `verify_payment_and_upgrade_tier(user_id, tier, duration_days, amount)`
Verifies payment was processed and upgrades user tier in database.

Returns: `(success: bool, message: str)`

**Features**:
- Checks for existing subscription (idempotency)
- Activates new subscription with duration
- Returns tier-appropriate benefits message
- Handles errors gracefully

**Usage**:
```python
from signalrank_telegram.payment_handler import verify_payment_and_upgrade_tier

success, msg = await verify_payment_and_upgrade_tier(
    user_id=12345,
    tier="PREMIUM",
    duration_days=30,
    amount=12000.0
)
if success:
    await bot.send_message(user_id, msg)
```

#### `format_tier_upgrade_confirmation(tier, amount, duration_days, user_id)`
Formats confirmation message showing tier benefits before payment.

**Response Format**:
```
🎉 PREMIUM TIER (7–30 days)

✅ Performance analytics
✅ Signals with 65+ confidence
✅ Entry zones
✅ TP1 & TP2 levels
✅ Risk guidance
✅ 30-day history

💰 Amount: ₦12,000
⏰ Duration: 30 days

Click below to pay with Paystack.
```

### 2. Tier-Specific Signal Formatter (`tier_signal_formatter.py`)

#### PREMIUM Signal Format
Shows TP1 & TP2 with basic confidence and validity.

**Example**:
```
🚀 BUY SIGNAL

Asset: BTCUSDT
Timeframe: 15M
Session: London

Entry: 41,250 – 41,350
Stop Loss: 40,980
TP1: 41,700
TP2: 42,200

🔥 Confidence: 78%
⏳ Validity: Next 2 candles

⚠️ Risk max 1–2%
```

**Function**: `format_premium_signal(signal: Dict[str, Any]) -> str`

#### VIP Signal Format
Shows all 3 TP levels with comprehensive details.

**Example**:
```
🚀 BUY SIGNAL — VIP

Asset: BTCUSDT
Timeframe: 15M
Session: London
Market Regime: Trending

Entry Zone: 41,250 – 41,350
Stop Loss: 40,980

TP1: 41,700
TP2: 42,200
TP3: 42,900

📊 Confluence Score: 82 / 100
🔥 Confidence: VERY HIGH
📈 HTF Bias: Bullish
📊 Risk–Reward: 1 : 2.8

❌ Invalidation:
• Close below 41,000

🧠 Trade Logic:
• HTF structure aligned
• Breakout + retest
• Volume expansion
• Momentum confirmation

📌 Signal ID: BTC-15M-012
📈 Strategy Version: v1.2
```

**Function**: `format_vip_signal(signal: Dict[str, Any]) -> str`

#### PREMIUM TP Update (when TP hit)
Simple, concise update showing TP level hit.

**Example**:
```
📢 UPDATE — BTCUSDT

✅ TP1 HIT
🔒 Consider moving SL to breakeven
```

**Function**: `format_premium_tp_update(tp_level: int, asset: str, confidence: str = "HIGH") -> str`

#### VIP TP Update (when TP hit)
Detailed guidance with remaining TPs and management suggestions.

**Example**:
```
📣 Outcome Update — 🟢 TP1 HIT

BTCUSDT
✅ Profit: +2.67%

💡 Partial TP1 hit — Consider:
  • Move SL to breakeven
  • Trail remaining position
  • Target TP2 for more gains

📊 Remaining TPs: TP2 $42,200 | TP3 $42,900

This signal has been marked with an outcome in the tracker.
```

**Function**: `format_vip_tp_update(tp_level, asset, direction, entry, tp_price, remaining_tps) -> str`

#### VIP NO-TRADE Alert
Warning when market conditions are poor for trading.

**Example**:
```
🔵 VIP — NO-TRADE ALERT
⛔ NO TRADE ZONE — VIP

Market Conditions:
• Low volume
• Choppy structure
• Poor risk-to-reward

📉 Capital preservation mode active
```

**Function**: `format_vip_no_trade_alert(conditions: Dict[str, Any]) -> str`

### 3. Updated Upgrade Command (`commands.py`)

**Changes**:
- Uses `format_tier_upgrade_confirmation()` to show benefits
- Displays PREMIUM and VIP options separately
- Shows tier-specific benefits before payment link
- Displays VIP seat count remaining

**New Flow**:
1. User calls `/upgrade`
2. Bot shows PREMIUM benefits + payment links
3. Bot shows VIP benefits + payment link (if seats available)
4. User clicks link, completes payment
5. Paystack webhook fires
6. Bot calls `verify_payment_and_upgrade_tier()`
7. User tier updated in database
8. Confirmation message sent

### 4. Updated Bot Outcome Notifications (`bot.py`)

**Changes**:
- Detects TP level (TP1, TP2, TP3)
- Uses tier-specific formatters:
  - **VIP/ADMIN/OWNER**: `format_vip_tp_update()` - detailed guidance
  - **PREMIUM**: `format_premium_tp_update()` - simple concise
  - **FREE**: Minimal update - encourages upgrade

**Example Flow for VIP user when TP1 hit**:
1. Outcome computed: status = "tp1"
2. TP level detected: tp_level_num = 1
3. User tier: "vip"
4. Calls `format_vip_tp_update(tp_level=1, asset="BTCUSDT", ...)`
5. Returns detailed message with guidance
6. Sends to user via Telegram

## Integration Points

### Paystack Webhook
When payment confirmed:
```python
# In web/app.py webhook handler
success, msg = await verify_payment_and_upgrade_tier(
    user_id=telegram_user_id,
    tier=tier_from_paystack,
    duration_days=duration_from_paystack,
    amount=amount_from_paystack
)
if success:
    await application.bot.send_message(user_id, msg)
```

### Signal Dispatch
When sending new signal:
```python
# In bot dispatch_signals()
if tier == "PREMIUM":
    msg = format_premium_signal(signal_dict)
elif tier in ("VIP", "ADMIN", "OWNER"):
    msg = format_vip_signal(signal_dict)
else:
    msg = format_free_signal(signal_dict)

await bot.send_message(user_id, msg)
```

### Outcome Notification
When TP/SL hit:
```python
# In bot send_outcome_notifications()
user_tier = resolve_user_tier(user_id)
if user_tier in ("VIP", "ADMIN", "OWNER") and tp_level > 0:
    msg = format_vip_tp_update(tp_level, asset, direction, entry, tp_price, remaining_tps)
elif user_tier == "PREMIUM" and tp_level > 0:
    msg = format_premium_tp_update(tp_level, asset)
elif user_tier == "FREE":
    msg = format_free_tp_update(asset)
```

## Tier Visibility Summary

| Feature | FREE | PREMIUM | VIP | ADMIN/OWNER |
|---------|------|---------|-----|-------------|
| TPs shown | None | TP1, TP2 | TP1, TP2, TP3 | TP1, TP2, TP3 |
| Confidence | Basic % | % only | % + "HIGH/MODERATE" | % + "HIGH/MODERATE" |
| Session info | No | Yes | Yes | Yes |
| Regime | No | No | Yes | Yes |
| Confluence score | No | No | Yes | Yes |
| HTF Bias | No | No | Yes | Yes |
| Risk-Reward ratio | No | No | Yes | Yes |
| Trade Logic | No | No | Yes | Yes |
| Invalidation | No | No | Yes | Yes |
| TP Update detail | Minimal | Simple | Full guidance | Full guidance |

## Testing

**Test Payment Flow**:
```python
# Test payment confirmation
success, msg = await verify_payment_and_upgrade_tier(
    user_id=TEST_USER_ID,
    tier="PREMIUM",
    duration_days=30,
    amount=12000.0
)
assert success == True
assert "Premium Benefits" in msg
```

**Test Signal Formatting**:
```python
# Test PREMIUM signal format
signal = {
    "asset": "BTCUSDT",
    "timeframe": "15M",
    "direction": "long",
    "entry": 41250,
    "stop_loss": 40980,
    "take_profit": [41700, 42200],
    "score": 78,
    "session": "London",
    "validity": "Next 2 candles"
}
msg = format_premium_signal(signal)
assert "TP1: 41,700" in msg
assert "TP2: 42,200" in msg

# Test VIP signal format
signal["take_profit"] = [41700, 42200, 42900]
signal["regime"] = "Trending"
signal["confluence"] = 82
msg = format_vip_signal(signal)
assert "TP1: 41,700" in msg
assert "TP2: 42,200" in msg
assert "TP3: 42,900" in msg
assert "Confluence Score: 82" in msg
```

**Test TP Updates**:
```python
# Test PREMIUM TP update
msg = format_premium_tp_update(tp_level=1, asset="BTCUSDT")
assert "TP1 HIT" in msg
assert "breakeven" in msg

# Test VIP TP update
msg = format_vip_tp_update(
    tp_level=1,
    asset="BTCUSDT",
    direction="long",
    entry=41250,
    tp_price=41700,
    remaining_tps=[42200, 42900]
)
assert "TP1 HIT" in msg
assert "breakeven" in msg
assert "TP2" in msg
assert "TP3" in msg
```

## Files Created/Modified

### Created:
- `signalrank_telegram/payment_handler.py` (190 lines)
  - Payment confirmation and tier upgrade logic
  - Tier benefits formatting

- `signalrank_telegram/tier_signal_formatter.py` (238 lines)
  - Tier-specific signal formatters
  - TP update message builders
  - NO-TRADE alert formatter

### Modified:
- `signalrank_telegram/commands.py`
  - Updated `upgrade_command()` to use payment handlers
  - Shows tier benefits before payment link
  - Displays VIP seat availability

- `signalrank_telegram/bot.py`
  - Updated `send_outcome_notifications()`
  - Uses tier-specific TP update formatters
  - Proper TP level detection (1, 2, 3)

## Status: ✅ COMPLETE

All components implemented and integrated. Ready for production use with Paystack payment flow.
