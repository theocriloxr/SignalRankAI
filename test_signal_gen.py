#!/usr/bin/env python3
"""Quick test for signal generation."""
import sys
sys.path.insert(0, '.')
from strategies.run import run_all_strategies
import data.indicators
import pandas as pd

# Create sample market_data
candles = pd.DataFrame({
    'time': pd.date_range('2024-01-01', periods=100, freq='h'),
    'open': [50000 + i*10 for i in range(100)],
    'high': [50050 + i*10 for i in range(100)],
    'low': [49950 + i*10 for i in range(100)],
    'close': [50000 + i*10 for i in range(100)],
    'volume': [1000000 for _ in range(100)]
})

indicators = data.indicators.calculate_indicators(candles.to_dict('records'))

market_data = {
    '1h': {
        'candles': candles.to_dict('records'),
        'indicators': indicators
    }
}

signals = run_all_strategies('BTCUSDT', market_data, 'bullish')
print(f'Generated {len(signals)} signals')
for s in signals[:5]:
    print(f'  - {s.get("strategy_name")} dir={s.get("direction")} conf={s.get("confidence")}')
