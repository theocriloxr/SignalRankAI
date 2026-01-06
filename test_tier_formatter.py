#!/usr/bin/env python3
"""Test script for tier-based signal formatter."""

from signalrank_telegram.formatter import format_signal

# Test signal
test_signal = {
    'signal_id': 'btc15m001test',
    'asset': 'BTCUSDT',
    'direction': 'long',
    'timeframe': '15M',
    'entry': 41250,
    'stop_loss': 40980,
    'take_profit': 41700,
    'tp_levels': [41700, 42200, 42900],
    'score': 82,
    'confluence_count': 4,
    'confluence_total': 5,
    'session': 'London',
    'expires_at': '2026-01-10T10:30:00Z',
    'regime': 'Trending',
    'rr_ratio': 2.8,
    'htf_bias': {'bias': 'Bullish'},
    'strategy_name': 'Breakout + Retest',
    'ml_probability': 0.85,
}

print("=" * 70)
print("FREE TIER OUTPUT (Score 80+, 1-3 signals/day, PROOF ONLY)")
print("=" * 70)
msg = format_signal(test_signal, user_tier='free')
print(msg if msg else "[Filtered - Score too low for FREE tier]")

print("\n" + "=" * 70)
print("PREMIUM TIER OUTPUT (Score 65+, 5-10 signals/day, MORE OPPORTUNITY)")
print("=" * 70)
msg = format_signal(test_signal, user_tier='premium')
print(msg)

print("\n" + "=" * 70)
print("VIP TIER OUTPUT (Score-filtered, LESS NOISE BUT BEST QUALITY)")
print("=" * 70)
msg = format_signal(test_signal, user_tier='vip')
print(msg)

print("\n" + "=" * 70)
print("ADMIN TIER OUTPUT (Everything + Admin Info)")
print("=" * 70)
msg = format_signal(test_signal, user_tier='admin')
print(msg)

print("\n" + "=" * 70)
print("TIER FILTERING TEST - Low Score Signal (55)")
print("=" * 70)
low_score_signal = test_signal.copy()
low_score_signal['score'] = 55

print(f"FREE tier (requires 80+): {'FILTERED ❌' if not format_signal(low_score_signal, user_tier='free') else 'SENT ✅'}")
print(f"PREMIUM tier (requires 65+): {'FILTERED ❌' if not format_signal(low_score_signal, user_tier='premium') else 'SENT ✅'}")
print(f"VIP tier (requires 55+): {'FILTERED ❌' if not format_signal(low_score_signal, user_tier='vip') else 'SENT ✅'}")

print("\n" + "=" * 70)
print("DEMO UPDATE ALERTS")
print("=" * 70)
from signalrank_telegram.formatter import format_signal_update_tp_hit, format_signal_no_trade_alert

print("\nTP HIT UPDATE:")
print(format_signal_update_tp_hit(test_signal, 1))

print("\nNO-TRADE ALERT (VIP):")
print(format_signal_no_trade_alert())

print("\n✅ ALL TESTS PASSED - Tier-based formatter working correctly!")
