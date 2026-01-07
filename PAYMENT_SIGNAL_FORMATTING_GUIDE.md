# Payment & Signal Formatting - Quick Usage Guide

## 1. Payment Confirmation Flow

### Setup Paystack Webhook
In your `web/app.py` webhook handler:

```python
from signalrank_telegram.payment_handler import verify_payment_and_upgrade_tier

@app.post("/webhook/paystack")
async def paystack_webhook(request):
    # Verify signature (existing code)
    event = await request.json()
    
    if event['event'] == 'charge.success':
        reference = event['data']['reference']
        
        # Get payment details from Paystack
        tier = event['data']['metadata'].get('tier', 'FREE')
        user_id = event['data']['metadata'].get('user_id')
        duration_days = event['data']['metadata'].get('duration_days', 30)
        amount = event['data']['amount'] / 100  # Convert from kobo to naira
        
        # Verify and upgrade tier
        success, msg = await verify_payment_and_upgrade_tier(
            user_id=user_id,
            tier=tier,
            duration_days=duration_days,
            amount=amount
        )
        
        if success:
            # Send confirmation to user
            await application.bot.send_message(
                chat_id=user_id,
                text=msg
            )
        
        return {"status": "ok"}
```

## 2. Signal Display

### When Sending New Signals

```python
from signalrank_telegram.tier_signal_formatter import (
    format_premium_signal,
    format_vip_signal
)

# In dispatch_signals()
tier = resolve_user_tier(user_id)

if tier.lower() == "premium":
    msg = format_premium_signal(signal_dict)
elif tier.lower() in ("vip", "admin", "owner"):
    msg = format_vip_signal(signal_dict)
else:
    msg = format_free_signal(signal_dict)  # Your free format

await bot.send_message(user_id, msg)
```

## 3. Outcome Notifications

### When TP or SL is Hit

```python
from signalrank_telegram.tier_signal_formatter import (
    format_premium_tp_update,
    format_vip_tp_update
)

# In send_outcome_notifications()
user_tier = resolve_user_tier(user_id).lower()
tp_level = parse_tp_level(status)  # Returns 1, 2, 3, or 0

if user_tier in ("vip", "admin", "owner") and tp_level > 0:
    msg = format_vip_tp_update(
        tp_level=tp_level,
        asset=asset,
        direction=direction,
        entry=entry_price,
        tp_price=tp_prices[tp_level - 1],
        remaining_tps=tp_prices[tp_level:]
    )
elif user_tier == "premium" and tp_level > 0:
    msg = format_premium_tp_update(tp_level=tp_level, asset=asset)
else:
    # Your free tier update
    msg = format_free_tp_update(asset, status)

await bot.send_message(user_id, msg)
```

## 4. Upgrade Command

Updated `/upgrade` command now shows:

1. **PREMIUM benefits** with payment links
2. **VIP benefits** with seat count and payment link

No changes needed - it's automatic!

## 5. Signal Data Requirements

For proper formatting, ensure your signal dict includes:

### PREMIUM Signals
```python
signal = {
    "asset": "BTCUSDT",           # Required
    "timeframe": "15M",            # Required
    "direction": "long",           # Required
    "entry": 41250,                # Required
    "stop_loss": 40980,            # Required
    "take_profit": [41700, 42200], # Required (list of TPs)
    "score": 78,                   # Optional, shows confidence %
    "session": "London",           # Optional
    "validity": "Next 2 candles",  # Optional
}
```

### VIP Signals (all PREMIUM fields +)
```python
signal = {
    # All PREMIUM fields above +
    "regime": "Trending",              # Optional
    "confluence": 82,                  # Optional (0-100)
    "confluence_score": 82,            # Alternative field name
    "htf_bias": "Bullish",            # Optional
    "higher_timeframe_bias": "Bullish", # Alternative field name
    "risk_reward": 2.8,               # Optional
    "rr_estimate": 2.8,               # Alternative field name
    "invalidation": [                 # Optional (list or string)
        "Close below 41,000",
        "Break below support"
    ],
    "trade_logic": [                  # Optional (list or string)
        "HTF structure aligned",
        "Breakout + retest",
        "Volume expansion"
    ],
    "signal_id": "BTC-15M-012",       # Optional
    "version": "v1.2",                # Optional
    "entry_zone": 41350,              # Optional (high of entry zone)
    "entry_zone_high": 41350,         # Alternative field name
}
```

## 6. Message Examples

### PREMIUM Signal
```
🚀 BUY SIGNAL

Asset: BTCUSDT
Timeframe: 15M
Session: London

Entry: 41,250
Stop Loss: 40,980
TP1: 41,700
TP2: 42,200

🔥 Confidence: 78%
⏳ Validity: Next 2 candles

⚠️ Risk max 1–2%
```

### VIP Signal
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

📌 Signal ID: BTC-15M-012
📈 Strategy Version: v1.2
```

### PREMIUM TP1 Update
```
📢 UPDATE — BTCUSDT

✅ TP1 HIT
🔒 Consider moving SL to breakeven
```

### VIP TP1 Update
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

## 7. Troubleshooting

**Q: Signal not showing TP levels?**
A: Make sure `take_profit` field is a list: `[41700, 42200, 42900]` not just `41700`

**Q: Confidence not showing?**
A: Include `score` field in signal dict with numeric value (0-100)

**Q: VIP user not seeing TP3?**
A: Check that `take_profit` list has 3 elements

**Q: Session/Regime not showing?**
A: PREMIUM only shows session, VIP shows both. Make sure to include them in signal dict.

**Q: TP update not showing guidance?**
A: Make sure TP level is detected correctly (status = "tp1" for TP1, "tp2" for TP2, "tp3" for TP3)

## 8. Testing Locally

```python
# Test signal formatting
from signalrank_telegram.tier_signal_formatter import format_premium_signal, format_vip_signal

signal = {
    "asset": "BTCUSDT",
    "timeframe": "15M",
    "direction": "long",
    "entry": 41250,
    "stop_loss": 40980,
    "take_profit": [41700, 42200, 42900],
    "score": 78,
    "session": "London",
    "validity": "Next 2 candles",
    "regime": "Trending",
    "confluence": 82,
}

# Test PREMIUM format
premium_msg = format_premium_signal(signal)
print(premium_msg)

# Test VIP format
vip_msg = format_vip_signal(signal)
print(vip_msg)
```

That's it! The bot now has complete payment confirmation and tier-specific signal formatting. 🎉
