"""Quick test for tier_gated_formatter module."""
from signalrank_telegram.tier_gated_formatter import format_tiered_signal, should_user_receive_signal

test_signal = {
    'asset': 'BTCUSDT',
    'direction': 'long',
    'entry': '45000.00',
    'stop_loss': '44500.00',
    'take_profit': ['45500', '46000', '47000'],
    'ml_probability': 0.82,
    'score': 85.0,
    'signal_id': 'test-123',
}

print('=' * 50)
print('FREE USER:')
print('=' * 50)
text, markup = format_tiered_signal(test_signal, 'free')
print(text)
print()

print('=' * 50)
print('PREMIUM USER:')
print('=' * 50)
text, markup = format_tiered_signal(test_signal, 'premium')
print(text)
print()

print('=' * 50)
print('SCORE GATES:')
print('=' * 50)
print(f'FREE receives 85 score: {should_user_receive_signal(85.0, "free")}')
print(f'FREE receives 75 score: {should_user_receive_signal(75.0, "free")}')
print(f'PREMIUM receives 75: {should_user_receive_signal(75.0, "premium")}')
print(f'VIP receives 70: {should_user_receive_signal(70.0, "vip")}')
