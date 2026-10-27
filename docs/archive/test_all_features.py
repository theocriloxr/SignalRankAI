"""
Test Script - Verify All New Features Working
Run this to test formatting before deploying
"""

from signalrank_telegram.formatter import format_signal
from engine.tier_notifications import TierNotificationManager
from datetime import datetime, timezone

print("=" * 60)
print("Testing Signal-Only Bot Features")
print("=" * 60)
print()

# Test signal with all new features
test_signal = {
    'signal_id': 'test123',
    'asset': 'BTCUSDT',
    'symbol': 'BTCUSDT',
    'direction': 'long',
    'timeframe': '1h',
    'entry': 45000,
    'entry_price': 45000,
    'stop_loss': 44400,
    'sl_price': 44400,
    'sl_pct': -1.33,
    'take_profit': 46200,
    'tp_levels': [
        {'price': 46200, 'pct': 2.67, 'exit_percent': 33},
        {'price': 47400, 'pct': 5.33, 'exit_percent': 33},
        {'price': 48600, 'pct': 8.00, 'exit_percent': 34}
    ],
    'score': 85,
    'confidence': 85,
    'confluence_count': 5,
    'confluence_total': 5,
    'rr_ratio': 2.4,
    'regime': 'trending',
    'ml_probability': 0.78,
    'strategy_name': 'Trend Following',
    'strategy_group': 'momentum',
    'strength': 'Strong',
    'contributors': ['EMA', 'RSI', 'Volume'],
    
    # NEW FEATURES
    'entry_zone': {
        'entry_price': 45000,
        'zone_low': 44800,
        'zone_high': 45200,
        'zone_width_pct': 0.44,
        'status': 'BUY'
    },
    'htf_bias': {
        'bias': 'bullish',
        'confidence': 80,
        'tf': '4h',
        'ema_50': 44500,
        'ema_200': 43000,
        'structure': 'bullish'
    },
    'mtf_confluence': {
        'score': 75,
        'aligned_tfs': ['5m', '15m', '1h', '4h'],
        'conflicting_tfs': [],
        'total_checked': 4
    },
    'session': 'LONDON',
    'expires_at': datetime.now(timezone.utc),
    'invalid_if_price': 44200,
    'reason': 'Strong uptrend + volume spike (2.1x) + breakout above resistance + retest confirmed',
    'position_size': 0.05,
    'suggested_risk_amount': 2250,
    'risk_pct': 5.0
}

# Test 1: VIP Signal Format
print("TEST 1: VIP Signal Format")
print("-" * 60)
vip_msg = format_signal(test_signal, display_tier='vip')
print(vip_msg)
print()
print("✅ VIP signal should show: entry zones, HTF bias, MTF alignment, strategy, ML score")
print()

# Test 2: Premium Signal Format
print("=" * 60)
print("TEST 2: Premium Signal Format")
print("-" * 60)
premium_msg = format_signal(test_signal, display_tier='premium')
print(premium_msg)
print()
print("✅ Premium signal should show: entry zones, HTF bias, MTF alignment, confidence")
print()

# Test 3: Free Signal Format (Limited)
print("=" * 60)
print("TEST 3: Free Signal Format (Limited)")
print("-" * 60)
free_msg = format_signal(test_signal, display_tier='free', limited=True)
print(free_msg)
print()
print("✅ Free signal should show: basic info only, upgrade prompt")
print()

# Test 4: TP Hit Notifications
print("=" * 60)
print("TEST 4: TP Hit Notifications")
print("-" * 60)
notifier = TierNotificationManager()

print("--- PREMIUM TP1 Hit ---")
tp_premium = notifier.format_tp_hit_notification(test_signal, 'premium', 1, 2.67)
print(tp_premium)
print()

print("--- FREE TP1 Hit ---")
tp_free = notifier.format_tp_hit_notification(test_signal, 'free', 1, 2.67)
print(tp_free)
print()
print("✅ Premium should show detailed advice, Free should be basic")
print()

# Test 5: SL Hit Notifications
print("=" * 60)
print("TEST 5: SL Hit Notifications")
print("-" * 60)

print("--- PREMIUM SL Hit ---")
sl_premium = notifier.format_sl_hit_notification(test_signal, 'premium', -1.33)
print(sl_premium)
print()

print("--- FREE SL Hit ---")
sl_free = notifier.format_sl_hit_notification(test_signal, 'free', -1.33)
print(sl_free)
print()
print("✅ Premium should show analysis, Free should be basic")
print()

# Test 6: Signal Update (Invalidation)
print("=" * 60)
print("TEST 6: Signal Update (Invalidation)")
print("-" * 60)
invalidate_msg = notifier.format_signal_update(
    test_signal,
    'premium',
    'invalidated',
    {'reason': 'HTF bias flipped from bullish to bearish'}
)
print(invalidate_msg)
print()
print("✅ Should show invalidation reason and exit advice")
print()

# Test 7: NO TRADE Alert
print("=" * 60)
print("TEST 7: NO TRADE Alert")
print("-" * 60)
no_trade_msg = notifier.format_no_trade_alert(
    reasons=['Low volume (<50% avg)', 'Choppy ranging market (ADX <15)', 'Wide spread (>2%)'],
    session='ASIA'
)
print(no_trade_msg)
print()
print("✅ Should list reasons and recommend waiting")
print()

# Test 8: Performance Update
print("=" * 60)
print("TEST 8: Performance Update (Premium)")
print("-" * 60)
perf_stats = {
    'win_rate': 66.7,
    'total_signals': 15,
    'wins': 10,
    'losses': 5,
    'top_pairs': [
        {'symbol': 'BTCUSDT', 'win_rate': 80},
        {'symbol': 'ETHUSDT', 'win_rate': 70}
    ],
    'worst_pairs': [
        {'symbol': 'BNBUSDT', 'win_rate': 40}
    ]
}
perf_msg = notifier.format_performance_update('premium', perf_stats)
print(perf_msg)
print()
print("✅ Should show win rate, top/worst performers")
print()

# Test 9: Backward Compatibility (Signal without new features)
print("=" * 60)
print("TEST 9: Backward Compatibility (Old Signal)")
print("-" * 60)
old_signal = {
    'signal_id': 'old123',
    'asset': 'ETHUSDT',
    'direction': 'short',
    'timeframe': '15m',
    'entry': 2500,
    'stop_loss': 2550,
    'take_profit': 2400,
    'score': 78,
    'regime': 'ranging'
    # NO new features (entry_zone, htf_bias, etc.)
}
old_msg = format_signal(old_signal, display_tier='premium')
print(old_msg)
print()
print("✅ Should fall back to old format gracefully")
print()

# Final Summary
print("=" * 60)
print("✅ ALL TESTS COMPLETE")
print("=" * 60)
print()
print("If all tests above look correct:")
print("1. All new features are working")
print("2. Tier-based formatting is consistent")
print("3. Backward compatibility maintained")
print("4. Ready to deploy to Railway!")
print()
print("Next step: Run 'python main.py' in DRY_RUN mode to test full pipeline")
print()
